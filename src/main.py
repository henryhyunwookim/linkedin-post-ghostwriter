"""
LinkedIn Post Ghostwriter - Main Orchestration Pipeline.

Purpose:
    Coordinates the weekly ghostwriting workflow:
      1. Loads profile memory from Google Cloud Storage / local JSON
      2. Authenticates with Gmail API via OAuth 2.0 / Secret Manager
      3. Reads past week's email digests across 4 key sources
      4. Scrapes user's LinkedIn profile (with graceful fallback)
      5. Generates concise AI thought post + sources with Gemini LLM
      6. Transmits draft review email to user's Gmail
      7. Updates and persists profile memory on GCS
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime, timezone
from typing import Any

from src.auth import authenticate_gmail
from src.config import RECIPIENT_NAME, TIMEZONE
from src.email_sender import EmailSender
from src.gmail_reader import GmailReader
from src.linkedin_scraper import LinkedInScraper
from src.post_drafter import PostDrafter
from src.profile_memory import ProfileMemoryManager


def run_pipeline(dry_run: bool = False, days: int = 7) -> dict[str, Any]:
    """Executes the complete LinkedIn ghostwriter pipeline.

    Args:
        dry_run: If True, skips sending email and saving to GCS, printing draft to console.
        days: Lookback window in days for reading emails (default: 7).

    Returns:
        dict: Execution summary with status, stats, and metadata.
    """
    start_time = datetime.now(timezone.utc)
    date_str = start_time.strftime("%B %d, %Y")
    print(f"============================================================")
    print(f"🚀 Starting LinkedIn Post Ghostwriter Pipeline ({date_str})")
    print(f"Mode: {'DRY RUN (preview only)' if dry_run else 'LIVE EXECUTION'}")
    print(f"Lookback Window: {days} days")
    print(f"============================================================")

    memory_mgr = ProfileMemoryManager()
    memory = memory_mgr.load_memory()

    try:
        # Step 1: Authenticate Gmail
        print("\n[Step 1/6] Authenticating with Gmail API...")
        creds = authenticate_gmail()
        print("[Step 1/6] Gmail authentication successful.")

        # Step 2: Read Weekly Inbox Digests
        print(f"\n[Step 2/6] Reading Gmail digests from past {days} days...")
        reader = GmailReader(creds)
        digests = reader.fetch_weekly_digests(days=days)

        digest_stats: dict[str, int] = {
            "email_summary": sum(1 for d in digests if d.source_type == "email_summary"),
            "ai_news": sum(1 for d in digests if d.source_type == "ai_news"),
            "youtube_digest": sum(1 for d in digests if d.source_type == "youtube_digest"),
            "bytebytego": sum(1 for d in digests if d.source_type == "bytebytego"),
        }
        print(f"[Step 2/6] Digests parsed: {digest_stats}")

        # Step 3: Scrape LinkedIn Profile
        print("\n[Step 3/6] Fetching LinkedIn profile data...")
        scraper = LinkedInScraper()
        profile_data = scraper.scrape_profile(fallback_memory=memory)
        print(f"[Step 3/6] Profile status: {profile_data.scrape_status}, Name: {profile_data.name}")

        # Step 4: Gemini Topic Selection & Post Drafting
        print("\n[Step 4/6] Synthesizing topic and drafting post with Gemini...")
        recent_topics = memory_mgr.get_recent_topics(memory, limit=8)
        drafter = PostDrafter()
        draft_result = drafter.draft_post(
            digests=digests,
            profile_data=profile_data.to_dict(),
            recent_topics=recent_topics,
            topic_blacklist=memory.get("topic_blacklist", []),
        )

        topic = draft_result.get("topic", "Weekly AI Insight")
        print(f"[Step 4/6] Draft generated! Topic: '{topic}'")

        # Step 5: Dispatch Review Email or Print Preview
        print("\n[Step 5/6] Delivering post draft...")
        email_result = None
        if dry_run:
            print("\n" + "=" * 60)
            print("📝 [DRY RUN PREVIEW] LinkedIn Post Draft:")
            print("=" * 60)
            print(f"Topic: {topic}")
            print(f"Rationale: {draft_result.get('rationale')}\n")
            print("--- POST CONTENT ---")
            print(draft_result.get("post_text"))
            print("\n--- HASHTAGS ---")
            print(" ".join(draft_result.get("hashtags", [])))
            print("\n--- SOURCES USED ---")
            for s in draft_result.get("sources_used", []):
                print(f" - {s.get('title')}: {s.get('url')}")
            print("=" * 60 + "\n")
        else:
            sender = EmailSender(creds)
            email_result = sender.send_draft_email(
                draft_result=draft_result,
                date_str=date_str,
                digest_stats=digest_stats,
                recent_topics=recent_topics,
                profile_name=profile_data.name,
            )
            print("[Step 5/6] Draft review email successfully sent to Gmail.")

        # Step 6: Update & Persist Profile Memory
        print("\n[Step 6/6] Updating profile memory...")
        if not dry_run:
            memory_mgr.record_run(
                memory=memory,
                draft_result=draft_result,
                status="success",
                profile_update=profile_data.to_dict() if profile_data.scrape_status == "success" else None,
            )
            memory_mgr.save_memory(memory)
            print("[Step 6/6] Profile memory updated and saved.")
        else:
            print("[Step 6/6] Dry run: skipped saving updated memory.")

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        print(f"\n✅ Pipeline completed successfully in {elapsed:.1f}s.")
        return {
            "success": True,
            "topic": topic,
            "stats": digest_stats,
            "dry_run": dry_run,
            "elapsed_seconds": elapsed,
            "error": None,
        }

    except Exception as err:
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        err_msg = f"{type(err).__name__}: {str(err)}"
        print(f"\n❌ Pipeline failed after {elapsed:.1f}s: {err_msg}")
        traceback.print_exc()

        # Log failed run in memory
        try:
            memory_mgr.record_run(memory=memory, draft_result=None, status=f"failed: {err_msg}")
            memory_mgr.save_memory(memory)
        except Exception:
            pass

        return {
            "success": False,
            "topic": None,
            "stats": {},
            "dry_run": dry_run,
            "elapsed_seconds": elapsed,
            "error": err_msg,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LinkedIn Post Ghostwriter CLI")
    parser.add_argument("--dry-run", action="store_true", help="Generate preview without sending email or saving memory")
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days for reading emails (default: 7)")
    parser.add_argument("--auth", action="store_true", help="Run interactive Gmail authentication tool and exit")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.auth:
        authenticate_gmail(force_interactive=True)
        sys.exit(0)

    result = run_pipeline(dry_run=args.dry_run, days=args.days)
    sys.exit(0 if result["success"] else 1)
