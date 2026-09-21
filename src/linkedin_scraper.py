"""
LinkedIn Post Ghostwriter - LinkedIn Profile Scraper Module.

Purpose:
    Retrieves publicly visible information from the user's LinkedIn profile
    (headline, about summary, experience highlights, recent public activity).
    
    Implements graceful fallback: LinkedIn aggressively blocks unauthenticated
    scrapers with login walls (HTTP 999 or redirect to login). If scraping is
    blocked, the system falls back to stored profile memory so the pipeline
    never halts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import requests
from bs4 import BeautifulSoup

from src.config import LINKEDIN_LI_AT, LINKEDIN_PROFILE_URL


@dataclass
class LinkedInProfileData:
    """Structured representation of LinkedIn profile information and authentic activity."""

    name: str = "Author"
    headline: str = "AI & Cloud Solutions Architect"
    about: str = (
        "Focusing on AI system innovation, cloud architecture, and engineering."
    )
    experience_highlights: list[str] = field(default_factory=list)
    actual_posts: list[dict[str, Any]] = field(default_factory=list)
    recent_activity: list[str] = field(default_factory=list)
    scrape_status: str = "fallback"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "headline": self.headline,
            "about": self.about,
            "experience_highlights": self.experience_highlights,
            "actual_posts": self.actual_posts,
            "recent_activity": self.recent_activity,
            "scrape_status": self.scrape_status,
        }


class LinkedInScraper:
    """Scrapes public LinkedIn profile and activity with resilient fallback."""

    def __init__(
        self,
        profile_url: str = LINKEDIN_PROFILE_URL,
        li_at: str | None = LINKEDIN_LI_AT,
    ) -> None:
        self.profile_url = profile_url
        self.li_at = li_at
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9,ja;q=0.8,ko;q=0.7",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

    def scrape_profile(
        self, fallback_memory: dict[str, Any] | None = None
    ) -> LinkedInProfileData:
        """Attempts to scrape profile and actual activity, falling back to cloud memory if blocked."""
        print(f"[LinkedInScraper] Checking LinkedIn profile and activity: {self.profile_url}")

        fallback_profile = (
            fallback_memory.get("profile", {}) if fallback_memory else {}
        )

        default_data = LinkedInProfileData(
            name=fallback_profile.get("name", os.getenv("RECIPIENT_NAME", "Author")),
            headline=fallback_profile.get(
                "headline",
                "AI & Cloud Solutions Architect",
            ),
            about=fallback_profile.get(
                "about",
                "Specializing in AI system architectures, serverless deployments, and cloud engineering.",
            ),
            experience_highlights=fallback_profile.get("expertise_areas", []),
            actual_posts=fallback_memory.get("post_history", []) if fallback_memory else [],
            recent_activity=fallback_memory.get("recent_activities", []) if fallback_memory else [],
            scrape_status="fallback",
        )

        cookies = {}
        if self.li_at:
            cookies["li_at"] = self.li_at

        try:
            response = requests.get(
                self.profile_url,
                headers=self.headers,
                cookies=cookies if cookies else None,
                timeout=12,
                allow_redirects=True,
            )

            # Check if LinkedIn redirected to login or returned authwall code
            if response.status_code in (401, 403, 999) or "login" in response.url.lower():
                print(
                    f"[LinkedInScraper] LinkedIn authwall encountered (Status: {response.status_code}). "
                    "Using verified actual posts and activity from cloud profile memory."
                )
                return default_data

            if response.status_code != 200:
                print(
                    f"[LinkedInScraper] Unexpected HTTP response {response.status_code}. "
                    "Using verified cloud profile memory baseline."
                )
                return default_data

            soup = BeautifulSoup(response.text, "html.parser")

            # Try OpenGraph tags first
            og_title = soup.find("meta", property="og:title")
            og_desc = soup.find("meta", property="og:description")

            name = default_data.name
            headline = default_data.headline
            about = default_data.about

            if og_title and og_title.get("content"):
                title_text = og_title["content"].strip()
                if " - " in title_text:
                    parts = title_text.split(" - ", 1)
                    name = parts[0].strip()
                    headline = parts[1].replace("| LinkedIn", "").strip()

            if og_desc and og_desc.get("content"):
                about = og_desc["content"].strip()

            h1 = soup.find("h1")
            if h1 and h1.get_text(strip=True):
                name = h1.get_text(strip=True)

            headline_tag = soup.find("div", class_=re.compile(r"headline|text-body-medium", re.I))
            if headline_tag and headline_tag.get_text(strip=True):
                headline = headline_tag.get_text(strip=True)

            about_tag = soup.find("section", id=re.compile(r"about", re.I))
            if about_tag:
                about_text = about_tag.get_text(separator=" ", strip=True)
                if len(about_text) > 30:
                    about = about_text

            # Parse actual posts and activities
            scraped_posts: list[dict[str, Any]] = []
            scraped_activity: list[str] = []

            activity_section = soup.find("section", id=re.compile(r"activity|posts|feed", re.I))
            if activity_section:
                for item in activity_section.find_all(["li", "div"], class_=re.compile(r"post|update|activity", re.I)):
                    text = item.get_text(separator=" ", strip=True)
                    if len(text) > 40 and not any(text in p.get("post_text", "") for p in scraped_posts):
                        scraped_posts.append({
                            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                            "post_text": text[:600],
                            "topic": text[:80] + "...",
                        })
                        scraped_activity.append(text[:250])

            # Merge with default fallback posts/activities if scraped had fewer items
            final_posts = scraped_posts if scraped_posts else default_data.actual_posts
            final_activity = scraped_activity if scraped_activity else default_data.recent_activity

            print("[LinkedInScraper] Successfully extracted profile elements from LinkedIn.")
            return LinkedInProfileData(
                name=name,
                headline=headline,
                about=about,
                experience_highlights=default_data.experience_highlights,
                actual_posts=final_posts,
                recent_activity=final_activity,
                scrape_status="success",
            )

        except Exception as exc:
            print(f"[LinkedInScraper] Scraping attempt error: {exc}. Proceeding with cloud memory fallback.")
            return default_data
