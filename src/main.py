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

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.auth import authenticate_gmail
from src.config import RECIPIENT_NAME, TIMEZONE
from src.email_sender import EmailSender
from src.gmail_reader import GmailReader
from src.linkedin_scraper import LinkedInScraper
from src.post_drafter import PostDrafter
from src.profile_memory import ProfileMemoryManager
from src.run_logger import RunLogger


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
    print("============================================================")
    print(f"[START] LinkedIn Post Ghostwriter Pipeline ({date_str})")
    print(f"Mode: {'DRY RUN (preview only)' if dry_run else 'LIVE EXECUTION'}")
    print(f"Lookback Window: {days} days")
    print("============================================================")

    memory_mgr = ProfileMemoryManager()
    memory = memory_mgr.load_memory()
    run_logger = RunLogger()

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

        # Step 3: Fetch LinkedIn Profile and Authentic Activity
        print("\n[Step 3/6] Fetching LinkedIn profile data and recent activity...")
        scraper = LinkedInScraper()
        profile_data = scraper.scrape_profile(fallback_memory=memory)
        print(
            f"[Step 3/6] Profile status: {profile_data.scrape_status}, "
            f"Name: {profile_data.name}, "
            f"Actual Posts: {len(profile_data.actual_posts)}, "
            f"Activities: {len(profile_data.recent_activity)}"
        )

        # Step 4: Gemini Topic Selection & Post Drafting
        print("\n[Step 4/6] Synthesizing topic and drafting post with Gemini...")
        recent_posted_topics = memory_mgr.get_recent_topics(memory, limit=8)
        recently_suggested_topics = run_logger.get_recently_suggested_topics(limit=8)

        drafter = PostDrafter()
        draft_result = drafter.draft_post(
            digests=digests,
            profile_data=profile_data.to_dict(),
            recent_topics=recent_posted_topics,
            topic_blacklist=memory.get("topic_blacklist", []),
            suggested_topics=recently_suggested_topics,
        )

        topic = draft_result.get("topic", "Weekly AI Insight")
        print(f"[Step 4/6] Draft generated! Topic: '{topic}'")

        # Step 5: Dispatch Review Email or Print Preview
        print("\n[Step 5/6] Delivering post draft...")
        email_result = None
        if dry_run:
            print("\n" + "=" * 60)
            print("[DRY RUN PREVIEW] LinkedIn Post Draft:")
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
                recent_topics=recent_posted_topics,
                profile_name=profile_data.name,
            )
            print("[Step 5/6] Draft review email successfully sent to Gmail.")

        # Step 6: Update Profile Memory & Record Run
        print("\n[Step 6/6] Updating profile memory and recording run log...")
        if not dry_run:
            # Update profile memory with actual LinkedIn data (no drafts added)
            memory_mgr.update_from_linkedin(memory, profile_data)
            memory_mgr.save_memory(memory)
            print("[Step 6/6] Profile memory updated in Google Cloud Storage.")

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            run_logger.record_run(
                status="success",
                topic_suggested=topic,
                stats=digest_stats,
                elapsed_seconds=elapsed,
            )
            print("[Step 6/6] Execution log and suggested topic recorded in GCS run log.")
        else:
            print("[Step 6/6] Dry run: skipped updating cloud memory and run log.")

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        print(f"\n[SUCCESS] Pipeline completed successfully in {elapsed:.1f}s.")
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
        print(f"\n[FAILED] Pipeline failed after {elapsed:.1f}s: {err_msg}")
        traceback.print_exc()

        if not dry_run:
            try:
                run_logger.record_run(
                    status="failed",
                    topic_suggested=None,
                    stats={},
                    elapsed_seconds=elapsed,
                    error=err_msg,
                )
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
