# GitHub Copilot Instructions

This repository is a **standalone sample** for Azure AI Foundry Agents with **Grounding with Bing Search**.

## Security and configuration rules (must follow)

- **Never hardcode** any secrets or environment-specific identifiers in code, tests, scripts, or docs.
  - Examples: subscription IDs, tenant IDs, resource group names, resource IDs, endpoints, connection IDs, API keys, tokens.
- **Always read configuration from environment variables**.
  - For local development, `.env` is used (loaded via `python-dotenv` and/or PowerShell `scripts/load-env.ps1`).
- If a required value is missing, **fail fast** with a clear error message listing the missing env vars.
- Do not print secrets to the console (API keys, tokens). Avoid logging full credential payloads.

## Documentation and commands

- In README/commands, use placeholders like `<YOUR_SUBSCRIPTION_ID>` and `<your-foundry-account>`.
- Do not paste real resource IDs, subscription IDs, or tenant IDs into documentation.

## Repo hygiene

- `.env` must remain untracked; only `.env.example` is committed.
- Keep `.gitignore` aligned to exclude `.env`, venvs, caches (`__pycache__`), and local temp files (e.g., `temp_*.json`).

## Style

- Prefer small, readable scripts.
- Prefer explicit variable names and clear error messages.
