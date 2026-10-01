"""
LinkedIn Post Ghostwriter - Cloud Secrets Sync Utility.

Purpose:
    Uploads local sensitive configurations (credentials.json, GEMINI_API_KEY)
    to Google Cloud Secret Manager so that any secondary PC can run the
    ghostwriter pipeline immediately after cloning without manual file copying.

Usage:
    python -m src.sync_secrets
"""

from __future__ import annotations

import os
import subprocess
import sys

from src.config import (
    GCP_PROJECT_ID,
    GEMINI_API_KEY,
    SECRET_GEMINI_API_KEY,
    SECRET_GMAIL_CREDS,
    SECRET_NAME,
)


def _set_secret(secret_id: str, secret_value: str, project_id: str) -> bool:
    """Creates or updates a secret version in Secret Manager using gcloud CLI."""
    is_win = sys.platform == "win32"
    try:
        # Check if secret exists
        check_cmd = [
            "gcloud",
            "secrets",
            "describe",
            secret_id,
            f"--project={project_id}",
            "--format=value(name)",
        ]
        res = subprocess.run(check_cmd, capture_output=True, text=True, shell=is_win)
        if res.returncode != 0:
            print(f"[SyncSecrets] Creating new secret: {secret_id}...")
            create_cmd = [
                "gcloud",
                "secrets",
                "create",
                secret_id,
                f"--project={project_id}",
                "--replication-policy=automatic",
            ]
            subprocess.run(create_cmd, check=True, capture_output=True, shell=is_win)

        # Add secret version with value via stdin
        print(f"[SyncSecrets] Adding latest version for {secret_id}...")
        version_cmd = [
            "gcloud",
            "secrets",
            "versions",
            "add",
            secret_id,
            f"--project={project_id}",
            "--data-file=-",
        ]
        subprocess.run(
            version_cmd,
            input=secret_value,
            text=True,
            check=True,
            capture_output=True,
            shell=is_win,
        )
        print(f"[SyncSecrets] Successfully synced secret: {secret_id}")

        # Auto-prune old versions via gcloud CLI
        try:
            list_cmd = ["gcloud", "secrets", "versions", "list", secret_id, f"--project={project_id}", "--filter=state:ENABLED", "--format=value(name)"]
            list_res = subprocess.run(list_cmd, capture_output=True, text=True, shell=is_win)
            if list_res.returncode == 0:
                active_vers = [v.strip().split("/")[-1] for v in list_res.stdout.splitlines() if v.strip()]
                if len(active_vers) > 1:
                    sorted_vers = sorted(active_vers, key=lambda x: int(x) if x.isdigit() else 0, reverse=True)
                    for old_v in sorted_vers[1:]:
                        subprocess.run(["gcloud", "secrets", "versions", "destroy", old_v, f"--secret={secret_id}", f"--project={project_id}", "--quiet"], shell=is_win, capture_output=True)
        except Exception:
            pass

        return True
    except Exception as exc:
        print(f"[SyncSecrets] Error syncing {secret_id}: {exc}")
        return False


def main() -> None:
    print("============================================================")
    print(" LinkedIn Post Ghostwriter - Cloud Secrets Sync")
    print(f" Target GCP Project: {GCP_PROJECT_ID}")
    print("============================================================")

    # 1. Sync Gemini API Key
    if GEMINI_API_KEY:
        print(f"\n[1/3] Syncing Gemini API Key to Secret Manager ({SECRET_GEMINI_API_KEY})...")
        _set_secret(SECRET_GEMINI_API_KEY, GEMINI_API_KEY, GCP_PROJECT_ID)
    else:
        print("\n[1/3] WARNING: GEMINI_API_KEY not found in environment; skipped.")

    # 2. Sync credentials.json
    if os.path.exists("credentials.json"):
        print(f"\n[2/3] Syncing credentials.json to Secret Manager ({SECRET_GMAIL_CREDS})...")
        try:
            with open("credentials.json", "r", encoding="utf-8") as f:
                creds_content = f.read()
            _set_secret(SECRET_GMAIL_CREDS, creds_content, GCP_PROJECT_ID)
        except Exception as e:
            print(f"[2/3] Error reading credentials.json: {e}")
    else:
        print("\n[2/3] Note: credentials.json not found locally; skipped.")

    # 3. Check gmail-agent-token
    print(f"\n[3/3] Checking Gmail OAuth token secret ({SECRET_NAME})...")
    check_cmd = [
        "gcloud",
        "secrets",
        "describe",
        SECRET_NAME,
        f"--project={GCP_PROJECT_ID}",
        "--format=value(name)",
    ]
    is_win = sys.platform == "win32"
    res = subprocess.run(check_cmd, capture_output=True, text=True, shell=is_win)
    if res.returncode == 0:
        print(f"[3/3] Confirmed: {SECRET_NAME} is active in Secret Manager.")
    else:
        print(f"[3/3] Note: {SECRET_NAME} not found. Run 'deployment\\upload_token.ps1' after local auth.")

    print("\n[Done] Cloud Secrets sync complete. Any PC with gcloud access can now run this project!")


if __name__ == "__main__":
    main()
