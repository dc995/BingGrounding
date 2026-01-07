# Bing Grounding Sample — Agent/Copilot Guidelines

This repo is a standalone sample. Keep it safe to publish.

## Hard rules

- Do not hardcode secrets or subscription-specific identifiers in code or docs.
- Read all Azure-specific values from environment variables (`.env` for local dev).
- Never commit `.env` or any file containing real keys/tokens.
- Prefer placeholders like `<YOUR_SUBSCRIPTION_ID>` in docs/commands.

## Sensitive/Azure-specific data that must come from env vars

- `AZURE_SUBSCRIPTION_ID`, tenant IDs, resource IDs
- Foundry account/project names, endpoints
- Bing keys (must be retrieved at runtime; never checked in)

## Repo hygiene

- Keep `.env.example` up to date.
- Ensure `.gitignore` covers `.env`, venvs, and temp artifacts.
