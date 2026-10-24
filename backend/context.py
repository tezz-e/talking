"""
Talking — Context Assembly Engine

Orchestrates the RAG pipeline: pulls contact info, recent messages,
semantic memories, and facts, then assembles everything into a
system prompt ready for Gemini.
"""

import logging
import re
from difflib import SequenceMatcher
from datetime import datetime
from typing import Optional

from backend.database import DatabaseManager
from backend.memory import MemoryStore
from backend.personality import PersonalityEngine
from backend.models import Message

logger = logging.getLogger(__name__)


class ContextAssembler:
    """
    Coordinates DB lookups, vector search, and prompt construction
    to produce a fully-contextualized system prompt for generation.
    """

    def __init__(
        self,
        db: DatabaseManager,
        memory: MemoryStore,
        personality: PersonalityEngine,
        llm=None,
    ):
        self.db = db
        self.memory = memory
        self.personality = personality
        self.llm = llm

    # ══════════════════════════════════════════════════════════════════════
    #  ASSEMBLE CONTEXT FOR GENERATION
    # ══════════════════════════════════════════════════════════════════════

    def assemble(
        self,
        contact_id: str,
        incoming_message: str,
        mood: str = "default",
    ) -> tuple[str, str, list[str]]:
        """
        Build the full context for an AI reply.

        Args:
            contact_id:       The contact who sent the message.
            incoming_message: Their latest message text.
            mood:             Desired tone modifier.

        Returns:
            (system_prompt, user_message, retrieved_memories_text)
        """
        # 1. Load contact from DB
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise ValueError(f"Contact '{contact_id}' not found in database.")

        contact_dict = contact.model_dump()

        # 2. Get last 15 messages
        recent_msgs = self.db.get_recent_messages(contact_id, n=15)
        recent_history = [
            {"role": m.role, "content": m.content}
            for m in recent_msgs
        ]

        # 3. Search vector store for relevant memories
        retrieved_memories_text: list[str] = []
        learned_callback_hints = self._find_learned_callback_hints(
            contact_id=contact_id,
            incoming_message=incoming_message,
        )
        try:
            recent_query_lines = [
                m.content
                for m in recent_msgs[-5:]
                if m.content and m.content.strip()
            ]
            if recent_query_lines and recent_query_lines[-1].strip() == incoming_message.strip():
                recent_query_lines = recent_query_lines[:-1]
            memory_query = "\n".join(recent_query_lines + [incoming_message]).strip()
            results = self.memory.search(
                query=memory_query or incoming_message,
                contact_id=contact_id,
                n_results=8,
            )
            retrieved_memories_text = [r["text"] for r in results]
            callback_hints = []
            if not learned_callback_hints:
                callback_hints = self._find_callback_hints(
                    incoming_message=incoming_message,
                    retrieved_memories=retrieved_memories_text,
                )
            lyric_hints = []
            if not learned_callback_hints:
                lyric_hints = self._resolve_known_lyric_hints(
                    incoming_message=incoming_message,
                    retrieved_memories=retrieved_memories_text,
                )
        except Exception as exc:
            logger.warning("Memory search failed (non-fatal): %s", exc)
            callback_hints = []
            lyric_hints = []

        # 4. Get facts about this contact
        facts = self.db.get_facts(contact_id)
        if facts:
            facts_text = "\n".join(
                f"- [{f.category}] {f.fact} (confidence: {f.confidence:.0%})"
                for f in facts
            )
            # Append facts to contact notes for prompt context
            existing_notes = contact_dict.get("notes", "")
            contact_dict["notes"] = (
                f"{existing_notes}\n\nKNOWN FACTS:\n{facts_text}".strip()
            )

        # 5. Build the system prompt
        prompt_memories = None if learned_callback_hints else retrieved_memories_text
        system_prompt = self.personality.build_system_prompt(
            contact=contact_dict,
            relationship_stage=contact.relationship_stage.value,
            mood=mood,
            retrieved_memories=prompt_memories if prompt_memories else None,
            recent_history=recent_history if recent_history else None,
            learned_callback_hints=learned_callback_hints if learned_callback_hints else None,
            lyric_hints=lyric_hints if lyric_hints else None,
            callback_hints=callback_hints if callback_hints else None,
        )

        # 6. Format the user message
        user_message = f"{contact.name} says: {incoming_message}"

        # 7. Return everything
        logger.info(
            "Context assembled for contact '%s' — %d recent msgs, %d memories, %d facts",
            contact.name,
            len(recent_history),
            len(retrieved_memories_text),
            len(facts),
        )

        return system_prompt, user_message, retrieved_memories_text

    def _find_learned_callback_hints(
        self,
        contact_id: str,
        incoming_message: str,
    ) -> list[str]:
        """Find user-approved callback overrides for this contact."""
        hints = []
        for override in self.db.list_callback_overrides(contact_id):
            score = self._callback_similarity(
                incoming_message,
                override.get("trigger_text", ""),
            )
            if score < 0.82:
                continue
            hints.append(
                "User-approved callback for a similar incoming line: "
                f"'{override.get('response_text', '')}'."
            )
            if len(hints) >= 3:
                break
        return hints

    def get_learned_callback_reply(
        self,
        contact_id: str,
        incoming_message: str,
    ) -> Optional[str]:
        """Return an exact user-approved reply when a callback override matches."""
        best_score = 0.0
        best_reply: Optional[str] = None
        for override in self.db.list_callback_overrides(contact_id):
            score = self._callback_similarity(
                incoming_message,
                override.get("trigger_text", ""),
            )
            if score > best_score:
                best_score = score
                best_reply = override.get("response_text", "")

        if best_score >= 0.82 and best_reply:
            return best_reply
        return None

    @staticmethod
    def _normalize_callback_text(text: str) -> str:
        """Normalize chat text for fuzzy callback matching."""
        text = text.lower().replace("ain't", "aint").replace("don't", "dont")
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _callback_similarity(self, left: str, right: str) -> float:
        left_norm = self._normalize_callback_text(left)
        right_norm = self._normalize_callback_text(right)
        if not left_norm or not right_norm:
            return 0.0

        left_words = left_norm.split()
        right_words = right_norm.split()
        if len(right_words) < 3:
            return 0.0

        left_phrase = f" {left_norm} "
        right_phrase = f" {right_norm} "
        if len(left_norm) >= 8 and len(right_norm) >= 8 and (
            left_phrase in right_phrase or right_phrase in left_phrase
        ):
            return 1.0

        left_terms = set(left_words)
        right_terms = set(right_words)
        overlap = len(left_terms & right_terms) / max(len(left_terms), 1)
        sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
        return max(overlap, sequence)

    def _find_callback_hints(
        self,
        incoming_message: str,
        retrieved_memories: list[str],
    ) -> list[str]:
        """
        Find likely call-and-response continuations in retrieved chat snippets.

        If the incoming message resembles a past line, the next line from the
        same speaker is often the exact lyric/meme continuation the user wants.
        """
        hints: list[str] = []
        seen: set[str] = set()

        for memory in retrieved_memories:
            parsed_lines = []
            for raw_line in memory.splitlines():
                if ": " not in raw_line:
                    continue
                speaker, content = raw_line.split(": ", 1)
                content = content.strip()
                if speaker.strip() and content:
                    parsed_lines.append((speaker.strip(), content))

            for idx, (speaker, content) in enumerate(parsed_lines[:-1]):
                if self._callback_similarity(incoming_message, content) < 0.72:
                    continue

                continuations = []
                for next_speaker, next_content in parsed_lines[idx + 1 : idx + 4]:
                    if next_speaker == speaker and next_content:
                        continuations.append(next_content)
                    elif continuations:
                        break

                if not continuations:
                    continue

                hint = (
                    f"Current line resembles past line '{speaker}: {content}'. "
                    f"The next matching callback line was: '{continuations[0]}'."
                )
                if hint not in seen:
                    hints.append(hint)
                    seen.add(hint)
                if len(hints) >= 3:
                    return hints

        return hints

    def _resolve_known_lyric_hints(
        self,
        incoming_message: str,
        retrieved_memories: list[str],
    ) -> list[str]:
        """
        Ask the model for a tiny known-lyric continuation when local chat
        history appears to contain music/rap callbacks but not the right line.
        """
        if self.llm is None or not self._looks_like_lyric_context(
            incoming_message,
            retrieved_memories,
        ):
            return []

        memory_excerpt = "\n---\n".join(memory[:700] for memory in retrieved_memories[:3])
        system_instruction = (
            "You identify short song-lyric or meme callback continuations for a texting assistant. "
            "Use Google Search to verify the line before answering. "
            "If the user's current line is clearly a known lyric/setup, return ONLY a JSON object "
            "with keys confidence and continuation. The continuation must be the likely immediate "
            "next callback line, 10 words or fewer. If you are not confident, return "
            '{"confidence":0,"continuation":""}. Do not include explanations.'
        )
        user_message = (
            f"Search for the next lyric after this line: {incoming_message}\n\n"
            f"Relevant chat context:\n{memory_excerpt}\n\n"
            "Return JSON only."
        )

        try:
            if hasattr(self.llm, "generate_with_google_search"):
                raw, grounded = self.llm.generate_with_google_search(
                    system_instruction,
                    user_message,
                    temperature=0.1,
                )
            else:
                raw = ""
                grounded = False
            confidence, continuation = self._parse_lyric_hint(raw)
        except Exception as exc:
            logger.warning("Lyric callback resolver failed (non-fatal): %s", exc)
            return []

        if confidence < 0.74 or not continuation:
            return []

        continuation = self._limit_words(continuation, 10)
        return [
            (
                "Known lyric resolver suggests this short continuation: "
                f"'{continuation}'. Prefer this over local chat if it clearly fits."
            )
        ]

    @staticmethod
    def _looks_like_lyric_context(incoming_message: str, retrieved_memories: list[str]) -> bool:
        text = incoming_message.lower()
        music_markers = {
            "rap", "rapper", "song", "lyrics", "lyric", "cench", "central cee",
            "dave", "shawty", "cabo", "miami beach", "spotify",
        }
        if any(marker in text for marker in music_markers):
            return True

        # Very short, stylized fragments are often callback setups even when
        # they do not name the artist/song.
        normalized = ContextAssembler._normalize_callback_text(incoming_message)
        words = normalized.split()
        if 3 <= len(words) <= 9:
            memory_text = "\n".join(retrieved_memories[:2]).lower()
            return any(marker in memory_text for marker in ("lyric", "song", "rap", "rapper"))

        return False

    @staticmethod
    def _parse_lyric_hint(raw: str) -> tuple[float, str]:
        import json

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return 0.0, ""

        try:
            confidence = float(data.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        continuation = str(data.get("continuation", "")).strip()
        return confidence, continuation

    @staticmethod
    def _limit_words(text: str, max_words: int) -> str:
        words = text.strip().split()
        return " ".join(words[:max_words])

    # ══════════════════════════════════════════════════════════════════════
    #  SAVE EXCHANGE (after user approves / sends)
    # ══════════════════════════════════════════════════════════════════════

    def save_exchange(
        self,
        contact_id: str,
        their_message: str,
        your_response: str,
        ai_draft: Optional[str] = None,
        was_edited: bool = False,
        save_to_db: bool = False,
    ) -> None:
        """
        Persist a complete exchange (their message + your reply) to
        vector store, and optionally to the relational DB if requested.

        Args:
            contact_id:    The contact involved.
            their_message: What they said.
            your_response: What you actually sent.
            ai_draft:      The original AI draft (if any).
            was_edited:    Whether you modified the AI draft.
            save_to_db:    Whether to insert messages into SQLite (default: False).
        """
        now = datetime.utcnow()

        if save_to_db:
            # Save their message to DB
            their_msg = Message(
                contact_id=contact_id,
                role="them",
                content=their_message,
                timestamp=now,
            )
            self.db.add_message(their_msg)

            # Save your response to DB
            your_msg = Message(
                contact_id=contact_id,
                role="you",
                content=your_response,
                ai_draft=ai_draft,
                was_edited=was_edited,
                timestamp=now,
            )
            self.db.add_message(your_msg)

        # Add the exchange to the vector store for future retrieval
        exchange_text = f"Them: {their_message}\nYou: {your_response}"
        try:
            self.memory.add_messages(
                [
                    {
                        "text": exchange_text,
                        "contact_id": contact_id,
                        "timestamp": now.isoformat(),
                        "is_user": False,  # combined exchange
                    }
                ]
            )
        except Exception as exc:
            logger.warning("Failed to store exchange in vector memory (non-fatal): %s", exc)

        logger.info(
            "Saved exchange for contact '%s' — edited=%s, saved_to_db=%s",
            contact_id,
            was_edited,
            save_to_db,
        )
