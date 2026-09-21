"""
LinkedIn Post Ghostwriter - Email Generation & Delivery Module.

Purpose:
    Constructs a responsive, elegant HTML review email containing the draft
    LinkedIn post, topic rationale, source references, and weekly ingestion stats.
    Transmits the email to the user's Gmail address via Gmail API OAuth2.
"""

from __future__ import annotations

import base64
import html
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.auth import authenticate_gmail
from src.config import RECIPIENT_EMAIL, RECIPIENT_NAME


class EmailSender:
    """Handles HTML email construction and Gmail API delivery for LinkedIn drafts."""

    def __init__(self, creds: Credentials | None = None) -> None:
        self.creds: Credentials = creds or authenticate_gmail()
        self.service = build("gmail", "v1", credentials=self.creds)

    def build_html_draft_email(
        self,
        draft_result: dict[str, Any],
        date_str: str,
        digest_stats: dict[str, int],
        recent_topics: list[str],
        profile_name: str = "Author",
    ) -> str:
        """Constructs an executive-quality HTML review email."""
        topic = html.escape(draft_result.get("topic", "Weekly AI Insight"))
        rationale = html.escape(draft_result.get("rationale", ""))
        post_text = draft_result.get("post_text", "")
        # Format post text with clean paragraphs
        post_paragraphs = [
            f"<p style='margin: 0 0 12px 0; line-height: 1.65; color: #1e293b;'>{html.escape(p)}</p>"
            for p in post_text.split("\n\n")
            if p.strip()
        ]
        post_html = "\n".join(post_paragraphs)

        # Sources HTML
        sources = draft_result.get("sources_used", [])
        if sources:
            sources_items = []
            for s in sources:
                title = html.escape(s.get("title", "Source"))
                url = s.get("url", "")
                if url:
                    sources_items.append(
                        f"<li style='margin-bottom: 6px;'><a href='{html.escape(url)}' target='_blank' style='color: #0a66c2; text-decoration: underline;'>{title}</a></li>"
                    )
                else:
                    sources_items.append(f"<li style='margin-bottom: 6px; color: #475569;'>{title}</li>")
            sources_html = f"<ul style='margin: 0; padding-left: 20px; font-size: 13px; line-height: 1.5;'>{''.join(sources_items)}</ul>"
        else:
            sources_html = "<p style='margin: 0; font-size: 13px; color: #64748b;'>Weekly email digest synthesis.</p>"

        # Hashtags HTML
        hashtags = draft_result.get("hashtags", [])
        hashtags_html = " ".join(
            f"<span style='background: #e0f2fe; color: #0369a1; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; margin-right: 6px; display: inline-block;'>{html.escape(t)}</span>"
            for t in hashtags
        )

        # Ingestion stats pills
        stats_html = f"""
        <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
            <tr>
                <td style="padding: 6px; text-align: center; background: #f8fafc; border-radius: 6px; border: 1px solid #e2e8f0;">
                    <div style="font-size: 16px; font-weight: 700; color: #0284c7;">{digest_stats.get('email_summary', 0)}</div>
                    <div style="font-size: 10.5px; color: #64748b; text-transform: uppercase;">Agent Summaries</div>
                </td>
                <td style="width: 8px;"></td>
                <td style="padding: 6px; text-align: center; background: #f8fafc; border-radius: 6px; border: 1px solid #e2e8f0;">
                    <div style="font-size: 16px; font-weight: 700; color: #10b981;">{digest_stats.get('ai_news', 0)}</div>
                    <div style="font-size: 10.5px; color: #64748b; text-transform: uppercase;">AI News KR/JP</div>
                </td>
                <td style="width: 8px;"></td>
                <td style="padding: 6px; text-align: center; background: #f8fafc; border-radius: 6px; border: 1px solid #e2e8f0;">
                    <div style="font-size: 16px; font-weight: 700; color: #f59e0b;">{digest_stats.get('youtube_digest', 0)}</div>
                    <div style="font-size: 10.5px; color: #64748b; text-transform: uppercase;">YouTube Insights</div>
                </td>
                <td style="width: 8px;"></td>
                <td style="padding: 6px; text-align: center; background: #f8fafc; border-radius: 6px; border: 1px solid #e2e8f0;">
                    <div style="font-size: 16px; font-weight: 700; color: #6366f1;">{digest_stats.get('bytebytego', 0)}</div>
                    <div style="font-size: 10.5px; color: #64748b; text-transform: uppercase;">ByteByteGo</div>
                </td>
            </tr>
        </table>
        """

        # Recent topics list
        recent_topics_html = ""
        if recent_topics:
            recent_items = [
                f"<li style='margin-bottom: 4px; color: #64748b;'>{html.escape(t)}</li>"
                for t in recent_topics[-5:]
            ]
            recent_topics_html = f"""
            <div style="margin-top: 16px; padding: 12px; background-color: #f8fafc; border-radius: 8px; border: 1px solid #e2e8f0;">
                <span style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748b; letter-spacing: 0.05em; display: block; margin-bottom: 6px;">
                    Recent Topics Avoided (Post History):
                </span>
                <ul style="margin: 0; padding-left: 18px; font-size: 12px; line-height: 1.4;">
                    {''.join(recent_items)}
                </ul>
            </div>
            """

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LinkedIn Post Draft</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
</head>
<body style="margin: 0; padding: 24px 12px; background-color: #f1f5f9; font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
    <div style="max-width: 680px; margin: 0 auto;">
        
        <!-- Header Banner -->
        <div style="background: linear-gradient(135deg, #0a66c2 0%, #004182 100%); border-radius: 14px; padding: 26px 24px; color: #ffffff; margin-bottom: 20px; box-shadow: 0 4px 14px rgba(10, 102, 194, 0.2);">
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td>
                        <span style="background-color: rgba(255,255,255,0.2); color: #ffffff; padding: 3px 10px; border-radius: 9999px; font-size: 11px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;">
                            WEEKLY REVIEW • FRIDAY 9PM JST
                        </span>
                        <h1 style="margin: 10px 0 4px 0; font-size: 23px; font-weight: 800; letter-spacing: -0.02em;">LinkedIn Post Ghostwriter</h1>
                        <p style="margin: 0; color: #bfdbfe; font-size: 13.5px;">Week of {date_str} • Curated for <strong>{profile_name}</strong></p>
                    </td>
                    <td style="text-align: right; vertical-align: middle;">
                        <div style="background-color: rgba(255,255,255,0.15); border-radius: 10px; padding: 10px 14px; display: inline-block; text-align: center;">
                            <div style="font-size: 22px;">✍️</div>
                            <div style="font-size: 10px; color: #ffffff; text-transform: uppercase; font-weight: 700; margin-top: 2px;">Draft Ready</div>
                        </div>
                    </td>
                </tr>
            </table>
        </div>

        <!-- Topic & Rationale Card -->
        <div style="background-color: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 18px 20px; margin-bottom: 20px; box-shadow: 0 2px 6px rgba(0,0,0,0.02);">
            <span style="font-size: 11px; text-transform: uppercase; font-weight: 700; color: #0a66c2; letter-spacing: 0.05em; display: block; margin-bottom: 4px;">
                Selected Topic
            </span>
            <h2 style="margin: 0 0 8px 0; font-size: 18px; color: #0f172a; font-weight: 700;">
                {topic}
            </h2>
            <p style="margin: 0; font-size: 13.5px; line-height: 1.55; color: #475569;">
                <strong>Strategic Rationale:</strong> {rationale}
            </p>
        </div>

        <!-- Draft Post Container (Copy-Ready Box) -->
        <div style="background-color: #ffffff; border-radius: 12px; border: 2px solid #0a66c2; padding: 22px 24px; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(10, 102, 194, 0.08);">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; border-bottom: 1px solid #f1f5f9; padding-bottom: 12px;">
                <span style="font-size: 12px; font-weight: 700; color: #0a66c2; text-transform: uppercase; letter-spacing: 0.04em;">
                    📋 Ready-to-Publish LinkedIn Post
                </span>
                <span style="font-size: 11.5px; color: #64748b;">Copy & paste directly into LinkedIn</span>
            </div>

            <!-- Post Text Content -->
            <div style="font-size: 14.5px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
                {post_html}
            </div>

            <!-- Hashtags -->
            <div style="margin-top: 16px; padding-top: 14px; border-top: 1px solid #f1f5f9;">
                {hashtags_html}
            </div>
        </div>

        <!-- Sources Referenced Card -->
        <div style="background-color: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 18px 20px; margin-bottom: 20px;">
            <span style="font-size: 11px; text-transform: uppercase; font-weight: 700; color: #0f172a; letter-spacing: 0.05em; display: block; margin-bottom: 8px;">
                🔗 Sources Referenced in Draft
            </span>
            {sources_html}
        </div>

        <!-- Ingestion Stats Card -->
        <div style="background-color: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 18px 20px; margin-bottom: 20px;">
            <span style="font-size: 11px; text-transform: uppercase; font-weight: 700; color: #0f172a; letter-spacing: 0.05em; display: block; margin-bottom: 4px;">
                📊 Weekly Digest Inputs Analyzed
            </span>
            {stats_html}
            {recent_topics_html}
        </div>

        <!-- Footer -->
        <div style="text-align: center; padding: 16px; color: #94a3b8; font-size: 12px; line-height: 1.5;">
            <p style="margin: 0 0 4px 0;">Generated by <strong>LinkedIn Post Ghostwriter</strong> • Running on Google Cloud Run</p>
            <p style="margin: 0;">Recipient: <strong>{RECIPIENT_NAME}</strong> ({RECIPIENT_EMAIL})</p>
        </div>

    </div>
</body>
</html>
"""

    def send_draft_email(
        self,
        draft_result: dict[str, Any],
        date_str: str,
        digest_stats: dict[str, int],
        recent_topics: list[str],
        profile_name: str = "Author",
    ) -> dict[str, Any]:
        """Dispatches the draft review email to the user's Gmail address."""
        if not RECIPIENT_EMAIL:
            raise ValueError(
                "Recipient email is required to dispatch LinkedIn draft. "
                "Please ensure active gcloud account is set or specify RECIPIENT_EMAIL."
            )

        topic = draft_result.get("topic", "AI Insight")
        html_body = self.build_html_draft_email(
            draft_result=draft_result,
            date_str=date_str,
            digest_stats=digest_stats,
            recent_topics=recent_topics,
            profile_name=profile_name,
        )

        message = MIMEMultipart("alternative")
        message["Subject"] = f"[LinkedIn Draft] {topic} — Week of {date_str}"
        message["To"] = RECIPIENT_EMAIL

        # Plain text fallback
        plain_text = f"""LinkedIn Post Draft - Week of {date_str}
======================================================
Topic: {topic}
Rationale: {draft_result.get('rationale', '')}

--- DRAFT POST (Ready to copy) ---
{draft_result.get('post_text', '')}

--- HASHTAGS ---
{' '.join(draft_result.get('hashtags', []))}

--- SOURCES REFERENCED ---
"""
        for s in draft_result.get("sources_used", []):
            plain_text += f"- {s.get('title')}: {s.get('url', '')}\n"

        plain_text += f"\nDigest Inputs Analyzed: {digest_stats}\n"
        plain_text += "Sent automatically by LinkedIn Post Ghostwriter.\n"

        message.attach(MIMEText(plain_text, "plain", "utf-8"))
        message.attach(MIMEText(html_body, "html", "utf-8"))

        raw_email = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        body = {"raw": raw_email}

        try:
            result = self.service.users().messages().send(userId="me", body=body).execute()
            print(f"[EmailSender] LinkedIn draft email sent successfully! Message ID: {result.get('id')}")
            return result
        except HttpError as error:
            print(f"[EmailSender] Gmail API dispatch error: {error}")
            raise error
