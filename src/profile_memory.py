"""
LinkedIn Post Ghostwriter - Profile Memory Persistence Module.

Purpose:
    Manages persistent profile memory and historical records about the user,
    their authentic LinkedIn presence, actual past published posts, and
    accumulated technical focus areas.

    Persists data canonically as a JSON file stored in Google Cloud Storage (GCS)
    at `linkedin-ghostwriter/profile_memory.json`, with fallback to a temporary
    cache path for offline local development.

    CRITICAL ARCHITECTURAL RULES:
    1. AI-generated drafts are NEVER saved into `post_history`.
    2. `post_history` and `recent_activities` represent the author's ACTUAL
       LinkedIn posts and activities.
    3. Pipeline execution logs belong in `RunLogger` (`run_log.json`), NOT here.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Any

from src.config import GCS_BUCKET_NAME, GCS_MEMORY_BLOB, LOCAL_MEMORY_FILE


def _get_default_memory() -> dict[str, Any]:
    """Returns baseline memory structure when no prior cloud records exist."""
    name = os.getenv("RECIPIENT_NAME", "Author")
    return {
        "profile": {
            "name": name,
            "headline": "AI & Cloud Solutions Architect",
            "about": (
                "Specializing in AI system architectures, serverless deployments, "
                "and digital transformation."
            ),
            "expertise_areas": [
                "Generative AI & Agentic Systems",
                "Cloud Architecture & Serverless Deployments",
                "System Design & Scalability",
                "AI Ethics & Enterprise Adoption",
            ],
            "last_scraped": None,
        },
        "post_history": [],
        "recent_activities": [],
        "topic_blacklist": [
            "politics",
            "unverified rumors",
            "generic motivational quotes",
        ],
        "accumulated_insights": [],
    }


class ProfileMemoryManager:
    """Manages reading, updating, and saving profile memory via Google Cloud Storage."""

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
                self._gcs_client = None
        return self._gcs_client

    def load_memory(self) -> dict[str, Any]:
        """Loads profile memory from GCS with gcloud CLI and local temp fallback."""
        # 1. Try Google Cloud Storage Python Client
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
            except Exception as err:
                print(f"[ProfileMemory] Note: could not load from GCS SDK: {err}")

        # 2. Try gcloud CLI fallback (works on any developer PC with active gcloud login)
        if self.bucket_name:
            try:
                is_win = sys.platform == "win32"
                cmd = ["gcloud", "storage", "cat", f"gs://{self.bucket_name}/{self.blob_path}"]
                res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=12, shell=is_win)
                parsed = json.loads(res.stdout)
                print(f"[ProfileMemory] Loaded memory from GCS via gcloud storage CLI.")
                return self._validate_and_fill_defaults(parsed)
            except Exception as e:
                pass

        # 3. Try local cache file (in OS temp directory)
        if os.path.exists(self.local_path):
            try:
                with open(self.local_path, "r", encoding="utf-8") as f:
                    parsed = json.load(f)
                print(f"[ProfileMemory] Loaded memory from local cache: {self.local_path}")
                return self._validate_and_fill_defaults(parsed)
            except Exception as err:
                print(f"[ProfileMemory] Error reading local cache {self.local_path}: {err}")

        # 4. Fall back to default baseline
        print("[ProfileMemory] Using default initial baseline memory.")
        default_mem = _get_default_memory()
        self._save_local(default_mem)
        return default_mem

    def save_memory(self, memory_data: dict[str, Any]) -> bool:
        """Saves profile memory to GCS and local temp cache."""
        # Strip deprecated run_log if present
        if "run_log" in memory_data:
            del memory_data["run_log"]

        self._save_local(memory_data)
        if not self.bucket_name:
            return True

        data_str = json.dumps(memory_data, ensure_ascii=False, indent=2)

        # 1. Try Google Cloud Storage Python Client
        client = self._get_gcs_client()
        if client and self.bucket_name:
            try:
                bucket = client.bucket(self.bucket_name)
                blob = bucket.blob(self.blob_path)
                blob.upload_from_string(data_str, content_type="application/json")
                print(f"[ProfileMemory] Successfully saved memory to gs://{self.bucket_name}/{self.blob_path}")
                return True
            except Exception as err:
                print(f"[ProfileMemory] Note: could not save via GCS SDK: {err}")

        # 2. Try gcloud CLI fallback
        if self.bucket_name and os.path.exists(self.local_path):
            try:
                is_win = sys.platform == "win32"
                cmd = ["gcloud", "storage", "cp", self.local_path, f"gs://{self.bucket_name}/{self.blob_path}"]
                subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15, shell=is_win)
                print(f"[ProfileMemory] Saved memory to GCS via gcloud storage CLI.")
                return True
            except Exception as err:
                print(f"[ProfileMemory] Failed to save memory to GCS via CLI: {err}")

        return False

    def _save_local(self, memory_data: dict[str, Any]) -> None:
        """Save memory to local temp cache."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.local_path)), exist_ok=True)
            with open(self.local_path, "w", encoding="utf-8") as f:
                json.dump(memory_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ProfileMemory] Warning: could not write local cache file: {e}")

    def _validate_and_fill_defaults(self, data: dict[str, Any]) -> dict[str, Any]:
        """Ensure all required keys exist and deprecated keys are removed."""
        defaults = _get_default_memory()
        for key, val in defaults.items():
            if key not in data:
                data[key] = val
            elif isinstance(val, dict) and isinstance(data[key], dict):
                for sub_key, sub_val in val.items():
                    if sub_key not in data[key]:
                        data[key][sub_key] = sub_val

        # Ensure run_log is purged from profile memory
        if "run_log" in data:
            del data["run_log"]

        return data

    def get_recent_topics(self, memory: dict[str, Any], limit: int = 8) -> list[str]:
        """Extract topics from actual published posts to reflect author's covered themes."""
        history = memory.get("post_history", [])
        return [entry.get("topic", "") for entry in history[-limit:] if entry.get("topic")]

    def update_from_linkedin(
        self,
        memory: dict[str, Any],
        profile_data: Any,
    ) -> None:
        """Updates memory with verified actual posts and activity extracted from LinkedIn.

        NOTE: This does NOT add AI-generated draft posts to post_history.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        memory["profile"]["last_scraped"] = now_iso

        if hasattr(profile_data, "headline") and profile_data.headline:
            memory["profile"]["headline"] = profile_data.headline
        if hasattr(profile_data, "about") and profile_data.about:
            memory["profile"]["about"] = profile_data.about

        # Ingest actual posts from profile if scraped
        actual_posts = getattr(profile_data, "actual_posts", [])
        if actual_posts:
            existing_texts = {p.get("post_text", "").strip() for p in memory.get("post_history", [])}
            for post in actual_posts:
                text = post.get("post_text", "").strip()
                if text and text not in existing_texts:
                    memory.setdefault("post_history", []).append(post)
                    existing_texts.add(text)

            # Keep post_history capped at most recent 50 actual posts
            if len(memory["post_history"]) > 50:
                memory["post_history"] = memory["post_history"][-50:]

        # Ingest recent LinkedIn activities (shares, comments, engagements)
        recent_activity = getattr(profile_data, "recent_activity", [])
        if recent_activity:
            existing_act = set(memory.get("recent_activities", []))
            for act in recent_activity:
                if act and act not in existing_act:
                    memory.setdefault("recent_activities", []).append(act)
                    existing_act.add(act)

            if len(memory["recent_activities"]) > 50:
                memory["recent_activities"] = memory["recent_activities"][-50:]
