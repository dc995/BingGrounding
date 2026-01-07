"""Bing grounding smoke test.

Licensed under the MIT-0 License.
"""

import json
import os
import re
import subprocess
from typing import Iterable, Optional, Tuple

from dotenv import load_dotenv
from azure.identity import AzureCliCredential, DefaultAzureCredential

from azure.ai.projects import AIProjectClient

from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    BingGroundingSearchConfiguration,
    BingGroundingSearchToolParameters,
    BingGroundingTool,
    BingGroundingToolDefinition,
)


_PROJECT_CONNECTION_ID_PATTERN = re.compile(
    r"^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/[^/]+/accounts/[^/]+/projects/[^/]+/connections/[^/]+$"
)

_ACCOUNT_CONNECTION_ID_PATTERN = re.compile(
    r"^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/[^/]+/accounts/[^/]+/connections/[^/]+$"
)


def _get_env_any(*names: str) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _env_truthy(name: str) -> bool:
    value = os.getenv(name)
    return value is not None and value.lower() in ("1", "true", "yes", "y")


def _az_json(args: list[str]) -> object:
    """Run an Azure CLI command and parse JSON output.

    This is used only as a convenience to auto-discover values if the user
    provides AZURE_RESOURCE_GROUP and has an authenticated Azure CLI.
    """

    try:
        completed = subprocess.run(
            ["az", *args, "-o", "json"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Azure CLI 'az' not found on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"Azure CLI command failed: az {' '.join(args)}\n{stderr}") from exc

    return json.loads(completed.stdout)


def _try_discover_foundry_from_resource_group(resource_group: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (account_name, project_name) if we can infer them from the RG."""

    accounts = _az_json(
        [
            "resource",
            "list",
            "-g",
            resource_group,
            "--resource-type",
            "Microsoft.CognitiveServices/accounts",
            "--query",
            "[?kind=='AIServices'].name",
        ]
    )

    if isinstance(accounts, list) and len(accounts) == 1:
        account_name = accounts[0]
    else:
        return None, None

    projects = _az_json(
        [
            "resource",
            "list",
            "-g",
            resource_group,
            "--resource-type",
            "Microsoft.CognitiveServices/accounts/projects",
            "--query",
            "[].name",
        ]
    )

    if not isinstance(projects, list):
        return account_name, None

    # Project resources come back like "{account}/{project}".
    normalized: list[str] = []
    for entry in projects:
        if not isinstance(entry, str):
            continue
        prefix = f"{account_name}/"
        if entry.startswith(prefix):
            normalized.append(entry[len(prefix) :])

    if len(normalized) == 1:
        return account_name, normalized[0]

    return account_name, None


def _derive_project_endpoint() -> str:
    explicit = _get_env_any("PROJECT_ENDPOINT", "AZURE_AI_PROJECT_ENDPOINT")
    if explicit:
        return explicit

    account_name = _get_env_any("FOUNDRY_ACCOUNT_NAME", "AI_FOUNDRY_ACCOUNT_NAME")
    project_name = _get_env_any("FOUNDRY_PROJECT_NAME", "PROJECT_NAME", "AI_FOUNDRY_PROJECT_NAME")

    # Optional convenience: discover account/project from resource group using Azure CLI.
    # This is OPT-IN so the script never runs `az` implicitly.
    if (not account_name or not project_name) and _env_truthy("ALLOW_AZ_DISCOVERY"):
        resource_group = _get_env_any("AZURE_RESOURCE_GROUP", "SANDBOX_RESOURCE_GROUP")
        if resource_group:
            discovered_account, discovered_project = _try_discover_foundry_from_resource_group(resource_group)
            account_name = account_name or discovered_account
            project_name = project_name or discovered_project

    if not account_name or not project_name:
        raise ValueError(
            "Missing configuration. Set PROJECT_ENDPOINT, or set both "
            "FOUNDRY_ACCOUNT_NAME and FOUNDRY_PROJECT_NAME. Optionally, set AZURE_RESOURCE_GROUP "
            "(or SANDBOX_RESOURCE_GROUP) to auto-discover via Azure CLI."
        )

    return f"https://{account_name}.services.ai.azure.com/api/projects/{project_name}"


def _choose_model_deployment(project_client: AIProjectClient) -> str:
    configured = _get_env_any(
        "MODEL_DEPLOYMENT_NAME",
        "AZURE_AI_MODEL_DEPLOYMENT_NAME",
        "AZURE_OPENAI_DEPLOYMENT",
    )
    if configured:
        return configured

    deployments = list(project_client.deployments.list())
    names: list[str] = []
    for deployment in deployments:
        name = getattr(deployment, "name", None)
        if isinstance(name, str) and name:
            names.append(name)

    if len(names) == 1:
        return names[0]

    if not names:
        raise ValueError("No deployments found in this Foundry project. Set MODEL_DEPLOYMENT_NAME explicitly.")

    formatted = "\n".join(f"- {n}" for n in sorted(set(names)))
    raise ValueError("Multiple deployments found; set MODEL_DEPLOYMENT_NAME to one of:\n" + formatted)


def _resolve_bing_connection_id(project_client: AIProjectClient) -> Optional[str]:
    """Resolve a Bing grounding connection reference.

    By default, returns the project-scoped ARM-style connection id from Foundry Project connections.

    Workaround mode:
      If BING_GROUNDING_USE_CONNECTION_NAME=1, return the connection name instead.
      This bypasses client-side id validation and can help in some environments.
    """

    use_name = _env_truthy("BING_GROUNDING_USE_CONNECTION_NAME")

    conn_id = _get_env_any(
        "BING_GROUNDING_CONNECTION_ID",
        "BING_CONNECTION_ID",
        "BING_PROJECT_CONNECTION_ID",
        "BING_CUSTOM_SEARCH_PROJECT_CONNECTION_ID",
    )

    if conn_id:
        if _PROJECT_CONNECTION_ID_PATTERN.match(conn_id):
            return conn_id

        if _ACCOUNT_CONNECTION_ID_PATTERN.match(conn_id):
            conn_name_from_id = conn_id.rsplit("/", 1)[-1]
            if use_name:
                return conn_name_from_id
            conn = project_client.connections.get(conn_name_from_id)
            return getattr(conn, "id", None)

        print("WARNING: Ignoring invalid Bing connection id from environment (expected ARM id format).")

    conn_name = _get_env_any("BING_GROUNDING_CONNECTION_NAME", "BING_CONNECTION_NAME")
    if conn_name:
        if use_name:
            return conn_name
        conn = project_client.connections.get(conn_name)
        return getattr(conn, "id", None)

    # Best-effort auto-detect: pick a connection whose name/target suggests Bing.
    candidates = []
    for c in project_client.connections.list():
        name = getattr(c, "name", "")
        target = getattr(c, "target", "")
        type_value = getattr(c, "type", "")
        haystack = f"{name} {target} {type_value}".lower()
        if "bing" in haystack or "ground" in haystack:
            candidates.append(c)

    if len(candidates) == 1:
        if use_name:
            return getattr(candidates[0], "name", None)
        return getattr(candidates[0], "id", None)

    return None


def _build_bing_tool_definitions(connection_id_or_name: str):
    # BingGroundingTool enforces a strict (project-scoped) ARM id format.
    # If we have that, use the simple tool.
    if _PROJECT_CONNECTION_ID_PATTERN.match(connection_id_or_name):
        return BingGroundingTool(connection_id=connection_id_or_name).definitions

    # Otherwise build the tool definition explicitly (works with connection name).
    config = BingGroundingSearchConfiguration(connection_id=connection_id_or_name)
    params = BingGroundingSearchToolParameters(search_configurations=[config])
    return [BingGroundingToolDefinition(bing_grounding=params)]


def _extract_text_and_citations(message) -> Tuple[str, Iterable[str]]:
    texts: list[str] = []
    citations: list[str] = []

    content = getattr(message, "content", None) or []
    for part in content:
        if getattr(part, "type", None) != "text":
            continue

        text_obj = getattr(part, "text", None)
        if text_obj is None:
            continue

        value = getattr(text_obj, "value", None)
        if value:
            texts.append(value)

        annotations = getattr(text_obj, "annotations", None) or []
        for ann in annotations:
            url_citation = getattr(ann, "url_citation", None)
            if not url_citation:
                continue
            url = getattr(url_citation, "url", None)
            if url:
                citations.append(url)

    return "\n".join(texts).strip(), citations


def _print_run_result(title: str, agents_client: AgentsClient, thread_id: str, run: object | None = None) -> None:
    messages = list(agents_client.messages.list(thread_id=thread_id))
    assistant_messages = [m for m in messages if getattr(m, "role", "") == "assistant"]

    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)

    if not assistant_messages:
        print("No assistant message returned.")
        if run is not None:
            status = getattr(run, "status", None)
            last_error = getattr(run, "last_error", None) or getattr(run, "error", None)
            if status is not None:
                print(f"Run status: {status}")
            if last_error:
                print(f"Run error: {last_error}")
        return

    last = assistant_messages[0]
    text, citations = _extract_text_and_citations(last)
    print(text or "(empty response)")

    if citations:
        print("\nCitations:")
        for url in dict.fromkeys(citations):
            print(f"- {url}")


def _print_project_connections(project_client: AIProjectClient) -> None:
    print("\nPROJECT CONNECTIONS")
    try:
        connections = list(project_client.connections.list())
    except Exception as exc:
        print(f"(unable to list connections: {exc})")
        return

    if not connections:
        print("(none found)")
        return

    for c in connections:
        name = getattr(c, "name", "")
        cid = getattr(c, "id", "")
        ctype = getattr(c, "type", "")
        target = getattr(c, "target", "")
        print(f"- name={name} | type={ctype} | target={target} | id={cid}")


def _run_bing_grounded(agents_client: AgentsClient, model_deployment: str, connection_id_or_name: str) -> None:
    agent = agents_client.create_agent(
        model=model_deployment,
        name="smoke-bing-grounding",
        instructions=(
            "You are a helpful assistant. Use Bing grounding to answer the user and include at least one citation."
        ),
        tools=_build_bing_tool_definitions(connection_id_or_name),
    )

    try:
        thread = agents_client.threads.create()
        prompt = (
            "Question 2 (BING grounded): What is today's date and the current weather in Seattle? "
            "Use Grounding with Bing Search and include source URLs."
        )
        print("\nINPUT (bing-grounded)")
        print(prompt)

        agents_client.messages.create(thread_id=thread.id, role="user", content=prompt)
        run = agents_client.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
        _print_run_result("Bing-grounded response", agents_client, thread.id, run)
    finally:
        try:
            agents_client.delete_agent(agent.id)
        except Exception:
            pass


def main() -> int:
    load_dotenv(override=False)

    endpoint = _derive_project_endpoint()

    credential = (
        AzureCliCredential() if _env_truthy("USE_AZURE_CLI_CREDENTIAL") else DefaultAzureCredential()
    )

    project_client = AIProjectClient(endpoint=endpoint, credential=credential)
    agents_client = AgentsClient(endpoint=endpoint, credential=credential)

    model_deployment = _choose_model_deployment(project_client)
    bing_connection_id = _resolve_bing_connection_id(project_client)

    print("\nCONFIG")
    print(f"- PROJECT_ENDPOINT: {endpoint}")
    print(f"- MODEL_DEPLOYMENT_NAME: {model_deployment}")
    if bing_connection_id:
        print(f"- BING_GROUNDING_CONNECTION: {bing_connection_id}")
    else:
        print("- BING_GROUNDING_CONNECTION: (not set / not auto-detected)")

    _print_project_connections(project_client)

    print("\nNOTE")
    print(
        "Bing grounding does not work with VPN or Private Endpoints in many setups. "
        "If your Foundry account/project is private-only, the non-grounded test can still validate reachability, "
        "but Bing grounding may fail or produce no citations."
    )

    comparison_prompt = (
        "What is today's date and the current weather in Seattle? "
        "Include source URLs if you used web grounding."
    )

    # 1) Non-grounded run
    no_bing_agent = agents_client.create_agent(
        model=model_deployment,
        name="smoke-no-grounding",
        instructions="You are a helpful assistant. Answer concisely. If you don't know, say so.",
    )

    try:
        no_bing_thread = agents_client.threads.create()
        non_grounded_prompt = (
            "Question 1 (NO grounding): "
            + comparison_prompt
            + " Do not browse the web; answer from general knowledge."
        )
        print("\nINPUT (non-grounded)")
        print(non_grounded_prompt)

        agents_client.messages.create(thread_id=no_bing_thread.id, role="user", content=non_grounded_prompt)
        agents_client.runs.create_and_process(thread_id=no_bing_thread.id, agent_id=no_bing_agent.id)
        _print_run_result("Non-grounded response", agents_client, no_bing_thread.id)

        # 2) Bing-grounded run
        if os.getenv("SKIP_BING_GROUNDING") not in ("1", "true", "TRUE"):
            if not bing_connection_id:
                raise ValueError(
                    "Missing Bing grounding connection reference. Set BING_GROUNDING_CONNECTION_ID, or set "
                    "BING_GROUNDING_CONNECTION_NAME to the name of a Foundry Project connection. "
                    "If you intentionally want to skip, set SKIP_BING_GROUNDING=1."
                )

            _run_bing_grounded(agents_client, model_deployment, bing_connection_id)

        return 0
    finally:
        agents_client.delete_agent(no_bing_agent.id)


if __name__ == "__main__":
    raise SystemExit(main())
