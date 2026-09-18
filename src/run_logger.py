"""
LinkedIn Post Ghostwriter - Run Logger Module.

Purpose:
    Manages operational telemetry, pipeline execution history, and draft
    topic suggestion tracking independently from profile memory.
    
    Persists data to Google Cloud Storage (GCS) at `linkedin-ghostwriter/run_log.json`
    with automatic fallback to a system temp directory for offline development.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Any

from src.config import GCS_BUCKET_NAME, GCS_RUN_LOG_BLOB, LOCAL_RUN_LOG_FILE


class RunLogger:
    """Manages recording and reading pipeline execution logs and draft suggestions."""

    def __init__(
        self,
        bucket_name: str = GCS_BUCKET_NAME,
        blob_path: str = GCS_RUN_LOG_BLOB,
        local_path: str = LOCAL_RUN_LOG_FILE,
    ) -> None:
        self.bucket_name = bucket_name
        self.blob_path = blob_path
        self.local_path = local_path
        self._gcs_client = None

    def _get_gcs_client(self) -> Any:
        """Lazy initialization of Google Cloud Storage client."""
        if self._gcs_client is None:
            try:
                from google.cloud import storage

                self._gcs_client = storage.Client()
            except Exception:
                self._gcs_client = None
        return self._gcs_client

    def load_run_log(self) -> list[dict[str, Any]]:
        """Loads run log entries from GCS or local temporary cache."""
        client = self._get_gcs_client()
        if client and self.bucket_name:
            try:
                bucket = client.bucket(self.bucket_name)
                blob = bucket.blob(self.blob_path)
                if blob.exists():
                    data = blob.download_as_text(encoding="utf-8")
                    parsed = json.loads(data)
                    if isinstance(parsed, list):
                        return parsed
            except Exception as err:
                print(f"[RunLogger] Note: could not load run log via GCS SDK: {err}")

        # Fallback to gcloud CLI if running locally
        if self.bucket_name:
            try:
                import sys

                is_win = sys.platform == "win32"
                cmd = ["gcloud", "storage", "cat", f"gs://{self.bucket_name}/{self.blob_path}"]
                res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10, shell=is_win)
                parsed = json.loads(res.stdout)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass

        # Fallback to local temporary cache
        if os.path.exists(self.local_path):
            try:
                with open(self.local_path, "r", encoding="utf-8") as f:
                    parsed = json.load(f)
                    if isinstance(parsed, list):
                        return parsed
            except Exception:
                pass

        return []

    def record_run(
        self,
        status: str,
        topic_suggested: str | None = None,
        stats: dict[str, int] | None = None,
        elapsed_seconds: float = 0.0,
        error: str | None = None,
    ) -> None:
        """Appends a new execution record to the cloud run log."""
        runs = self.load_run_log()
        now_iso = datetime.now(timezone.utc).isoformat()

        entry = {
            "timestamp": now_iso,
            "status": status,
            "topic_suggested": topic_suggested,
            "stats": stats or {},
            "elapsed_seconds": round(elapsed_seconds, 1),
            "error": error,
        }
        runs.append(entry)

        # Retain last 100 execution runs
        if len(runs) > 100:
            runs = runs[-100:]

        self._save_runs(runs)

    def _save_runs(self, runs: list[dict[str, Any]]) -> None:
        """Saves run log entries to GCS and local temp cache."""
        data_str = json.dumps(runs, ensure_ascii=False, indent=2)

        # Save to local temp cache
        try:
            with open(self.local_path, "w", encoding="utf-8") as f:
                f.write(data_str)
        except Exception:
            pass

        # Save to GCS
        client = self._get_gcs_client()
        if client and self.bucket_name:
            try:
                bucket = client.bucket(self.bucket_name)
                blob = bucket.blob(self.blob_path)
                blob.upload_from_string(data_str, content_type="application/json")
                print(f"[RunLogger] Successfully recorded run in gs://{self.bucket_name}/{self.blob_path}")
                return
            except Exception as err:
                print(f"[RunLogger] Note: could not save run log via GCS SDK: {err}")

        # Fallback to gcloud CLI if SDK failed locally
        if self.bucket_name and os.path.exists(self.local_path):
            try:
                import sys

                is_win = sys.platform == "win32"
                cmd = ["gcloud", "storage", "cp", self.local_path, f"gs://{self.bucket_name}/{self.blob_path}"]
                subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15, shell=is_win)
                print(f"[RunLogger] Successfully recorded run via gcloud storage CLI.")
            except Exception:
                pass

    def get_recently_suggested_topics(self, limit: int = 8) -> list[str]:
        """Extracts recently suggested draft topics to prevent repetitive proposals."""
        runs = self.load_run_log()
        topics = []
        for r in reversed(runs):
            t = r.get("topic_suggested")
            if t and t not in topics:
                topics.append(t)
            if len(topics) >= limit:
                break
        return topics
