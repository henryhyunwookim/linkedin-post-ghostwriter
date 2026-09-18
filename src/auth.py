"""
LinkedIn Post Ghostwriter - Gmail Authentication Module.

Purpose:
    Handles OAuth 2.0 authentication for the Google Gmail API.
    Supports both local execution (using token.json) and Cloud Run
    execution (retrieving the token from Google Cloud Secret Manager).
"""

from __future__ import annotations

import json
import os
import sys
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from src.config import GCP_PROJECT_ID, SCOPES, SECRET_NAME


def _get_project_id() -> str | None:
    """Get the GCP project ID from configuration or Cloud Run metadata server."""
    if GCP_PROJECT_ID:
        return GCP_PROJECT_ID
    # Fallback: on Cloud Run, query the metadata server
    try:
        import requests

        resp = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/project/project-id",
            headers={"Metadata-Flavor": "Google"},
            timeout=2,
        )
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception:
        pass
    return None


def _is_cloud_run() -> bool:
    """Check if executing inside Google Cloud Run environment."""
    return os.getenv("K_SERVICE") is not None


def load_token_from_secret_manager() -> dict | None:
    """Load token content from Google Cloud Secret Manager via SDK or gcloud CLI."""
    project_id = _get_project_id()
    if not project_id:
        print("[Auth] WARNING: Could not determine project ID for Secret Manager.")
        return None

    # Method 1: Python Secret Manager SDK
    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{SECRET_NAME}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        token_data = response.payload.data.decode("UTF-8")
        print("[Auth] Successfully loaded token from Secret Manager (SDK).")
        return json.loads(token_data)
    except Exception as err:
        # Expected if ADC is not set or expired locally; fallback to gcloud CLI
        pass

    # Method 2: gcloud CLI fallback
    try:
        import subprocess

        is_win = sys.platform == "win32"
        cmd = [
            "gcloud",
            "secrets",
            "versions",
            "access",
            "latest",
            f"--secret={SECRET_NAME}",
            f"--project={project_id}",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10, shell=is_win)
        token_data = res.stdout.strip()
        if token_data:
            print("[Auth] Successfully loaded token from Secret Manager (gcloud CLI).")
            return json.loads(token_data)
    except Exception as err:
        print(f"[Auth] Error retrieving token from Secret Manager: {err}")

    return None


def fetch_credentials_from_secret_manager() -> str | None:
    """Attempts to retrieve credentials.json content from Secret Manager."""
    project_id = _get_project_id()
    if not project_id:
        return None

    from src.config import SECRET_GMAIL_CREDS

    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{SECRET_GMAIL_CREDS}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception:
        pass

    try:
        import subprocess

        is_win = sys.platform == "win32"
        cmd = [
            "gcloud",
            "secrets",
            "versions",
            "access",
            "latest",
            f"--secret={SECRET_GMAIL_CREDS}",
            f"--project={project_id}",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10, shell=is_win)
        return res.stdout.strip()
    except Exception:
        pass

    return None


def save_token_to_secret_manager(creds: Credentials) -> None:
    """Save refreshed token back to Secret Manager as a new version."""
    try:
        from google.cloud import secretmanager

        project_id = _get_project_id()
        if not project_id:
            print("[Auth] WARNING: Could not determine project ID for Secret Manager.")
            return

        client = secretmanager.SecretManagerServiceClient()
        parent = f"projects/{project_id}/secrets/{SECRET_NAME}"
        token_json = creds.to_json()

        client.add_secret_version(
            request={
                "parent": parent,
                "payload": {"data": token_json.encode("UTF-8")},
            }
        )
        print("[Auth] Successfully saved refreshed token to Secret Manager.")
    except Exception as e:
        print(f"[Auth] Error saving token to Secret Manager: {e}")


def authenticate_gmail(force_interactive: bool = False) -> Credentials:
    """Authenticates with Gmail API.

    Resolution order:
      1. Local token.json if present (and not force_interactive)
      2. Cloud Secret Manager (shared token for Cloud Run and multi-PC development)
      3. Interactive browser OAuth flow (fallback if token expired or missing)
    """
    creds = None
    on_cloud_run = _is_cloud_run()

    # --- 1. Try local token.json file ---
    if os.path.exists("token.json") and not force_interactive:
        try:
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
            print("[Auth] Loaded credentials from local token.json.")
        except Exception as e:
            print(f"[Auth] Error loading local token.json: {e}")
            creds = None

    # --- 2. Try Google Cloud Secret Manager (works on Cloud Run & any developer PC) ---
    if not creds and not force_interactive:
        token_data = load_token_from_secret_manager()
        if token_data:
            try:
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                print("[Auth] Initialized credentials from Cloud Secret Manager.")
            except Exception as e:
                print(f"[Auth] Error parsing token from Secret Manager: {e}")
                creds = None

    # --- 3. Refresh or re-authenticate if necessary ---
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("[Auth] Attempting to refresh access token...")
                creds.refresh(Request())
                print("[Auth] Access token refreshed successfully.")
                if os.path.exists("token.json"):
                    with open("token.json", "w", encoding="utf-8") as token:
                        token.write(creds.to_json())
                if on_cloud_run:
                    save_token_to_secret_manager(creds)
            except Exception as e:
                print(f"[Auth] Error refreshing token: {e}")
                creds = None

        if not creds:
            is_interactive = sys.stdin and sys.stdin.isatty()

            if (not is_interactive or on_cloud_run) and not force_interactive:
                raise RuntimeError(
                    "\n" + "=" * 80 + "\n"
                    "LINKEDIN GHOSTWRITER AUTHENTICATION ERROR: Token has expired or is missing.\n"
                    "\n"
                    "TO FIX (no redeployment needed):\n"
                    "1. On your local machine, run: python -m src.auth\n"
                    "2. Complete the browser login flow.\n"
                    "3. Upload the new token:  .\\deployment\\upload_token.ps1\n"
                    "\n"
                    "The Cloud Run service will automatically pick up the new token on the next run.\n"
                    + "=" * 80 + "\n"
                )

            # Check if credentials.json exists locally; if not, try to fetch from cloud
            if not os.path.exists("credentials.json"):
                cloud_creds = fetch_credentials_from_secret_manager()
                if cloud_creds:
                    with open("credentials.json", "w", encoding="utf-8") as f:
                        f.write(cloud_creds)
                    print("[Auth] Downloaded credentials.json from Google Cloud Secret Manager.")
                else:
                    raise FileNotFoundError(
                        "credentials.json not found in root directory or Secret Manager. "
                        "Please place credentials.json from Google Cloud Console in project root."
                    )

            print("[Auth] Starting local server for interactive authentication...")
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

            with open("token.json", "w", encoding="utf-8") as token:
                token.write(creds.to_json())
            print("[Auth] Successfully authenticated and saved token.json!")

    return creds


if __name__ == "__main__":
    print("LinkedIn Post Ghostwriter - Interactive Authentication Tool")
    print("=" * 60)
    try:
        authenticate_gmail(force_interactive=True)
        print("\nSuccess! token.json has been generated/updated.")
        print()
        print("Next step: upload the token to Secret Manager (for Cloud Run):")
        print("  .\\deployment\\upload_token.ps1")
    except Exception as err:
        print(f"\nAuthentication failed: {err}")
        sys.exit(1)
