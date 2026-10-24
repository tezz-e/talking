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
        elif (self.data_dir / "SOUL.template.md").exists():
            self.soul = (self.data_dir / "SOUL.template.md").read_text(encoding="utf-8").strip()
            logger.info("Loaded SOUL.template.md (%d chars)", len(self.soul))
        else:
            logger.warning("SOUL.md not found at %s â€” using empty identity.", soul_path)
            self.soul = "You are a friendly, authentic person. Be yourself."

        if style_path.exists():
            self.style = style_path.read_text(encoding="utf-8").strip()
            logger.info("Loaded STYLE.md (%d chars)", len(self.style))
        elif (self.data_dir / "STYLE.template.md").exists():
            self.style = (self.data_dir / "STYLE.template.md").read_text(encoding="utf-8").strip()
            logger.info("Loaded STYLE.template.md (%d chars)", len(self.style))
        else:
            logger.warning("STYLE.md not found at %s â€” using default style.", style_path)
            self.style = "Text casually, like a real person. Keep it natural."

        self._loaded = True

    def _ensure_loaded(self) -> None:
        """Lazy-load personality files if not already loaded."""
        if not self._loaded:
            self.load()

    # â”€â”€ System Prompt Builder â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

        # â”€â”€ Core Identity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        sections.append(
            f"CORE IDENTITY:\n{self.soul}"
        )

        # â”€â”€ Texting Style â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        sections.append(
            f"TEXTING STYLE â€” FOLLOW THESE RULES STRICTLY:\n{self.style}"
        )

        # â”€â”€ Contact Context â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        interests = ", ".join(contact.get("their_interests", [])) or "unknown"
        jokes = ", ".join(contact.get("inside_jokes", [])) or "none yet"
        notes = contact.get("notes", "") or "none"
        style_notes = contact.get("style_notes", "") or "none"
        convo_goal = contact.get("convo_goal", "just_vibing")
        my_impression = contact.get("my_impression", "")
        strategy_note = contact.get("strategy_note", "")

        contact_lines = [
            f"You are texting with {contact.get('name', 'someone')}.",
            f"Relationship: {relationship_stage}",
            f"How you know them: {contact.get('how_you_know', 'unknown')}",
            f"Their interests: {interests}",
            f"Inside jokes: {jokes}",
            f"Their texting style: {style_notes}",
            f"Goal for this conversation: {convo_goal}",
        ]
        if my_impression:
            contact_lines.append(f"Your impression of them: {my_impression}")
        if notes:
            contact_lines.append(f"Notes: {notes}")
        if strategy_note:
            contact_lines.append(f"TACTICAL STRATEGY DIRECTIVE: {strategy_note}")

        sections.append("CURRENT CONVERSATION:\n" + "\n".join(contact_lines))

        sections.append(
            "RESPONSE STRATEGY:\n"
            "First understand the latest message on its own, like a normal text. "
            "If it is a question, answer it. If it is an update, react naturally. "
            "If it is emotional, match the emotion. If it is a joke, banter back. "
            "Use memories only when they are directly relevant; do not force old "
            "chat history into unrelated new topics."
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

        # â”€â”€ Retrieved Memories â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

        # â”€â”€ Recent Message History â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if recent_history:
            history_lines = []
            for msg in recent_history:
                role_label = "You" if msg.get("role") == "you" else contact.get("name", "Them")
                history_lines.append(f"{role_label}: {msg.get('content', '')}")
            sections.append(
                "RECENT MESSAGE HISTORY:\n" + "\n".join(history_lines)
            )

        # â”€â”€ Few-Shot Examples â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if few_shot_examples:
            example_lines = []
            for ex in few_shot_examples:
                role_label = "You" if ex.get("role") == "you" else "Them"
                example_lines.append(f"{role_label}: {ex.get('content', '')}")
            sections.append(
                "EXAMPLE EXCHANGES (match this style exactly):\n" + "\n".join(example_lines)
            )

        # â”€â”€ Mood â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        mood_instructions = self.get_mood_instructions(mood)
        sections.append(f"MOOD: {mood} â€” {mood_instructions}")

        # â”€â”€ Rules â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        rules = [
            "RULES:",
            "1. Reply as a single text message (or a few short ones if that's your style)",
            "2. Match the style in STYLE.md EXACTLY - same capitalization, emoji usage, abbreviations",
            "3. The current message matters most. Do not overfit to retrieved memories.",
            "4. Don't be generic. Be specific when there is useful context; otherwise just reply naturally.",
            "5. If recent messages look like a setup from a song, meme, or running bit, continue the bit in the same low-effort texting style shown in past chats. Do not explain the reference.",
            "6. Keep it natural - no AI-sounding phrases",
            "7. Never mention you are an AI",
            "8. Match the energy of the conversation",
            "9. If the mood is 'flirty', add subtle playful undertones",
            "10. If you don't know something, deflect naturally like a human would",
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
