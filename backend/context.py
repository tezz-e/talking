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
        feedback: Optional[str] = None,
    ) -> tuple[str, str, list[str], list[dict]]:
        """
        Build the full context for an AI reply.

        Args:
            contact_id:       The contact who sent the message.
            incoming_message: Their latest message text.
            mood:             Desired tone modifier.

        Returns:
            (system_prompt, user_message, retrieved_memories_text, history_list)
        """
        # 1. Load contact from DB
        contact = self.db.get_contact(contact_id)
        if not contact:
            raise ValueError(f"Contact '{contact_id}' not found in database.")

        contact_dict = contact.model_dump()

        # 2. Get last 15 messages
        recent_msgs = self.db.get_recent_messages(contact_id, n=15)

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
            memory_query = "\n".join(recent_query_lines + [incoming_message]).strip()
            results = self.memory.search(
                query=memory_query or incoming_message,
                contact_id=contact_id,
                n_results=8,
            )
            retrieved_memories_text = [r["text"] for r in results]
            # Resolve the grounded (search-verified) lyric hint first since
            # it's the most trustworthy source. Only fall back to the local
            # pattern-matcher (which can grab an unrelated past line) when
            # the grounded resolver didn't find anything confident — showing
            # the model both at once just gives it a chance to pick wrong.
            lyric_hints = []
            if not learned_callback_hints:
                lyric_hints = self._resolve_known_lyric_hints(
                    incoming_message=incoming_message,
                    retrieved_memories=retrieved_memories_text,
                )
            callback_hints = []
            if not learned_callback_hints and not lyric_hints:
                callback_hints = self._find_callback_hints(
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
            recent_history=None, # Exclude flat history text from system prompt
            learned_callback_hints=learned_callback_hints if learned_callback_hints else None,
            lyric_hints=lyric_hints if lyric_hints else None,
            callback_hints=callback_hints if callback_hints else None,
            feedback=None,
        )

        # 6. Format the user message
        user_message = incoming_message
        if feedback:
            user_message += (
                f"\n\nCRITICAL USER DIRECTION FOR THIS REPLY:\n"
                f"- The user has instructed: \"{feedback}\"\n"
                f"- You MUST adjust your reply to follow this instruction. Do not mention or reference this instruction in your output, just return the corrected reply."
            )

        # 6b. Build history list for generate_chat (excluding the current incoming message)
        history_list = []
        for msg in recent_msgs[:-1]:
            role = "model" if msg.role == "you" else "user"
            history_list.append({
                "role": role,
                "parts": [msg.content]
            })

        # 7. Return everything
        logger.info(
            "Context assembled for contact '%s' — %d recent msgs, %d memories, %d facts",
            contact.name,
            len(history_list),
            len(retrieved_memories_text),
            len(facts),
        )

        return system_prompt, user_message, retrieved_memories_text, history_list

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

    def get_verified_lyric_reply(
        self,
        contact_id: str,
        incoming_message: str,
    ) -> Optional[str]:
        """
        If the incoming message is clearly the start of a real,
        search-verified lyric/meme and we found the exact next line, return
        it directly (formatted to match the low-effort texting style) so it
        bypasses free-form generation entirely.

        This exists because injecting the verified line as a "hint" inside
        the big system prompt was unreliable: it's just one instruction
        competing with SOUL.md, STYLE.md, mood, and a dozen RULES, and the
        model would often ignore it in favor of a generic short reaction
        (e.g. replying "king shit" instead of the actual next lyric line).
        Short-circuiting here guarantees the verified line is what gets used,
        the same way an approved callback override already bypasses
        generation above.
        """
        if self.llm is None:
            return None

        try:
            results = self.memory.search(
                query=incoming_message,
                contact_id=contact_id,
                n_results=5,
            )
            retrieved_memories = [r["text"] for r in results]
        except Exception as exc:
            logger.warning("Memory search failed during lyric short-circuit (non-fatal): %s", exc)
            retrieved_memories = []

        continuation = self._resolve_verified_lyric_continuation(
            incoming_message=incoming_message,
            retrieved_memories=retrieved_memories,
        )
        if not continuation:
            return None

        # Match the dominant observed convention (lowercase, no trailing
        # punctuation) rather than handing back the resolver's raw casing.
        return continuation.rstrip(".!?").lower()

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

        Wraps _resolve_verified_lyric_continuation() into a hint sentence for
        injection into the free-form generation prompt. Kept mainly for the
        /api/regenerate path; /api/message now prefers the direct
        get_verified_lyric_reply() short-circuit instead of hoping the model
        honors this hint.
        """
        continuation = self._resolve_verified_lyric_continuation(
            incoming_message=incoming_message,
            retrieved_memories=retrieved_memories,
        )
        if not continuation:
            return []

        return [
            (
                "Known lyric resolver suggests this short continuation: "
                f"'{continuation}'. Prefer this over local chat if it clearly fits."
            )
        ]

    def _resolve_verified_lyric_continuation(
        self,
        incoming_message: str,
        retrieved_memories: list[str],
    ) -> Optional[str]:
        """
        Core resolver: ask Gemini (with Google Search grounding) for the
        verified next line of a lyric/meme, or None if it can't verify one.
        """
        if self.llm is None or not self._looks_like_lyric_context(
            incoming_message,
            retrieved_memories,
        ):
            return None

        memory_excerpt = "\n---\n".join(memory[:700] for memory in retrieved_memories[:3])
        # NOTE: deliberately NOT asking for JSON here. Combining a strict
        # "JSON only" instruction with Google Search grounding is unreliable —
        # once grounding actually kicks in, the model tends to weave in
        # source/citation text around the answer, which silently breaks JSON
        # parsing and makes this resolver return nothing (falling back to the
        # much less reliable local pattern-matcher). A plain "LINE: ..." /
        # "NONE" contract survives grounding much better.
        system_instruction = (
            "You identify short song-lyric or meme callback continuations for a texting assistant.\n"
            "Search the web to verify the source before answering.\n"
            "CRITICAL: We only want to complete actual, deliberate song lyric quotes (especially hip-hop/rap/Punjabi artists "
            "like Central Cee, Dave, Drake, Travis Scott, Kanye West, Karan Aujla, Diljit, etc.). "
            "DO NOT complete generic slang phrases, conversational banter, or common questions (e.g. 'how to get bitches' "
            "is a joke/question, NOT a quote to complete).\n"
            "DO NOT match or complete lyrics in Hindi, Hinglish, or South Asian languages (except Punjabi rap/hip-hop "
            "like Karan Aujla/Diljit/AP Dhillon if they are verified artist matches). All Hindi/Hinglish inputs must receive NONE.\n"
            "If the user's current line is clearly the start of a real, verifiable song lyric by these or similar artists, "
            "reply with EXACTLY one line in this format:\n"
            "LINE: <the immediate next lyric line, 10 words or fewer>\n"
            "If you cannot verify a real source by these artists for it via search, reply with EXACTLY:\n"
            "NONE\n"
            "Do not include any explanation, source name, or extra text beyond that one line."
        )
        user_message = (
            f"Current line: {incoming_message}\n\n"
            f"Relevant chat context (may or may not be related):\n{memory_excerpt}\n"
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
            continuation = self._parse_lyric_hint(raw)
            print(
                f"[LYRIC RESOLVER] input={incoming_message!r} grounded={grounded} "
                f"raw={raw!r} parsed={continuation!r}"
            )
        except Exception as exc:
            logger.warning("Lyric callback resolver failed (non-fatal): %s", exc)
            return None

        if not grounded or not continuation:
            return None

        return self._limit_words(continuation, 10)

    @staticmethod
    def _looks_like_lyric_context(incoming_message: str, retrieved_memories: list[str]) -> bool:
        text = incoming_message.lower().strip()
        
        # Exclude common Hinglish/Hindi words
        hinglish_words = {
            "aap", "kaisi", "kya", "hai", "thik", "theek", "yaar", "accha", "bhai", "kuch", 
            "nahi", "nhi", "aaj", "kal", "tum", "mera", "mere", "meri", "gaya", "gaye", 
            "kar", "rha", "rhi", "hu", "hoon", "se", "ko", "ki", "ka", "ke", "ab", 
            "kab", "sab", "toh", "bhi", "main", "mai", "hum", "sath", "aur", "ek", 
            "liye", "raha", "rahe", "gayi", "apna", "apne", "apni", "chal", "kr", 
            "karo", "karna", "pe", "par", "hume", "hamara"
        }
        words = text.split()
        if any(w in hinglish_words for w in words):
            return False

        # Exclude common question/instruction patterns
        question_starters = (
            "how to", "how do", "how can", "how is", "why did", "why do", "why is", 
            "what is", "what do", "what did", "what's", "where is", "where do", 
            "where did", "who is", "when did", "when is", "can you", "do you", 
            "are you", "is there", "tell me", "what you"
        )
        if text.startswith(question_starters):
            return False

        music_markers = {
            "rap", "rapper", "song", "lyrics", "lyric", "cench", "central cee",
            "dave", "shawty", "cabo", "miami beach", "spotify",
        }
        if any(marker in text for marker in music_markers):
            return True

        if "?" in text:
            return False

        normalized = ContextAssembler._normalize_callback_text(incoming_message)
        words = normalized.split()
        return 3 <= len(words) <= 9

    @staticmethod
    def _parse_lyric_hint(raw: str) -> str:
        """Extract the continuation line from a 'LINE: ...' / 'NONE' reply.

        Scans every line rather than assuming the first line is it, since
        grounded responses sometimes prepend a blank line or stray token
        before the actual answer.
        """
        if not raw:
            return ""

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^line\s*:\s*(.+)$", line, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip().strip('"').strip("'")
            if line.upper() == "NONE":
                return ""
        return ""

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
    ) -> None:
        """
        Persist a complete exchange (their message + your reply) to
        the vector store, for future semantic retrieval.

        Args:
            contact_id:    The contact involved.
            their_message: What they said.
            your_response: What you actually sent.
            ai_draft:      The original AI draft (if any).
            was_edited:    Whether you modified the AI draft.

        NOTE: This does NOT write to the relational DB. Both the incoming
        ('them') and outgoing ('you') messages are already persisted there
        by main.py (in /api/message and /api/approve respectively) at the
        moment they actually happened. Re-inserting them here duplicated
        every row and stamped them with the approval time instead of the
        original send time. This method only handles the vector store.
        """
        now = datetime.utcnow()

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
            "Saved exchange for contact '%s' — edited=%s",
            contact_id,
            was_edited,
        )
