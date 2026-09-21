<#
.SYNOPSIS
    Deploys LinkedIn Post Ghostwriter to Google Cloud Run and configures Cloud Scheduler.

.DESCRIPTION
    Containerizes the Flask service, deploys it to Google Cloud Run, configures
    a Cloud Storage bucket for persistent profile memory, configures a dedicated
    IAM Service Account with invocation rights, and schedules a Cloud Scheduler
    job to trigger the ghostwriter pipeline every Friday at 9:00 PM JST (0 21 * * 5)
    in the Asia/Tokyo timezone.

.PARAMETER ProjectId
    GCP Project ID. Defaults to .env configuration or gen-lang-client-0480639565.

.PARAMETER Region
    Deployment region. Defaults to 'asia-northeast1'.

.PARAMETER ServiceName
    Cloud Run service name. Defaults to 'linkedin-post-ghostwriter'.

.PARAMETER JobName
    Cloud Scheduler job name. Defaults to 'linkedin-ghostwriter-weekly-trigger'.

.PARAMETER Schedule
    Cron expression. Defaults to '0 21 * * 5' (every Friday at 9:00 PM JST).

.PARAMETER TimeZone
    Schedule timezone. Defaults to 'Asia/Tokyo'.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$ProjectId,

    [Parameter(Mandatory = $false)]
    [string]$Region,

    [Parameter(Mandatory = $false)]
    [string]$ServiceName,

    [Parameter(Mandatory = $false)]
    [string]$JobName,

    [Parameter(Mandatory = $false)]
    [string]$Schedule,

    [Parameter(Mandatory = $false)]
    [string]$TimeZone,

    [Parameter(Mandatory = $false)]
    [string]$GeminiModel
)

$ErrorActionPreference = "Stop"

# Load local .env if available
$envPath = Join-Path $PSScriptRoot "..\" | Join-Path -ChildPath ".env"
if (Test-Path $envPath) {
    Write-Host "Loading configuration from: $envPath" -ForegroundColor DarkGray
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            Set-Variable -Name "ENV_$name" -Value $value -Scope Script
        }
    }
}

$PROJECT_ID = if ($ProjectId) { $ProjectId } elseif ($ENV_GCP_PROJECT_ID) { $ENV_GCP_PROJECT_ID } else { "gen-lang-client-0480639565" }
$REGION = if ($Region) { $Region } elseif ($ENV_GCP_REGION) { $ENV_GCP_REGION } else { "asia-northeast1" }
$SERVICE_NAME = if ($ServiceName) { $ServiceName } elseif ($ENV_SERVICE_NAME) { $ENV_SERVICE_NAME } else { "linkedin-post-ghostwriter" }
$JOB_NAME = if ($JobName) { $JobName } elseif ($ENV_JOB_NAME) { $ENV_JOB_NAME } else { "linkedin-ghostwriter-weekly-trigger" }
$SCHEDULE = if ($Schedule) { $Schedule } elseif ($ENV_SCHEDULE) { $ENV_SCHEDULE } else { "0 21 * * 5" }
$TIMEZONE = if ($TimeZone) { $TimeZone } elseif ($ENV_TIMEZONE) { $ENV_TIMEZONE } else { "Asia/Tokyo" }
$BUCKET_NAME = if ($ENV_GCS_BUCKET_NAME) { $ENV_GCS_BUCKET_NAME } else { "$PROJECT_ID-linkedin-memory" }
$GEMINI_MODEL = if ($GeminiModel) { $GeminiModel } elseif ($ENV_GEMINI_MODEL) { $ENV_GEMINI_MODEL } else { "gemini-3.8-flash" }

Write-Host "===========================================================================" -ForegroundColor Green
Write-Host " Deploying LinkedIn Post Ghostwriter to Google Cloud..." -ForegroundColor Green
Write-Host "  Project:    $PROJECT_ID"
Write-Host "  Region:     $REGION"
Write-Host "  Service:    $SERVICE_NAME"
Write-Host "  Job:        $JOB_NAME"
Write-Host "  Schedule:   $SCHEDULE ($TIMEZONE) [Friday 9:00 PM JST]"
Write-Host "  Memory GCS: gs://$BUCKET_NAME"
Write-Host "  Model:      $GEMINI_MODEL"
Write-Host "===========================================================================" -ForegroundColor Green
Write-Host ""

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Error "Google Cloud SDK (gcloud) is not found in PATH."
    exit 1
}

# Step 1: Set active project and default region
Write-Host "[Step 1/6] Setting active project to $PROJECT_ID and region to $REGION..." -ForegroundColor Cyan
gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION

# Step 2: Enable required GCP services
Write-Host "[Step 2/6] Enabling required APIs (Run, Build, Artifact Registry, Scheduler, Secret Manager, Storage)..." -ForegroundColor Cyan
gcloud services enable `
    run.googleapis.com `
    cloudbuild.googleapis.com `
    artifactregistry.googleapis.com `
    cloudscheduler.googleapis.com `
    secretmanager.googleapis.com `
    storage.googleapis.com

# Step 3: Create Cloud Storage bucket for profile memory if not exists
Write-Host "[Step 3/6] Ensuring Cloud Storage bucket gs://$BUCKET_NAME exists..." -ForegroundColor Cyan
$existingBucket = (& gcloud storage buckets list --project=$PROJECT_ID --filter="name:$BUCKET_NAME" --format="value(name)")
if (-not $existingBucket) {
    Write-Host "Creating bucket gs://$BUCKET_NAME in region $REGION..."
    & gcloud storage buckets create "gs://$BUCKET_NAME" --project=$PROJECT_ID --location=$REGION --uniform-bucket-level-access
} else {
    Write-Host "Bucket gs://$BUCKET_NAME already exists."
}

# Step 4: Deploy container from source to Cloud Run
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\")).Path
Set-Location $repoRoot

Write-Host "[Step 4/6] Deploying container from source (.) to Cloud Run..." -ForegroundColor Cyan
gcloud run deploy $SERVICE_NAME `
    --source . `
    --region $REGION `
    --no-allow-unauthenticated `
    --timeout 300 `
    --memory 1Gi `
    --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID,GCS_BUCKET_NAME=$BUCKET_NAME,GCP_REGION=$REGION,GEMINI_MODEL=$GEMINI_MODEL" `
    --quiet

# Retrieve the assigned service URL
$SERVICE_URL = (& gcloud run services describe $SERVICE_NAME --region $REGION --format "value(status.url)").Trim()
if (-not $SERVICE_URL) {
    Write-Error "Failed to retrieve the deployed service URL for $SERVICE_NAME."
    exit 1
}
Write-Host "Service deployed successfully at: $SERVICE_URL" -ForegroundColor Green

# Step 5: Configure dedicated Service Account for Cloud Scheduler
$SA_NAME = "linkedin-ghostwriter-sa"
$SA_EMAIL = "$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

Write-Host "[Step 5/6] Setting up Service Account ($SA_EMAIL) for Cloud Scheduler..." -ForegroundColor Cyan
if (-not (gcloud iam service-accounts list --filter="email:$SA_EMAIL" --format="value(email)")) {
    Write-Host "Creating service account: $SA_NAME..."
    gcloud iam service-accounts create $SA_NAME --display-name "LinkedIn Ghostwriter Cloud Scheduler Invoker"
} else {
    Write-Host "Service account $SA_NAME already exists."
}

# Grant run.invoker role on Cloud Run service to Service Account
Write-Host "Granting roles/run.invoker to $SA_EMAIL..."
$iamArgs = @(
    "run", "services", "add-iam-policy-binding", $SERVICE_NAME,
    "--region", $REGION,
    "--member=serviceAccount:$SA_EMAIL",
    "--role=roles/run.invoker",
    "--quiet"
)
& gcloud @iamArgs

# Grant Secret Manager Secret Accessor to Cloud Run default / runtime SA
Write-Host "Granting Secret Accessor permissions on Secret Manager..."
try {
    $projectNumber = (& gcloud projects describe $PROJECT_ID --format="value(projectNumber)").Trim()
    $computeSa = "$projectNumber-compute@developer.gserviceaccount.com"
    & gcloud projects add-iam-policy-binding $PROJECT_ID `
        --member="serviceAccount:$computeSa" `
        --role="roles/secretmanager.secretAccessor" `
        --quiet
} catch {
    Write-Host "Note: Secret Manager binding check completed."
}

# Step 6: Configure Cloud Scheduler recurring HTTP trigger (Friday 9:00 PM JST)
Write-Host "[Step 6/6] Configuring Cloud Scheduler recurring trigger for Friday 9:00 PM JST..." -ForegroundColor Cyan
$audience = $SERVICE_URL.TrimEnd('/')

if (gcloud scheduler jobs list --location=$REGION --filter="name:projects/$PROJECT_ID/locations/$REGION/jobs/$JOB_NAME" --format="value(name)") {
    Write-Host "Updating existing Cloud Scheduler job ($JOB_NAME)..."
    $schedArgs = @(
        "scheduler", "jobs", "update", "http", $JOB_NAME,
        "--location", $REGION,
        "--schedule", $SCHEDULE,
        "--time-zone", $TIMEZONE,
        "--uri", $SERVICE_URL,
        "--http-method", "POST",
        "--oidc-service-account-email", $SA_EMAIL,
        "--oidc-token-audience", $audience
    )
    & gcloud @schedArgs
} else {
    Write-Host "Creating new Cloud Scheduler job ($JOB_NAME)..."
    $schedArgs = @(
        "scheduler", "jobs", "create", "http", $JOB_NAME,
        "--location", $REGION,
        "--schedule", $SCHEDULE,
        "--time-zone", $TIMEZONE,
        "--uri", $SERVICE_URL,
        "--http-method", "POST",
        "--oidc-service-account-email", $SA_EMAIL,
        "--oidc-token-audience", $audience
    )
    & gcloud @schedArgs
}

Write-Host ""
Write-Host "===========================================================================" -ForegroundColor Green
Write-Host " Cloud Deployment & Scheduler Setup Complete!" -ForegroundColor Green
Write-Host " Service URL: $SERVICE_URL" -ForegroundColor Green
Write-Host " Schedule:    $SCHEDULE ($TIMEZONE) [Friday 9:00 PM JST]" -ForegroundColor Green
Write-Host " GCS Memory:  gs://$BUCKET_NAME" -ForegroundColor Green
Write-Host " Invoker SA:  $SA_EMAIL" -ForegroundColor Green
Write-Host "===========================================================================" -ForegroundColor Green
