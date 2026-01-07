# Bing Grounding Sample (Standalone)

This repo is a standalone smoke test for **Azure AI Foundry Agents**, including an optional **Grounding with Bing Search** run.

Sample repository:
https://github.com/dc995/BingGrounding

The smoke test runs two scenarios:

1) **Non-grounded agent**: validates you can create/run an agent in your Foundry project.
2) **Bing-grounded agent**: validates the agent can use the Bing grounding tool and return **citations (URLs)**.

## Official references

- Product documentation (Microsoft Learn):
	https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/bing-tools?view=foundry&viewFallbackFrom=foundry-classic&tabs=grounding-with-bing&pivots=python
- Workshop lab (Build your first agent):
	https://microsoft.github.io/build-your-first-agent-with-azure-ai-agent-service-workshop/lab-4-bing_search/
- Official SDK sample (Azure SDK for Python):
	https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-agents/samples/agents_tools/sample_agents_bing_grounding.py
- Source repository (Azure SDK for Python):
	https://github.com/Azure/azure-sdk-for-python

## How Bing Grounding is linked to the model (agent setup)

In Azure AI Foundry Agents, “linking Bing Grounding to the model” means:

1) Your Foundry project has a **Connection** that represents *Grounding with Bing Search* (metadata type `bing_grounding`).
2) When you create an agent, you attach the **Bing grounding tool** that points at that connection.

### 1) Ensure the Foundry Bing grounding Connection exists

This repo includes a helper to create/update the required connection(s):

```powershell
python .\create_bing_grounding_connection.py
```

The helper creates/updates both an account-level and project-level connection and ensures `isSharedToAll=true`.

### 2) Configure your connection reference (env vars)

Set ONE of these (recommended is name):

- `BING_GROUNDING_CONNECTION_NAME` (example: `binggrounding`)
- `BING_GROUNDING_CONNECTION_ID` (the project-scoped ARM connection id)

Also set:

- `PROJECT_ENDPOINT`
- `MODEL_DEPLOYMENT_NAME`

### 3) Attach Bing grounding when creating the agent (Python)

At runtime, the “link” is the tool definition passed to `create_agent(...)`.

Example pattern (mirrors what this repo does):

```python
import os

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import BingGroundingTool

endpoint = os.environ["PROJECT_ENDPOINT"]
credential = DefaultAzureCredential()

project_client = AIProjectClient(endpoint=endpoint, credential=credential)
agents_client = AgentsClient(endpoint=endpoint, credential=credential)

# Resolve the Foundry connection id from the connection name
conn_name = os.environ["BING_GROUNDING_CONNECTION_NAME"]
conn_id = project_client.connections.get(conn_name).id

# Create a Bing grounding tool bound to that connection
bing = BingGroundingTool(connection_id=conn_id)

# Create an agent using your model deployment + the Bing grounding tool
agent = agents_client.create_agent(
	model=os.environ["MODEL_DEPLOYMENT_NAME"],
	name="my-agent",
	instructions="Use Bing grounding for current info and include citations.",
	tools=bing.definitions,
)
```

Once the agent is created with `tools=...`, runs against that agent can call Bing grounding and return citations (URLs).

### Common pitfalls

- If the grounded run returns no citations, check VPN / private-only networking restrictions.
- If you see “connection id was not found”, the connection often exists but is not the correct `bing_grounding` schema in Foundry.

## Comparison: this sample vs the official SDK sample

- Scope
	- Official SDK sample: minimal example showing how to create an agent with the Bing grounding tool, run it, and print the response with citations.
	- This repo: standalone, runnable smoke test repo (plus a helper to create/update the Foundry Bing grounding connection).

- SDK usage / structure
	- Official SDK sample: uses `AIProjectClient(...).agents` and a single grounded scenario.
	- This repo: uses `AIProjectClient` for project resources (deployments/connections) and `AgentsClient` for agent lifecycle and runs.

- Configuration expectations
	- Official SDK sample: expects `PROJECT_ENDPOINT`, `MODEL_DEPLOYMENT_NAME`, and `BING_CONNECTION_NAME`.
	- This repo: supports multiple env-var aliases and can (in limited, opt-in cases) derive or auto-pick values (endpoint derivation, single-deployment auto-pick, best-effort connection auto-detect).

- Bing grounding tool wiring
	- Official SDK sample: assumes a project-scoped connection id can be resolved via the connection name and passed directly to the tool.
	- This repo: supports strict project-connection ids and includes a fallback path that can operate using a connection name (helpful in environments where client-side id validation is problematic).

- What gets tested
	- Official SDK sample: runs a single grounded scenario and prints run status / tool-call details / citations.
	- This repo: runs both a non-grounded baseline test and a grounded test (can skip grounding with `SKIP_BING_GROUNDING=1`).

- Connection creation
	- Official SDK sample: assumes the Foundry Bing grounding connection already exists.
	- This repo: includes a helper (`create_bing_grounding_connection.py`) to create/update the account + project connections via ARM and ensure `isSharedToAll=true`.

## Prerequisites

You need:

- Python 3.10+ (3.11 recommended)
- Azure CLI (`az`) installed
- Access to an Azure AI Foundry Project and at least one model deployment
- Access to a **Bing Grounding** resource (`Microsoft.Bing/accounts`, kind `Bing.Grounding`)
- Network: Bing grounding does **not** work from VPN / private-only network isolation

Azure service enablement (may be required in some subscriptions):

- If you're creating the Grounding with Bing Search resource via code-first tooling, you might need to register the Azure resource provider first:

```powershell
az provider register --namespace Microsoft.Bing
az provider show --namespace Microsoft.Bing --query registrationState -o tsv
```

Azure permissions (typical):

- You can authenticate with `az login`.
- You have enough permission on the Foundry account/project to list connections and run agents.
- You have enough permission on the Bing Grounding resource to call `listKeys`.

## One-time setup

### 1) Install Python dependencies

```powershell
python -m pip install -r .\requirements.txt
```

### 2) Authenticate to Azure

```powershell
az login
az account set --subscription <YOUR_SUBSCRIPTION_ID>
```

### 3) Create your `.env`

1. Copy `.env.example` to `.env`
2. Fill in values (do not commit `.env`)

Minimum required for running the smoke test:

- `PROJECT_ENDPOINT`
- `MODEL_DEPLOYMENT_NAME` (required if your project has multiple deployments)
- `BING_GROUNDING_CONNECTION_NAME` (unless you set `SKIP_BING_GROUNDING=1`)

Notes:

- The Python script reads `.env` via `python-dotenv`.
- The PowerShell runner loads `.env` via `scripts/load-env.ps1` and then runs the Python script.

### 4) Create/update the Bing Grounding connection in Foundry

This is the step that most often blocks new users.

The Bing grounding tool expects a Foundry **connection** whose schema represents **Grounding with Bing Search**.
This repo includes a helper that creates/updates both an account-level and project-level connection:

```powershell
python .\create_bing_grounding_connection.py
```

The helper reads these values from environment variables (typically your `.env`):

- `AZURE_SUBSCRIPTION_ID`
- `FOUNDRY_RESOURCE_GROUP`
- `FOUNDRY_ACCOUNT_NAME`
- `FOUNDRY_PROJECT_NAME`
- `BING_RESOURCE_ID` (resource id for your Bing Grounding account)
- `BING_GROUNDING_CONNECTION_NAME` (defaults to `binggrounding`)

After running, it prints the resulting connection ids and whether they are shared (`isSharedToAll=True`).

### 5) Verify the connection (optional but recommended)

Account-scoped connection:

```powershell
az cognitiveservices account connection show -g <FOUNDRY_RESOURCE_GROUP> -n <FOUNDRY_ACCOUNT_NAME> --connection-name <BING_GROUNDING_CONNECTION_NAME> --query "{category:properties.category,isSharedToAll:properties.isSharedToAll,meta:properties.metadata}" -o json
```

You should see:

- `properties.category` is `ApiKey`
- `properties.metadata.Type` is `bing_grounding`
- `properties.isSharedToAll` is `true`

## Run the smoke test

### Option A: PowerShell runner (recommended)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_smoke_test.ps1
```

To skip the Bing-grounded portion:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_smoke_test.ps1 -SkipBingGrounding
```

### Option B: Run Python directly

```powershell
python .\smoke_test_foundry_agents.py
```

## Expected output

- The non-grounded section prints a short explanation.
- The Bing-grounded section prints a response and a **Citations:** list containing URLs.

If the Bing-grounded run succeeds but has no citations, re-check that you're not on VPN / private-only networking.

## Troubleshooting

### `invalid_tool_input ... connection ID ... was not found`

This usually means the Foundry connection exists, but is not a **Grounding with Bing Search** connection schema.

Fix:

1. Re-run the helper:

```powershell
python .\create_bing_grounding_connection.py
```

1. Verify the connection has the expected values:

- `properties.category = ApiKey`
- `properties.metadata.Type = bing_grounding`
- `properties.isSharedToAll = true`

### Multiple deployments found

Set `MODEL_DEPLOYMENT_NAME` explicitly in `.env`.
