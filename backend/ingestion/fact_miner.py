"""
Talking — Automated Fact Miner
==============================
Extracts persistent, high-confidence biographical facts and preferences
about contacts from conversation turns.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional, List

from backend.models import ChatMessage, Fact

logger = logging.getLogger(__name__)


class FactMiner:
    """
    Analyzes conversation transcripts to extract biographical facts,
    preferences, pet details, life events, and relationship context
    about the other speaker.
    """

    SYSTEM_INSTRUCTION = (
        "You are a biographical fact extraction engine. "
        "Analyze the conversation transcript between the user and their contact. "
        "Extract persistent, verifiable facts about the CONTACT (the other person, NOT the user).\n\n"
        "Categories to extract:\n"
        "- 'work': Job title, company, projects, studies\n"
        "- 'preference': Favorite food, music, hobbies, dislikes\n"
        "- 'pet': Animals they own, pet names, pet breeds\n"
        "- 'life_event': Birthdays, upcoming trips, anniversaries, moves\n"
        "- 'relationship': Mutual friends, family members, partner status\n"
        "- 'opinion': Strong viewpoints, favorite shows, stances\n\n"
        "Rules:\n"
        "1. Only extract facts about the OTHER person (not the user).\n"
        "2. Do NOT extract temporary moods or ephemeral gossip (e.g. 'is tired today').\n"
        "3. Keep each fact concise and declarative (e.g. 'Works as a frontend engineer at Figma').\n"
        "4. Assign confidence between 0.75 and 1.0. Ignore low-certainty guesses.\n"
        "5. Output strictly valid JSON as an array of objects with keys: 'category', 'fact', 'confidence'."
    )

    def __init__(self, llm_engine) -> None:
        self.llm = llm_engine

    def mine_facts(
        self,
        messages: list[ChatMessage],
        contact_id: str,
        contact_name: str = "Contact",
        max_messages: int = 150,
    ) -> List[Fact]:
        """
        Extract factual knowledge from a sequence of chat messages.

        Parameters
        ----------
        messages:
            List of ChatMessage objects (chronological).
        contact_id:
            Target contact ID to associate facts with.
        contact_name:
            Display name of the other person.
        max_messages:
            Maximum number of turns to analyze in one window.

        Returns
        -------
        List[Fact]
            Extracted facts ready for SQLite insertion.
        """
        if not messages or not self.llm:
            return []

        # Sample or take most recent messages up to max_messages
        sample = messages[-max_messages:] if len(messages) > max_messages else messages

        transcript_lines = []
        for m in sample:
            sender_label = "You" if m.is_user else contact_name
            if m.content and not m.content.startswith("["):
                transcript_lines.append(f"{sender_label}: {m.content}")

        if len(transcript_lines) < 4:
            return []

        transcript_text = "\n".join(transcript_lines)
        prompt = (
            f"Extract all persistent facts about {contact_name} from this chat:\n\n"
            f"{transcript_text}\n\n"
            "Output JSON array:"
        )

        try:
            from google.genai import types

            response = self.llm.client.models.generate_content(
                model=self.llm.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.SYSTEM_INSTRUCTION,
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            raw = response.text or ""
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
                cleaned = re.sub(r"```$", "", cleaned).strip()

            items = json.loads(cleaned)
            if not isinstance(items, list):
                return []

            facts: List[Fact] = []
            for item in items:
                category = str(item.get("category", "preference")).strip()
                fact_text = str(item.get("fact", "")).strip()
                try:
                    conf = float(item.get("confidence", 0.8))
                except (ValueError, TypeError):
                    conf = 0.8

                if fact_text and len(fact_text) > 4:
                    facts.append(
                        Fact(
                            contact_id=contact_id,
                            category=category,
                            fact=fact_text,
                            source="chat_extraction",
                            confidence=min(1.0, max(0.5, conf)),
                        )
                    )
            return facts

        except Exception as exc:
            logger.warning("Fact extraction failed (non-fatal): %s", exc)
            return []
