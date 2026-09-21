"""
LinkedIn Post Ghostwriter - Configuration Module.

Purpose:
    Centralizes all environment variables, GCP infrastructure settings,
    Gemini API configurations, Gmail OAuth scopes, and LinkedIn profile targets.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dotenv import load_dotenv

# Load local environment variables from .env file if present in workspace root
load_dotenv()


def _resolve_cloud_secret(secret_name: str, project_id: str) -> str | None:
    """Attempts to retrieve a secret from GCP Secret Manager via SDK or gcloud CLI."""
    if not project_id:
        return None

    # Attempt 1: Secret Manager Python SDK
    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        val = response.payload.data.decode("utf-8").strip()
        if val:
            return val
    except Exception:
        pass

    # Attempt 2: gcloud CLI fallback (useful when running locally with active gcloud login)
    try:
        import sys

        is_win = sys.platform == "win32"
        cmd = [
            "gcloud",
            "secrets",
            "versions",
            "access",
            "latest",
            f"--secret={secret_name}",
            f"--project={project_id}",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10, shell=is_win)
        val = res.stdout.strip()
        if val:
            return val
    except Exception:
        pass

    return None


def _get_default_project_id() -> str:
    """Resolves GCP Project ID from env, active gcloud CLI config, or generic fallback."""
    proj = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if proj:
        return proj
    try:
        import sys

        is_win = sys.platform == "win32"
        res = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
            shell=is_win,
        )
        val = res.stdout.strip()
        if val and "(unset)" not in val:
            return val
    except Exception:
        pass
    return "your-gcp-project-id"


def _get_default_recipient_email() -> str:
    """Resolves target recipient email from env, active gcloud CLI account, or generic fallback."""
    email = os.getenv("RECIPIENT_EMAIL")
    if email:
        return email
    try:
        import sys

        is_win = sys.platform == "win32"
        res = subprocess.run(
            ["gcloud", "config", "get-value", "account"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
            shell=is_win,
        )
        val = res.stdout.strip()
        if val and "@" in val and "(unset)" not in val:
            return val
    except Exception:
        pass
    return "your_email@gmail.com"


# ===========================================================================
# 1. Google Cloud Platform & Serverless Configuration
# ===========================================================================
GCP_PROJECT_ID: str = _get_default_project_id()
GCP_REGION: str = os.getenv("GCP_REGION", "asia-northeast1")
SERVICE_NAME: str = os.getenv("SERVICE_NAME", "linkedin-post-ghostwriter")
JOB_NAME: str = os.getenv("JOB_NAME", "linkedin-ghostwriter-weekly-trigger")

# Cloud Storage for persistent profile memory and decoupled execution run logs
GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME", f"{GCP_PROJECT_ID}-linkedin-memory")
GCS_MEMORY_BLOB: str = os.getenv("GCS_MEMORY_BLOB", "linkedin-ghostwriter/profile_memory.json")
GCS_RUN_LOG_BLOB: str = os.getenv("GCS_RUN_LOG_BLOB", "linkedin-ghostwriter/run_log.json")

# Local cache/fallback path: uses OS temp directory so the git repository root remains clean
LOCAL_MEMORY_FILE: str = os.getenv(
    "LOCAL_MEMORY_FILE",
    os.path.join(tempfile.gettempdir(), "linkedin_ghostwriter_profile_memory.json"),
)
LOCAL_RUN_LOG_FILE: str = os.getenv(
    "LOCAL_RUN_LOG_FILE",
    os.path.join(tempfile.gettempdir(), "linkedin_ghostwriter_run_log.json"),
)

# Secret Manager secret names
SECRET_NAME: str = os.getenv("SECRET_NAME", "gmail-agent-token")
SECRET_GEMINI_API_KEY: str = os.getenv("SECRET_GEMINI_API_KEY", "gemini-api-key")
SECRET_GMAIL_CREDS: str = os.getenv("SECRET_GMAIL_CREDS", "gmail-oauth-credentials")
SECRET_LINKEDIN_LI_AT: str = os.getenv("SECRET_LINKEDIN_LI_AT", "linkedin-li-at")

# ===========================================================================
# 2. Large Language Model (Gemini) Configuration
# ===========================================================================
_raw_gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not _raw_gemini_key:
    # Auto-resolve from Secret Manager on clean PCs
    _raw_gemini_key = _resolve_cloud_secret(SECRET_GEMINI_API_KEY, GCP_PROJECT_ID)

GEMINI_API_KEY: str | None = _raw_gemini_key
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# ===========================================================================
# 3. Email Delivery & OAuth Scopes
# ===========================================================================
RECIPIENT_EMAIL: str = _get_default_recipient_email()
RECIPIENT_NAME: str = os.getenv("RECIPIENT_NAME", "Author")

# Gmail Scopes:
# - gmail.readonly: Read digests and email summaries from inbox
# - gmail.send: Send draft post to user's Gmail
SCOPES: list[str] = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# ===========================================================================
# 4. LinkedIn Profile Configuration & Optional Session Authentication
# ===========================================================================
LINKEDIN_PROFILE_URL: str = os.getenv(
    "LINKEDIN_PROFILE_URL", "https://www.linkedin.com/in/yourprofile/"
)

_raw_li_at = os.getenv("LINKEDIN_LI_AT")
if not _raw_li_at:
    _raw_li_at = _resolve_cloud_secret(SECRET_LINKEDIN_LI_AT, GCP_PROJECT_ID)

LINKEDIN_LI_AT: str | None = _raw_li_at

# ===========================================================================
# 5. Scheduling & Localization
# ===========================================================================
TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Tokyo")
SCHEDULE: str = os.getenv("SCHEDULE", "0 21 * * 5")  # Friday 9PM JST

