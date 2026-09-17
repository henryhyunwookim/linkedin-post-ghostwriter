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
    """Load token.json content from Google Cloud Secret Manager."""
    try:
        from google.cloud import secretmanager

        project_id = _get_project_id()
        if not project_id:
            print("[Auth] WARNING: Could not determine project ID for Secret Manager.")
            return None

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{SECRET_NAME}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        token_data = response.payload.data.decode("UTF-8")
        print("[Auth] Successfully loaded token from Secret Manager.")
        return json.loads(token_data)
    except Exception as e:
        print(f"[Auth] Error loading token from Secret Manager: {e}")
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

    On Cloud Run: loads token from Secret Manager, refreshes in-memory if needed.
    Locally: uses token.json file.
    """
    creds = None
    on_cloud_run = _is_cloud_run()

    # --- Load existing credentials ---
    if on_cloud_run and not force_interactive:
        token_data = load_token_from_secret_manager()
        if token_data:
            try:
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            except Exception as e:
                print(f"[Auth] Error parsing token from Secret Manager: {e}")
                creds = None
    elif os.path.exists("token.json") and not force_interactive:
        try:
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        except Exception as e:
            print(f"[Auth] Error loading token.json: {e}")
            creds = None

    # --- Refresh or re-authenticate ---
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("[Auth] Attempting to refresh access token...")
                creds.refresh(Request())
                if not on_cloud_run:
                    with open("token.json", "w", encoding="utf-8") as token:
                        token.write(creds.to_json())
                        print("[Auth] Saved refreshed token to token.json.")
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

            if not os.path.exists("credentials.json"):
                raise FileNotFoundError(
                    "credentials.json not found in root directory. "
                    "Please copy credentials.json from Google Cloud Console."
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
