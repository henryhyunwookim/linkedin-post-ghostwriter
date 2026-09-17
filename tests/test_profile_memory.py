"""Unit tests for profile memory persistence and management."""

import json
import os
import tempfile
import unittest
from src.profile_memory import ProfileMemoryManager, _get_default_memory


class TestProfileMemory(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_file.close()
        self.manager = ProfileMemoryManager(
            bucket_name="",  # disable GCS in unit test
            blob_path="",
            local_path=self.temp_file.name,
        )

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    def test_default_memory_structure(self):
        default_mem = _get_default_memory()
        self.assertIn("profile", default_mem)
        self.assertIn("post_history", default_mem)
        self.assertIn("accumulated_insights", default_mem)
        self.assertIn("run_log", default_mem)
        self.assertEqual(default_mem["profile"]["name"], "Henry Hyunwoo Kim")

    def test_save_and_load_memory(self):
        mem = _get_default_memory()
        mem["profile"]["headline"] = "Custom Test Headline"
        saved = self.manager.save_memory(mem)
        self.assertTrue(saved)

        loaded = self.manager.load_memory()
        self.assertEqual(loaded["profile"]["headline"], "Custom Test Headline")

    def test_record_run_and_topics(self):
        mem = _get_default_memory()
        draft = {
            "topic": "Agentic AI in Enterprise Workflows",
            "rationale": "High relevance this week",
            "post_text": "Sample LinkedIn post text...",
            "hashtags": ["#AI", "#Agents"],
            "sources_used": [{"title": "Weekly Digest", "url": "https://example.com"}],
        }

        self.manager.record_run(
            memory=mem,
            draft_result=draft,
            status="success",
            accumulated_points=[{"source": "test", "key_points": ["Point 1"]}],
        )

        self.assertEqual(len(mem["post_history"]), 1)
        self.assertEqual(mem["post_history"][0]["topic"], "Agentic AI in Enterprise Workflows")
        self.assertEqual(len(mem["run_log"]), 1)
        self.assertEqual(mem["run_log"][0]["status"], "success")

        recent_topics = self.manager.get_recent_topics(mem)
        self.assertIn("Agentic AI in Enterprise Workflows", recent_topics)


if __name__ == "__main__":
    unittest.main()
