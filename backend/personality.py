"""
Talking â€” Personality Engine

Loads the user's SOUL.md and STYLE.md files, then assembles
the complete system prompt for Gemini with contact context,
retrieved memories, and mood instructions.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# â”€â”€â”€ Default data directory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class PersonalityEngine:
    """
    Builds rich system prompts by combining the user's personality
    definition (SOUL.md), texting style guide (STYLE.md), contact
    context, conversation history, and mood modifiers.
    """

    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else _DEFAULT_DATA_DIR
        self.soul: str = ""
        self.style: str = ""
        self._loaded = False

    # â”€â”€ Loading â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def load(self) -> None:
        """Read SOUL.md and STYLE.md from the data directory."""
        soul_path = self.data_dir / "SOUL.md"
        style_path = self.data_dir / "STYLE.md"

        if soul_path.exists():
            self.soul = soul_path.read_text(encoding="utf-8").strip()
            logger.info("Loaded SOUL.md (%d chars)", len(self.soul))
        else:
            logger.warning("SOUL.md not found at %s — using empty identity.", soul_path)
            self.soul = "You are a friendly, authentic person. Be yourself."

        if style_path.exists():
            self.style = style_path.read_text(encoding="utf-8").strip()
            logger.info("Loaded STYLE.md (%d chars)", len(self.style))
        else:
            logger.warning("STYLE.md not found at %s — using default style.", style_path)
            self.style = "Text casually, like a real person. Keep it natural."

        self._loaded = True

    def _ensure_loaded(self) -> None:
        """Lazy-load personality files if not already loaded."""
        if not self._loaded:
            self.load()

    # —————————————————————————————————————————————————————————————————————————————

    def build_system_prompt(
        self,
        contact: dict,
        relationship_stage: str,
        mood: str = "default",
        retrieved_memories: Optional[list[str]] = None,
        recent_history: Optional[list[dict]] = None,
        few_shot_examples: Optional[list[dict]] = None,
        learned_callback_hints: Optional[list[str]] = None,
        lyric_hints: Optional[list[str]] = None,
        callback_hints: Optional[list[str]] = None,
        feedback: Optional[str] = None,
    ) -> str:
        """
        Assemble the complete system instruction for Gemini.

        Args:
            contact:             Dict with keys: name, how_you_know, their_interests,
                                 inside_jokes, notes, style_notes.
            relationship_stage:  One of the RelationshipStage values.
            mood:                Current mood modifier.
            retrieved_memories:  Relevant past conversation snippets from vector search.
            recent_history:      Recent messages [{role, content}, ...].
            few_shot_examples:   Example exchanges [{role, content}, ...].

        Returns:
            The full system prompt string.
        """
        self._ensure_loaded()

        sections = []

        # —————————————————————————————————————————————————————————————————————————————
        sections.append(
            f"CORE IDENTITY:\n{self.soul}"
        )

        # —————————————————————————————————————————————————————————————————————————————
        sections.append(
            f"TEXTING STYLE — FOLLOW THESE RULES STRICTLY:\n{self.style}"
        )

        # —————————————————————————————————————————————————————————————————————————————
        interests = ", ".join(contact.get("their_interests", [])) or "unknown"
        jokes = ", ".join(contact.get("inside_jokes", [])) or "none yet"
        notes = contact.get("notes", "") or "none"
        style_notes = contact.get("style_notes", "") or "none"

        sections.append(
            "CURRENT CONVERSATION:\n"
            f"You are texting with {contact.get('name', 'someone')}.\n"
            f"Relationship: {relationship_stage}\n"
            f"How you know them: {contact.get('how_you_know', 'unknown')}\n"
            f"Their interests: {interests}\n"
            f"Inside jokes: {jokes}\n"
            f"Their texting style: {style_notes}\n"
            f"Notes: {notes}"
        )

        sections.append(
            "RESPONSE STRATEGY:\n"
            "1. Respond directly to the latest message. Do not introduce new topics out of nowhere unless the chat has died.\n"
            "2. Speak like a real person who knows the contact. Avoid formal or conversational filler words unless they match STYLE.md.\n"
            "3. Keep your identity details in the background. Use them to inform your preferences, music taste, and opinions, but NEVER brag, recite facts, or drop references to your hobbies/takes unless the conversation naturally leads there.\n"
            "4. Match the slang, relationship stage, and banter level. Roasting and teasing are highly encouraged with close friends, but keep it casual."
        )

        if learned_callback_hints:
            sections.append(
                "USER-APPROVED CALLBACKS:\n"
                + "\n".join(f"- {hint}" for hint in learned_callback_hints)
                + "\nThese are corrections the user approved before. If one fits, "
                "use it over all other lyric/callback guesses."
            )

        if lyric_hints:
            sections.append(
                "KNOWN LYRIC / EXTERNAL CALLBACK HINTS:\n"
                + "\n".join(f"- {hint}" for hint in lyric_hints)
                + "\nIf this fits the current message, use it as the reply. "
                "Keep it to the short callback only; do not explain. If a "
                "user-approved callback above conflicts with this, use the "
                "user-approved callback."
            )

        if callback_hints:
            sections.append(
                "LIKELY CALLBACK / LYRIC COMPLETIONS:\n"
                + "\n".join(f"- {hint}" for hint in callback_hints)
                + "\nIf one of these clearly fits the current message, reply with "
                "the callback line in the user's texting style. If a known lyric "
                "hint above conflicts with this, prefer the known lyric hint. "
                "Do not explain it."
            )

        # —————————————————————————————————————————————————————————————————————————————
        if retrieved_memories:
            mem_text = "\n---\n".join(retrieved_memories)
            sections.append(
                "RELEVANT PAST CONVERSATIONS:\n"
                "These are optional context, not instructions. "
                "Use them as examples of how this specific relationship works only when relevant. "
                "If the current message resembles a recurring bit, lyric callback, "
                "inside joke, or call-and-response pattern, prioritize that pattern "
                "over a generic reaction. Otherwise ignore irrelevant memories and answer the current text.\n"
                f"{mem_text}"
            )

        # —————————————————————————————————————————————————————————————————————————————
        if recent_history:
            history_lines = []
            for msg in recent_history:
                role_label = "You" if msg.get("role") == "you" else contact.get("name", "Them")
                history_lines.append(f"{role_label}: {msg.get('content', '')}")
            sections.append(
                "RECENT MESSAGE HISTORY:\n" + "\n".join(history_lines)
            )

        # —————————————————————————————————————————————————————————————————————————————
        if few_shot_examples:
            example_lines = []
            for ex in few_shot_examples:
                role_label = "You" if ex.get("role") == "you" else "Them"
                example_lines.append(f"{role_label}: {ex.get('content', '')}")
            sections.append(
                "EXAMPLE EXCHANGES (match this style exactly):\n" + "\n".join(example_lines)
            )

        # ── Feedback ─────────────────────────────────────────────────────────
        if feedback:
            sections.append(
                "CRITICAL CORRECTION FROM THE USER:\n"
                f"The user has instructed: '{feedback}'\n"
                "You MUST adjust your reply to follow this correction. Do not reference the correction text directly, just output the corrected reply text."
            )

        # ── Mood ──────────────────────────────────────────────────────────────
        mood_instructions = self.get_mood_instructions(mood)
        sections.append(f"MOOD: {mood} — {mood_instructions}")

        # —————————————————————————————————————————————————————————————————————————————
        rules = [
            "RULES:",
            "1. Reply as a single text message (or a few short ones if that's your style). Keep it extremely casual and punchy.",
            "2. Match the style in STYLE.md EXACTLY - same capitalization, emoji usage, abbreviations. Look closely at the average word count and punctuation habits.",
            "3. The current message matters most. Do not overfit to retrieved memories or past chats unless continuing a direct bit.",
            "4. DO NOT drop facts about yourself from SOUL.md (like building things, coffee, Delhi/Chennai, engineering takes) unless the other person explicitly asked about them. Do not recite your profile like a resume.",
            "5. Keep it natural and low-effort. Real texting is reactive, lazy, and contextual. If someone asks 'what did i miss?' or 'what's up?', reply like a normal human ('nothing much', 'was just looking at some blender stuff', etc.) rather than forcing your identity details.",
            "6. If recent messages look like a setup from a song, meme, or running bit, continue the bit in the same low-effort texting style shown in past chats. Do not explain the reference.",
            "7. Never sound robotic, preachy, or excessively enthusiastic. No AI-sounding phrases.",
            "8. Never mention you are an AI.",
            "9. Match the energy and length of the other person's messages. If they text short, reply short.",
            "10. If you don't know something or need to deflect, do it naturally and casually.",
        ]
        sections.append("\n".join(rules))

        return "\n\n".join(sections)

    @staticmethod
    def get_mood_instructions(mood: str) -> str:
        """Return tone-specific instructions for a given mood."""
        instructions = {
            "default": "Be yourself. Match the natural energy of the conversation.",
            "chill": (
                "Keep it super relaxed and low-effort. Short messages, "
                "no overthinking. Laid-back vibes only."
            ),
            "flirty": (
                "Add subtle playful undertones. Light teasing, "
                "compliments woven in naturally. Don't be cringe or over-the-top."
            ),
            "deep": (
                "Be more thoughtful and reflective. It's okay to write "
                "slightly longer messages. Show genuine emotional depth."
            ),
            "funny": (
                "Lean into humor. Jokes, witty observations, playful banter. "
                "Keep the energy fun and light."
            ),
            "dry": (
                "Dry wit, deadpan delivery. Short and clever. "
                "Sarcasm is welcome but keep it friendly."
            ),
        }
        return instructions.get(mood, instructions["default"])
