<#
Licensed under the MIT-0 License.
#>

param(
    [switch]$SkipBingGrounding
)

$ErrorActionPreference = 'Stop'

Write-Host "Loading .env (repo root)" -ForegroundColor Cyan
Push-Location $PSScriptRoot
try {
    if (Test-Path .\scripts\load-env.ps1) {
        . .\scripts\load-env.ps1
    } else {
        Write-Warning "scripts/load-env.ps1 not found; relying on existing environment variables."
    }

    if ($SkipBingGrounding) {
        $env:SKIP_BING_GROUNDING = '1'
    }

    # Guardrail: do not run az implicitly; only run if user approves.
    if (-not $env:PROJECT_ENDPOINT -and (-not $env:FOUNDRY_ACCOUNT_NAME -or -not $env:FOUNDRY_PROJECT_NAME)) {
        if ($env:AZURE_RESOURCE_GROUP) {
            Write-Host "Missing Foundry project configuration." -ForegroundColor Yellow
            Write-Host "You can either set PROJECT_ENDPOINT (recommended) or set FOUNDRY_ACCOUNT_NAME + FOUNDRY_PROJECT_NAME." -ForegroundColor Yellow
            Write-Host "Optionally, I can try to discover account/project from the resource group using Azure CLI." -ForegroundColor Yellow

            $cmd1 = "az resource list -g $($env:AZURE_RESOURCE_GROUP) --resource-type Microsoft.CognitiveServices/accounts --query `"[?kind=='AIServices'].name`" -o json"
            $cmd2 = "az resource list -g $($env:AZURE_RESOURCE_GROUP) --resource-type Microsoft.CognitiveServices/accounts/projects --query `"[].name`" -o json"

            Write-Host "Commands that would be executed:" -ForegroundColor Cyan
            Write-Host "  $cmd1" -ForegroundColor DarkGray
            Write-Host "  $cmd2" -ForegroundColor DarkGray

            $answer = Read-Host "Approve running these az commands now? (y/N)"
            if ($answer -match '^(y|yes)$') {
                $env:ALLOW_AZ_DISCOVERY = '1'
            } else {
                Write-Host "Skipping az discovery." -ForegroundColor Yellow
            }
        }
    }

    Write-Host "Running smoke test..." -ForegroundColor Cyan
    python .\smoke_test_foundry_agents.py
}
finally {
    Pop-Location
}
