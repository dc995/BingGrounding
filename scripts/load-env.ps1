<#
Licensed under the MIT-0 License.
#>

# Load environment variables from .env file
# Usage: . .\scripts\load-env.ps1

Write-Host "Loading environment variables from .env file..." -ForegroundColor Cyan

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^\s*([^#][^=]*)\s*=\s*(.*)\s*$") {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()

            # Remove quotes if present
            $value = $value -replace '^"(.*)"$', '$1'
            $value = $value -replace "^'(.*)'$", '$1'

            # Set environment variable
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
            Write-Host "Loaded $name" -ForegroundColor Green
        }
    }

    Write-Host "`nEnvironment variables loaded successfully." -ForegroundColor Green
} else {
    Write-Host ".env file not found in current directory" -ForegroundColor Red
    Write-Host "Make sure you're in the repo root directory" -ForegroundColor Yellow
}
