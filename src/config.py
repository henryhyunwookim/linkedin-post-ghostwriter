"""
LinkedIn Post Ghostwriter - Configuration Module.

Purpose:
    Centralizes all environment variables, GCP infrastructure settings,
    Gemini API configurations, Gmail OAuth scopes, and LinkedIn profile targets.
"""

from __future__ import annotations

import os
from dotenv import load_dotenv

# Load local environment variables from .env file if present in workspace root
load_dotenv()

# ===========================================================================
# 1. Google Cloud Platform & Serverless Configuration
# ===========================================================================
GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "gen-lang-client-0480639565")
GCP_REGION: str = os.getenv("GCP_REGION", "asia-northeast1")
SERVICE_NAME: str = os.getenv("SERVICE_NAME", "linkedin-post-ghostwriter")
JOB_NAME: str = os.getenv("JOB_NAME", "linkedin-ghostwriter-weekly-trigger")

# Cloud Storage for persistent profile memory
GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME", f"{GCP_PROJECT_ID}-linkedin-memory")
GCS_MEMORY_BLOB: str = os.getenv("GCS_MEMORY_BLOB", "linkedin-ghostwriter/profile_memory.json")
LOCAL_MEMORY_FILE: str = os.getenv("LOCAL_MEMORY_FILE", "profile_memory.json")

# Secret Manager secret name for Gmail OAuth token
SECRET_NAME: str = os.getenv("SECRET_NAME", "linkedin-ghostwriter-token")

# ===========================================================================
# 2. Large Language Model (Gemini) Configuration
# ===========================================================================
GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# ===========================================================================
# 3. Email Delivery & OAuth Scopes
# ===========================================================================
RECIPIENT_EMAIL: str = os.getenv("RECIPIENT_EMAIL", "")
RECIPIENT_NAME: str = os.getenv("RECIPIENT_NAME", "Henry")

# Gmail Scopes:
# - gmail.readonly: Read digests and email summaries from inbox
# - gmail.send: Send draft post to user's Gmail
# - gmail.modify: Access metadata / mark processed if needed
SCOPES: list[str] = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

# ===========================================================================
# 4. LinkedIn Profile Configuration
# ===========================================================================
LINKEDIN_PROFILE_URL: str = os.getenv(
    "LINKEDIN_PROFILE_URL", "https://www.linkedin.com/in/henryhyunwookim/"
)

# ===========================================================================
# 5. Scheduling & Localization
# ===========================================================================
TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Tokyo")
SCHEDULE: str = os.getenv("SCHEDULE", "0 21 * * 5")  # Friday 9PM JST
