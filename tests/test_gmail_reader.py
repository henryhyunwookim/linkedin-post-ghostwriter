"""Unit tests for Gmail reader text parsing and summary extraction."""

import base64
import unittest
from src.gmail_reader import EmailDigest, _extract_text_and_links_from_part, extract_summary_block


class TestGmailReader(unittest.TestCase):
    def test_extract_summary_block_present(self):
        sample_body = (
            "Hey Henry,\n\n"
            "=== EMAIL SUMMARY ===\n"
            "Here is the synthesized summary of the thread regarding AI safety and cloud architecture.\n"
            "Key points:\n"
            "- Multi-agent systems need structured state checkpoints.\n"
            "- Cost reduction achieved by 30%.\n"
            "====================\n\n"
            "Begin forwarded message:\n"
            "From: colleague@example.com..."
        )
        extracted = extract_summary_block(sample_body)
        self.assertIn("=== EMAIL SUMMARY ===", extracted)
        self.assertIn("Multi-agent systems need structured state checkpoints", extracted)
        self.assertNotIn("Begin forwarded message", extracted)

    def test_extract_summary_block_absent(self):
        sample_body = "Just a standard email without summary block."
        extracted = extract_summary_block(sample_body)
        self.assertEqual(extracted, "")

    def test_extract_text_and_links_from_html_part(self):
        html_content = """
        <html>
          <body>
            <h1>Weekly AI News</h1>
            <p>Check out the new benchmark results at <a href="https://example.com/ai-benchmark">Benchmark</a>.</p>
            <p>Another resource: <a href="https://example.com/docs">Documentation</a></p>
          </body>
        </html>
        """
        b64_data = base64.urlsafe_b64encode(html_content.encode("utf-8")).decode("utf-8")
        part = {
            "mimeType": "text/html",
            "body": {"data": b64_data}
        }
        text, links = _extract_text_and_links_from_part(part)
        self.assertIn("Weekly AI News", text)
        self.assertIn("Check out the new benchmark results", text)
        self.assertIn("https://example.com/ai-benchmark", links)
        self.assertIn("https://example.com/docs", links)

    def test_email_digest_dataclass(self):
        digest = EmailDigest(
            source_type="ai_news",
            subject="Daily AI News Digest: Korea & Japan - Sept 18, 2026",
            sender="user@gmail.com",
            date_str="Fri, 18 Sep 2026 09:00:00 +0900",
            body_text="Coverage of regional AI initiatives...",
            summary_excerpt="Coverage of regional AI...",
            links=["https://example.com/news"],
            raw_id="msg123",
        )
        d_dict = digest.to_dict()
        self.assertEqual(d_dict["source_type"], "ai_news")
        self.assertEqual(d_dict["raw_id"], "msg123")
        self.assertEqual(len(d_dict["links"]), 1)


if __name__ == "__main__":
    unittest.main()
