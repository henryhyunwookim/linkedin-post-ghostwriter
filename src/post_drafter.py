"""
LinkedIn Post Ghostwriter - Gemini Post Drafter Module.

Purpose:
    Synthesizes gathered email digests and LinkedIn profile memory into a concise,
    high-impact LinkedIn post using Google Gemini LLM.
    
    Adheres strictly to user requirements:
      - Concise thought on recent activities in the AI field relevant to user's work
        (AI systems, cloud architecture, international development / ODA, digital capacity).
      - Sources section at the bottom citing the specific articles/digests used.
      - English only.
      - Avoids topics recently posted in post_history.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any
import google.generativeai as genai

from src.config import GEMINI_API_KEY, GEMINI_MODEL
from src.gmail_reader import EmailDigest


class PostDrafter:
    """Orchestrates topic selection and drafting of LinkedIn posts via Gemini."""

    def __init__(self, api_key: str | None = None, model_name: str | None = None) -> None:
        self.api_key = api_key or GEMINI_API_KEY
        if not self.api_key:
            raise ValueError(
                "Gemini API key is required. Set GEMINI_API_KEY in .env or pass it to PostDrafter."
            )
        self.model_name = model_name or GEMINI_MODEL
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(
            self.model_name,
            generation_config={"response_mime_type": "application/json"},
        )

    def _prepare_digests_summary(self, digests: list[EmailDigest]) -> str:
        """Compress email digests into a clean, structured context block."""
        if not digests:
            return "No new email digests found for the past week."

        blocks = []
        for i, d in enumerate(digests, 1):
            excerpt = d.summary_excerpt if d.summary_excerpt else d.body_text[:1200]
            links_str = "\n  - " + "\n  - ".join(d.links[:5]) if d.links else " None"
            blocks.append(
                f"### Digest #{i} [{d.source_type.upper()}]\n"
                f"- **Subject**: {d.subject}\n"
                f"- **Sender**: {d.sender}\n"
                f"- **Date**: {d.date_str}\n"
                f"- **Content / Key Excerpt**:\n{excerpt}\n"
                f"- **Key Links**:{links_str}"
            )
        return "\n\n".join(blocks)

    def draft_post(
        self,
        digests: list[EmailDigest],
        profile_data: dict[str, Any],
        recent_topics: list[str],
        topic_blacklist: list[str] | None = None,
    ) -> dict[str, Any]:
        """Runs the topic selection and drafting pipeline via Gemini."""
        digests_text = self._prepare_digests_summary(digests)
        blacklist = topic_blacklist or []

        prompt = f"""You are an elite ghostwriter crafting a LinkedIn post for Henry Hyunwoo Kim.

### Author Profile & Tone:
- **Name**: {profile_data.get('name', 'Henry Hyunwoo Kim')}
- **Headline**: {profile_data.get('headline', 'AI & Cloud Solutions Architect | Digital Transformation & ODA')}
- **Background**: {profile_data.get('about', 'Specializes in AI architectures, serverless, and digital transformation in APAC')}
- **Expertise Areas**: {', '.join(profile_data.get('expertise_areas', ['Generative AI', 'Cloud', 'Digital ODA']))}

### Constraints & Requirements:
1. **Topic Selection**:
   - Pick the single most compelling and timely topic from the weekly digests below.
   - Relevance: Must directly connect to recent AI developments, architectural innovations, or practical implementation (especially relevant to enterprise AI, cloud scaling, or digital capacity).
   - AVOID these topics posted recently: {recent_topics if recent_topics else 'None yet'}
   - STRICTLY AVOID blacklisted themes: {blacklist}

2. **Post Format & Style (CRITICAL)**:
   - **Language**: English only.
   - **Length**: Concise thought. No unnecessary fluff, corporate jargon, or buzzword soup. Keep the main thought crisp, dense, and insight-driven (approx. 800 - 1,200 characters total).
   - **Structure**:
     * **Opening Hook**: A single punchy, curiosity-piquing line that immediately engages technical leaders.
     * **Core Thought**: 2 to 3 short paragraphs synthesizing the technical shift or practical implication. Connect what happened to why it matters for engineering/delivery.
     * **Engagement Question**: 1 thoughtful closing question that prompts genuine peer discussion.
     * **Sources Section**: At the bottom of the post text, include a clean 'Sources:' section listing the relevant articles or digests referenced.
     * **Hashtags**: Exactly 3 to 5 targeted hashtags (e.g. #ArtificialIntelligence #CloudArchitecture #SystemDesign #DigitalTransformation).

### Weekly Digest Material:
{digests_text}

### Output JSON Schema:
Return ONLY a valid JSON object matching this schema:
{{
  "topic": "Concise topic title",
  "rationale": "1-2 sentences explaining why this topic was chosen based on the week's inputs",
  "post_text": "Complete, ready-to-publish LinkedIn post text including the hook, body paragraphs, closing question, Sources section, and hashtags at the bottom.",
  "sources_used": [
    {{"title": "Source name or article title", "url": "URL if available"}}
  ],
  "hashtags": ["#tag1", "#tag2", "#tag3"]
}}
"""

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                print(f"[PostDrafter] Calling Gemini ({self.model_name}) to draft post (attempt {attempt})...")
                response = self.model.generate_content(prompt)
                raw_text = response.text.strip()

                # Clean markdown fencing if present
                clean_json = re.sub(r"^```json\s*", "", raw_text, flags=re.MULTILINE)
                clean_json = re.sub(r"\s*```$", "", clean_json, flags=re.MULTILINE).strip()

                result = json.loads(clean_json)

                # Ensure post_text contains Sources section if not already present
                sources = result.get("sources_used", [])
                post_text = result.get("post_text", "")
                if "Sources:" not in post_text and sources:
                    sources_str = "\n\nSources:\n" + "\n".join(
                        f"- {s.get('title', 'Reference')}: {s.get('url', '')}".strip(" :")
                        for s in sources
                    )
                    # Insert before hashtags or append
                    post_text = post_text.strip() + sources_str
                    result["post_text"] = post_text

                print(f"[PostDrafter] Successfully generated draft for topic: {result.get('topic')}")
                return result

            except Exception as exc:
                print(f"[PostDrafter] Attempt {attempt}/{max_retries} failed: {exc}")
                if attempt < max_retries:
                    time.sleep(2 * attempt)
                else:
                    # Fallback default draft if Gemini fails completely
                    return {
                        "topic": "Recent Advancements in AI Engineering & Systems",
                        "rationale": "Automated fallback draft due to generation error.",
                        "post_text": (
                            "AI systems are shifting rapidly from standalone models to composite agentic architectures.\n\n"
                            "Observing the past week's developments in AI infrastructure and enterprise deployment, "
                            "the bottlenecks aren't in model capability—they are in deterministic tool execution, memory state management, and latency.\n\n"
                            "What architectural patterns have proved most resilient in your production AI deployments?\n\n"
                            "Sources:\n- Weekly Technical & AI Intelligence Digest\n\n"
                            "#ArtificialIntelligence #CloudArchitecture #AgenticAI #SystemDesign"
                        ),
                        "sources_used": [{"title": "Weekly Digest", "url": ""}],
                        "hashtags": ["#ArtificialIntelligence", "#CloudArchitecture", "#AgenticAI"],
                    }
        return {}
