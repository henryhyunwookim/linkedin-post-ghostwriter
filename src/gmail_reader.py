"""
LinkedIn Post Ghostwriter - Gmail Reader Module.

Purpose:
    Retrieves and parses incoming emails from the user's Gmail inbox over the
    past N days (default 7 days). Targets four primary sources:
      1. gmail-agent email summaries (body contains '=== EMAIL SUMMARY ===')
      2. AI News Digest (subject contains 'Daily AI News Digest')
      3. YouTube Digest (subject contains 'YouTube Intelligence Digest')
      4. ByteByteGo Substack newsletter (from: bytebytego@substack.com)
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


@dataclass
class EmailDigest:
    """Represents a structured email digest retrieved from Gmail."""

    source_type: str  # "email_summary" | "ai_news" | "youtube_digest" | "bytebytego"
    subject: str
    sender: str
    date_str: str
    body_text: str
    summary_excerpt: str = ""
    links: list[str] = field(default_factory=list)
    raw_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "subject": self.subject,
            "sender": self.sender,
            "date_str": self.date_str,
            "summary_excerpt": self.summary_excerpt,
            "body_text": self.body_text[:1000],  # truncated preview for logs
            "links": self.links[:10],
            "raw_id": self.raw_id,
        }


def _extract_text_and_links_from_part(part: dict) -> tuple[str, list[str]]:
    """Recursively extract plain text and hyperlink URLs from MIME parts."""
    text_content = ""
    links: list[str] = []

    mime_type = part.get("mimeType", "")
    body = part.get("body", {})
    data = body.get("data")

    if data:
        try:
            decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            if "html" in mime_type.lower():
                soup = BeautifulSoup(decoded, "html.parser")
                # Extract all valid links
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if href.startswith("http://") or href.startswith("https://"):
                        links.append(href)
                text_content += "\n" + soup.get_text(separator="\n", strip=True)
            else:
                text_content += "\n" + decoded
                # Also find raw urls in plain text
                raw_urls = re.findall(r"https?://[^\s<>\"']+", decoded)
                links.extend(raw_urls)
        except Exception as err:
            print(f"[GmailReader] Warning decoding part ({mime_type}): {err}")

    # Process nested subparts (e.g. multipart/alternative, multipart/mixed)
    for subpart in part.get("parts", []):
        sub_text, sub_links = _extract_text_and_links_from_part(subpart)
        text_content += "\n" + sub_text
        links.extend(sub_links)

    # Deduplicate links preserving order
    seen: set[str] = set()
    deduped_links: list[str] = []
    for link in links:
        if link not in seen:
            seen.add(link)
            deduped_links.append(link)

    return text_content.strip(), deduped_links


def extract_summary_block(text: str) -> str:
    """Extract '=== EMAIL SUMMARY ===' block if present in gmail-agent forwards."""
    if "=== EMAIL SUMMARY ===" in text:
        start_idx = text.find("=== EMAIL SUMMARY ===")
        # Look for the separator line closing the summary
        closing_match = re.search(r"={10,}", text[start_idx + 22 :])
        if closing_match:
            end_idx = start_idx + 22 + closing_match.end()
            return text[start_idx:end_idx].strip()
        # Fallback: take first 1500 chars after the header
        return text[start_idx : start_idx + 1500].strip()
    return ""


class GmailReader:
    """Interface to search, retrieve, and parse Gmail inbox messages."""

    def __init__(self, creds: Any) -> None:
        self.service = build("gmail", "v1", credentials=creds)

    def _execute_query(self, query: str, max_results: int = 25) -> list[str]:
        """Execute a Gmail query and return list of matching message IDs."""
        try:
            results = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )
            messages = results.get("messages", [])
            return [m["id"] for m in messages if "id" in m]
        except HttpError as error:
            print(f"[GmailReader] HttpError running query '{query}': {error}")
            return []

    def fetch_message_details(self, msg_id: str, source_type: str) -> EmailDigest | None:
        """Fetch full details and parse plain text from a message ID."""
        try:
            msg = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )

            payload = msg.get("payload", {})
            headers = payload.get("headers", [])

            subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "No Subject")
            sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown Sender")
            date_str = next((h["value"] for h in headers if h["name"].lower() == "date"), "")

            # Extract body text and hyperlinks
            body_text, links = _extract_text_and_links_from_part(payload)

            # Specific summary excerpt extraction for gmail-agent
            summary_excerpt = ""
            if source_type == "email_summary" or "=== EMAIL SUMMARY ===" in body_text:
                summary_excerpt = extract_summary_block(body_text)

            # If no summary excerpt but it's another digest, provide first 500 chars
            if not summary_excerpt and body_text:
                summary_excerpt = body_text[:600]

            return EmailDigest(
                source_type=source_type,
                subject=subject,
                sender=sender,
                date_str=date_str,
                body_text=body_text,
                summary_excerpt=summary_excerpt,
                links=links,
                raw_id=msg_id,
            )
        except HttpError as error:
            print(f"[GmailReader] Error fetching message ID {msg_id}: {error}")
            return None

    def fetch_weekly_digests(self, days: int = 7) -> list[EmailDigest]:
        """Fetch all relevant digest emails from the past N days across the 4 sources."""
        print(f"[GmailReader] Searching inbox for digests from the past {days} days...")

        queries = [
            # 1. gmail-agent email summaries
            ("email_summary", f'("=== EMAIL SUMMARY ===" OR (from:me subject:Fwd:)) newer_than:{days}d'),
            # 2. Daily AI News Digest: Korea & Japan
            ("ai_news", f'subject:"Daily AI News Digest" newer_than:{days}d'),
            # 3. YouTube Intelligence Digest
            ("youtube_digest", f'subject:"YouTube Intelligence Digest" newer_than:{days}d'),
            # 4. ByteByteGo Substack newsletter
            ("bytebytego", f'from:bytebytego@substack.com newer_than:{days}d'),
        ]

        seen_msg_ids: set[str] = set()
        digests: list[EmailDigest] = []

        for source_type, query in queries:
            print(f"[GmailReader] Executing query for {source_type}: {query}")
            msg_ids = self._execute_query(query)
            print(f"[GmailReader] Found {len(msg_ids)} message(s) for {source_type}")

            for msg_id in msg_ids:
                if msg_id in seen_msg_ids:
                    continue
                seen_msg_ids.add(msg_id)

                digest = self.fetch_message_details(msg_id, source_type)
                if digest and digest.body_text.strip():
                    # For email_summary, ensure either marker or Fwd: subject is verified
                    if source_type == "email_summary":
                        if "=== EMAIL SUMMARY ===" not in digest.body_text and not digest.subject.startswith("Fwd:"):
                            continue
                    digests.append(digest)

        print(f"[GmailReader] Successfully collected {len(digests)} total email digests.")
        return digests
