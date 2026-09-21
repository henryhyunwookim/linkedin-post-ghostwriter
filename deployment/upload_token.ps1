# Upload Gmail OAuth Token to Google Cloud Secret Manager
# Run this after: python -m src.auth
# This updates the token in Cloud Run WITHOUT redeploying the container.

$ErrorActionPreference = "Stop"

# Load local .env if available
$envPath = Join-Path $PSScriptRoot "..\" | Join-Path -ChildPath ".env"
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            Set-Variable -Name "ENV_$name" -Value $value -Scope Script
        }
    }
}

$activeGcloudProject = (& gcloud config get-value project 2>$null)
if ($activeGcloudProject -and $activeGcloudProject.Trim() -eq "(unset)") { $activeGcloudProject = $null }

$PROJECT_ID = if ($ENV_GCP_PROJECT_ID) { $ENV_GCP_PROJECT_ID } elseif ($activeGcloudProject) { $activeGcloudProject.Trim() } else { $null }

if (-not $PROJECT_ID) {
    Write-Error "GCP Project ID is required. Please set GCP_PROJECT_ID in .env or run 'gcloud config set project <PROJECT_ID>'."
    exit 1
}

$SECRET_NAME = if ($ENV_SECRET_NAME) { $ENV_SECRET_NAME } else { "gmail-agent-token" }

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\")).Path
$tokenPath = Join-Path $repoRoot "token.json"

if (-not (Test-Path $tokenPath)) {
    Write-Error "token.json not found at $tokenPath. Run 'python -m src.auth' first to generate it."
    exit 1
}

Write-Host "===========================================================================" -ForegroundColor Green
Write-Host " Uploading token.json to Google Cloud Secret Manager..." -ForegroundColor Green
Write-Host "  Project: $PROJECT_ID"
Write-Host "  Secret:  $SECRET_NAME"
Write-Host "===========================================================================" -ForegroundColor Green

# Check if secret already exists
$secretExists = gcloud secrets describe $SECRET_NAME --project $PROJECT_ID 2>$null

if ($secretExists) {
    Write-Host "Adding new version to existing secret: $SECRET_NAME..." -ForegroundColor Cyan
    gcloud secrets versions add $SECRET_NAME --data-file=$tokenPath --project $PROJECT_ID
} else {
    Write-Host "Creating new secret: $SECRET_NAME..." -ForegroundColor Cyan
    gcloud secrets create $SECRET_NAME --data-file=$tokenPath --project $PROJECT_ID --replication-policy="automatic"
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nDone! Cloud Run will automatically load the new token on subsequent runs." -ForegroundColor Green
} else {
    Write-Error "Failed to upload token to Secret Manager."
}
