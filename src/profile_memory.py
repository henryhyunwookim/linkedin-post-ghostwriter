"""
LinkedIn Post Ghostwriter - Profile Memory Persistence Module.

Purpose:
    Manages persistent memory and historical records about the user, their
    LinkedIn presence, past post topics, and accumulated insights.
    
    Persists data as a JSON file stored in Google Cloud Storage (GCS) on Cloud Run,
    with automatic fallback to a local JSON file for local development and testing.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from src.config import GCS_BUCKET_NAME, GCS_MEMORY_BLOB, LOCAL_MEMORY_FILE


def _get_default_memory() -> dict[str, Any]:
    """Returns baseline memory structure when no prior records exist."""
    return {
        "profile": {
            "name": "Henry Hyunwoo Kim",
            "headline": "AI & Cloud Solutions Architect | Digital Transformation & ODA",
            "about": (
                "Focusing on AI innovation, digital capacity building, and "
                "international development cooperation across Korea, Japan, "
                "and developing nations."
            ),
            "expertise_areas": [
                "Generative AI & Agentic Systems",
                "Cloud Architecture & Serverless Deployments",
                "International Cooperation & Digital ODA (KOICA/JICA/UN)",
                "AI Ethics, Policy, and Digital Inclusion",
            ],
            "last_scraped": None,
        },
        "post_history": [],
        "topic_blacklist": [
            "politics",
            "unverified rumors",
            "generic motivational quotes",
        ],
        "accumulated_insights": [],
        "run_log": [],
    }


class ProfileMemoryManager:
    """Manages reading, updating, and saving profile memory via GCS or local file."""

    def __init__(
        self,
        bucket_name: str = GCS_BUCKET_NAME,
        blob_path: str = GCS_MEMORY_BLOB,
        local_path: str = LOCAL_MEMORY_FILE,
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
            except Exception as e:
                print(f"[ProfileMemory] GCS client initialization error: {e}")
                self._gcs_client = None
        return self._gcs_client

    def load_memory(self) -> dict[str, Any]:
        """Loads profile memory from GCS, or fallback to local file / baseline."""
        client = self._get_gcs_client()
        if client and self.bucket_name:
            try:
                bucket = client.bucket(self.bucket_name)
                blob = bucket.blob(self.blob_path)
                if blob.exists():
                    data = blob.download_as_text(encoding="utf-8")
                    parsed = json.loads(data)
                    print(f"[ProfileMemory] Loaded memory from GCS gs://{self.bucket_name}/{self.blob_path}")
                    return self._validate_and_fill_defaults(parsed)
                else:
                    print(
                        f"[ProfileMemory] GCS blob gs://{self.bucket_name}/{self.blob_path} "
                        "not found yet. Initializing default baseline."
                    )
            except Exception as err:
                print(f"[ProfileMemory] Error downloading from GCS: {err}. Checking local fallback.")

        # Local file fallback
        if os.path.exists(self.local_path):
            try:
                with open(self.local_path, "r", encoding="utf-8") as f:
                    parsed = json.load(f)
                print(f"[ProfileMemory] Loaded memory from local file: {self.local_path}")
                return self._validate_and_fill_defaults(parsed)
            except Exception as err:
                print(f"[ProfileMemory] Error reading local file {self.local_path}: {err}")

        # Return default baseline
        print("[ProfileMemory] Using default initial baseline memory.")
        default_mem = _get_default_memory()
        self._save_local(default_mem)
        return default_mem

    def save_memory(self, memory_data: dict[str, Any]) -> bool:
        """Saves memory to GCS and local copy."""
        # Always write to local file for cache/diagnostics
        self._save_local(memory_data)

        client = self._get_gcs_client()
        if client and self.bucket_name:
            try:
                bucket = client.bucket(self.bucket_name)
                blob = bucket.blob(self.blob_path)
                data = json.dumps(memory_data, ensure_ascii=False, indent=2)
                blob.upload_from_string(data, content_type="application/json")
                print(f"[ProfileMemory] Successfully saved memory to gs://{self.bucket_name}/{self.blob_path}")
                return True
            except Exception as err:
                print(f"[ProfileMemory] Failed to save memory to GCS: {err}")
                return False
        return True

    def _save_local(self, memory_data: dict[str, Any]) -> None:
        """Save memory to local file."""
        try:
            with open(self.local_path, "w", encoding="utf-8") as f:
                json.dump(memory_data, f, ensure_ascii=False, indent=2)
            print(f"[ProfileMemory] Saved memory locally to {self.local_path}")
        except Exception as e:
            print(f"[ProfileMemory] Warning: could not write local memory file: {e}")

    def _validate_and_fill_defaults(self, data: dict[str, Any]) -> dict[str, Any]:
        """Ensure all required keys exist in memory dictionary."""
        defaults = _get_default_memory()
        for key, val in defaults.items():
            if key not in data:
                data[key] = val
            elif isinstance(val, dict) and isinstance(data[key], dict):
                for sub_key, sub_val in val.items():
                    if sub_key not in data[key]:
                        data[key][sub_key] = sub_val
        return data

    def get_recent_topics(self, memory: dict[str, Any], limit: int = 8) -> list[str]:
        """Extract recent topics already posted to avoid duplicate themes."""
        history = memory.get("post_history", [])
        return [entry.get("topic", "") for entry in history[-limit:] if entry.get("topic")]

    def record_run(
        self,
        memory: dict[str, Any],
        draft_result: dict[str, Any] | None,
        status: str = "success",
        profile_update: dict[str, Any] | None = None,
        accumulated_points: list[dict[str, Any]] | None = None,
    ) -> None:
        """Appends run information, new post record, and insights into memory."""
        now_iso = datetime.now(timezone.utc).isoformat()

        # Update profile if provided
        if profile_update:
            if "headline" in profile_update and profile_update["headline"]:
                memory["profile"]["headline"] = profile_update["headline"]
            if "about" in profile_update and profile_update["about"]:
                memory["profile"]["about"] = profile_update["about"]
            memory["profile"]["last_scraped"] = now_iso

        # Append post history if draft succeeded
        if draft_result:
            post_entry = {
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "topic": draft_result.get("topic", "Untitled Topic"),
                "rationale": draft_result.get("rationale", ""),
                "post_text": draft_result.get("post_text", ""),
                "hashtags": draft_result.get("hashtags", []),
                "sources_used": draft_result.get("sources_used", []),
            }
            memory.setdefault("post_history", []).append(post_entry)

        # Append insights
        if accumulated_points:
            memory.setdefault("accumulated_insights", []).extend(accumulated_points)
            # Keep accumulated insights capped at last 50 entries
            if len(memory["accumulated_insights"]) > 50:
                memory["accumulated_insights"] = memory["accumulated_insights"][-50:]

        # Append run log
        run_entry = {
            "timestamp": now_iso,
            "status": status,
            "topic_chosen": draft_result.get("topic") if draft_result else None,
        }
        memory.setdefault("run_log", []).append(run_entry)
        # Keep run log capped at 50 entries
        if len(memory["run_log"]) > 50:
            memory["run_log"] = memory["run_log"][-50:]
