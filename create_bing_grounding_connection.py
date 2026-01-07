"""Create/update the Foundry Bing grounding connection.

Licensed under the MIT-0 License.
"""

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class ArmResponse:
    status: int
    body: dict | None
    raw: str


def _env_truthy(name: str) -> bool:
    value = os.getenv(name)
    return value is not None and value.lower() in ("1", "true", "yes", "y")


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _get_credential():
    from azure.identity import AzureCliCredential, DefaultAzureCredential

    if _env_truthy("USE_AZURE_CLI_CREDENTIAL"):
        return AzureCliCredential()

    return DefaultAzureCredential(exclude_shared_token_cache_credential=True)


def _arm_request(method: str, url: str, token: str, body: dict | None = None) -> ArmResponse:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url=url, method=method, headers=headers, data=data)

    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else None
            return ArmResponse(status=resp.status, body=parsed, raw=raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = None
        return ArmResponse(status=e.code, body=parsed, raw=raw)


def _ensure_shared(url: str, token: str) -> ArmResponse:
    # Some API versions default isSharedToAll=false on create, even when requested.
    # Try a PATCH first (best practice for partial update). If PATCH isn't supported,
    # callers fall back to a full PUT.
    return _arm_request(
        "PATCH",
        url,
        token,
        # The connection RP requires the discriminator property name `AuthType` in PATCH bodies.
        body={"properties": {"AuthType": "ApiKey", "category": "ApiKey", "isSharedToAll": True}},
    )


def main() -> int:
    load_dotenv(override=False)

    subscription_id = _require_env("AZURE_SUBSCRIPTION_ID")
    foundry_rg = _require_env("FOUNDRY_RESOURCE_GROUP")
    foundry_account = _require_env("FOUNDRY_ACCOUNT_NAME")
    foundry_project = _require_env("FOUNDRY_PROJECT_NAME")

    bing_resource_id = _require_env("BING_RESOURCE_ID")
    connection_name = os.getenv("BING_GROUNDING_CONNECTION_NAME", "binggrounding")

    bing_api_version = os.getenv("BING_ARM_API_VERSION", "2025-05-01-preview")
    connections_api_version = os.getenv("FOUNDRY_CONNECTIONS_API_VERSION", "2025-10-01-preview")

    cred = _get_credential()
    token = cred.get_token("https://management.azure.com/.default").token

    # 1) Get Bing endpoint and keys
    bing_show = _arm_request(
        "GET",
        f"https://management.azure.com{bing_resource_id}?api-version={bing_api_version}",
        token,
    )
    if bing_show.status >= 400:
        print("Failed to GET Bing resource:", bing_show.status)
        print(bing_show.raw)
        return 2

    bing_endpoint = (bing_show.body or {}).get("properties", {}).get("endpoint")
    if not bing_endpoint:
        print("Bing resource did not return properties.endpoint")
        print(bing_show.raw)
        return 2

    bing_keys = _arm_request(
        "POST",
        f"https://management.azure.com{bing_resource_id}/listKeys?api-version={bing_api_version}",
        token,
        body={},
    )
    if bing_keys.status >= 400:
        print("Failed to listKeys on Bing resource:", bing_keys.status)
        print(bing_keys.raw)
        return 2

    key1 = (bing_keys.body or {}).get("key1")
    if not key1:
        print("listKeys response did not include key1")
        print(bing_keys.raw)
        return 2

    # 2) Create/update connections
    account_base_id = (
        f"/subscriptions/{subscription_id}/resourceGroups/{foundry_rg}"
        f"/providers/Microsoft.CognitiveServices/accounts/{foundry_account}"
    )

    account_conn_url = (
        f"https://management.azure.com{account_base_id}/connections/{connection_name}"
        f"?api-version={connections_api_version}"
    )

    account_conn_body = {
        "name": connection_name,
        "type": "Microsoft.CognitiveServices/accounts/connections",
        "properties": {
            "authType": "ApiKey",
            # Align with the official Foundry connection template for Bing Grounding.
            "category": "ApiKey",
            "target": bing_endpoint,
            "isSharedToAll": True,
            "credentials": {"key": key1},
            "metadata": {
                "ApiType": "Azure",
                "ResourceId": bing_resource_id,
                "Type": "bing_grounding",
            },
        },
    }

    account_put = _arm_request("PUT", account_conn_url, token, body=account_conn_body)
    if account_put.status >= 400:
        print("Failed to PUT account connection:", account_put.status)
        print(account_put.raw)
        return 3

    account_get = _arm_request("GET", account_conn_url, token)
    if account_get.status >= 400:
        print("Account connection PUT succeeded but GET failed:", account_get.status)
        print(account_get.raw)
        return 4

    if (account_get.body or {}).get("properties", {}).get("isSharedToAll") is not True:
        patch_resp = _ensure_shared(account_conn_url, token)
        if patch_resp.status == 405:
            patch_resp = _arm_request("PUT", account_conn_url, token, body=account_conn_body)
        if patch_resp.status >= 400:
            print("WARNING: Failed to set account isSharedToAll=true:", patch_resp.status)
            print(patch_resp.raw)
        account_get = _arm_request("GET", account_conn_url, token)

    # 3) Create/update project connection
    conn_base_id = (
        f"/subscriptions/{subscription_id}/resourceGroups/{foundry_rg}"
        f"/providers/Microsoft.CognitiveServices/accounts/{foundry_account}"
        f"/projects/{foundry_project}"
    )

    conn_url = (
        f"https://management.azure.com{conn_base_id}/connections/{connection_name}"
        f"?api-version={connections_api_version}"
    )

    conn_body = {
        "name": connection_name,
        "type": "Microsoft.CognitiveServices/accounts/projects/connections",
        "properties": {
            "authType": "ApiKey",
            "category": "ApiKey",
            "target": bing_endpoint,
            "isSharedToAll": True,
            "credentials": {"key": key1},
            "metadata": {
                "ApiType": "Azure",
                "ResourceId": bing_resource_id,
                "Type": "bing_grounding",
            },
        },
    }

    put_resp = _arm_request("PUT", conn_url, token, body=conn_body)
    if put_resp.status >= 400:
        print("Failed to PUT project connection:", put_resp.status)
        print(put_resp.raw)
        return 5

    get_resp = _arm_request("GET", conn_url, token)
    if get_resp.status >= 400:
        print("Project connection PUT succeeded but GET failed:", get_resp.status)
        print(get_resp.raw)
        return 6

    if (get_resp.body or {}).get("properties", {}).get("isSharedToAll") is not True:
        patch_resp = _ensure_shared(conn_url, token)
        if patch_resp.status == 405:
            patch_resp = _arm_request("PUT", conn_url, token, body=conn_body)
        if patch_resp.status >= 400:
            print("WARNING: Failed to set project isSharedToAll=true:", patch_resp.status)
            print(patch_resp.raw)
        get_resp = _arm_request("GET", conn_url, token)

    account_id = (account_get.body or {}).get("id")
    account_shared = (account_get.body or {}).get("properties", {}).get("isSharedToAll")
    project_id = (get_resp.body or {}).get("id")
    project_shared = (get_resp.body or {}).get("properties", {}).get("isSharedToAll")

    print("Updated Bing grounding connections:")
    print(f"  name: {connection_name}")
    print(f"  account: {account_id} (isSharedToAll={account_shared})")
    print(f"  project: {project_id} (isSharedToAll={project_shared})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
