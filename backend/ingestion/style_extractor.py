"""
Texting Style Extractor
========================

Analyses a collection of the user's chat messages to produce a quantitative
"texting fingerprint" — statistics about capitalisation, emoji usage,
abbreviations, punctuation habits, message length, laugh styles, and more.

The fingerprint is then rendered into a human-readable ``STYLE.md`` document
(either via an LLM for natural-language prose, or via simple templates).

Usage
-----
::

    from ingestion.style_extractor import StyleExtractor
    from models import ChatMessage

    extractor = StyleExtractor(llm=my_llm_instance)  # llm is optional
    extractor.extract_and_save(user_messages, "data/STYLE.md")
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from pathlib import Path
from typing import Optional

from backend.models import ChatMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Emoji detection
# ---------------------------------------------------------------------------

# Broad regex covering most Unicode emoji ranges, including modifiers,
# ZWJ sequences, variation selectors, and flag sequences.
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"   # emoticons
    "\U0001F300-\U0001F5FF"   # misc symbols & pictographs
    "\U0001F680-\U0001F6FF"   # transport & map
    "\U0001F700-\U0001F77F"   # alchemical symbols
    "\U0001F780-\U0001F7FF"   # geometric shapes extended
    "\U0001F800-\U0001F8FF"   # supplemental arrows-C
    "\U0001F900-\U0001F9FF"   # supplemental symbols & pictographs
    "\U0001FA00-\U0001FA6F"   # chess symbols
    "\U0001FA70-\U0001FAFF"   # symbols & pictographs extended-A
    "\U00002702-\U000027B0"   # dingbats
    "\U000024C2-\U0001F251"   # enclosed characters
    "\U0000FE0F"              # variation selector-16
    "\U0000200D"              # ZWJ
    "\U00002600-\U000026FF"   # misc symbols
    "\U00002300-\U000023FF"   # misc technical
    "\U0000203C-\U00003299"   # CJK symbols, enclosed CJK
    "]+",
    re.UNICODE,
)

# ---------------------------------------------------------------------------
# Abbreviation lexicon — common texting abbreviations to scan for.
# ---------------------------------------------------------------------------

_ABBREVIATION_WORDS: set[str] = {
    "u", "ur", "r", "y", "k", "ok", "kk", "lol", "lmao", "lmfao",
    "ngl", "fr", "bruh", "bro", "idk", "wyd", "hbu", "imo", "imho",
    "tbh", "smh", "omg", "omfg", "istg", "lowkey", "highkey",
    "prolly", "gonna", "wanna", "gotta", "tryna", "rn", "nvm",
    "ofc", "ily", "ilysm", "ikr", "ik", "wtf", "wth", "stfu",
    "af", "asf", "nah", "yea", "yeh", "yeah", "ye", "pls", "plz",
    "thx", "ty", "tysm", "np", "sry", "mb", "lmk", "hml", "hmu",
    "dm", "jk", "jkjk", "smth", "sth", "tho", "doe", "finna",
    "bet", "cap", "nocap", "sus", "ong", "w", "l", "fs", "frl",
    "ion", "ight", "aight", "ard", "yuh", "yup", "yep", "nope",
    "cuz", "cus", "bc", "b4", "2day", "2morrow", "2nite", "g2g",
    "gtg", "brb", "bbl", "ttyl", "ttyl8r",
}

# ---------------------------------------------------------------------------
# Laughing-style patterns
# ---------------------------------------------------------------------------

_LAUGH_PATTERNS: dict[str, re.Pattern] = {
    "lol":  re.compile(r"\blol\b", re.IGNORECASE),
    "lmao": re.compile(r"\blmao\b", re.IGNORECASE),
    "lmfao": re.compile(r"\blmfao\b", re.IGNORECASE),
    "haha": re.compile(r"\bha(?:ha)+\b", re.IGNORECASE),
    "hehe": re.compile(r"\bhe(?:he)+\b", re.IGNORECASE),
    "😂":   re.compile(r"😂"),
    "💀":   re.compile(r"💀"),
    "🤣":   re.compile(r"🤣"),
    "😭":   re.compile(r"😭"),
    "LMAO": re.compile(r"\bLMAO\b"),              # uppercase specifically
    "LOL":  re.compile(r"\bLOL\b"),                # uppercase specifically
    "HAHA": re.compile(r"\bHA(?:HA)+\b"),          # all-caps
}

# ---------------------------------------------------------------------------
# Filler / transition words
# ---------------------------------------------------------------------------

_FILLER_WORDS: set[str] = {
    "like", "just", "literally", "basically", "actually", "honestly",
    "probably", "maybe", "kinda", "sorta", "well", "so", "anyway",
    "anyways", "tho", "though", "still", "but", "also", "right",
    "okay", "wait", "oh", "ah", "um", "uh", "hmm", "damn",
}


# ===========================================================================
# StyleExtractor
# ===========================================================================

class StyleExtractor:
    """Analyse a user's messages and produce a texting-style fingerprint.

    Parameters
    ----------
    llm:
        An optional LLM instance (e.g. ``GeminiLLM``) that exposes a
        ``.generate(prompt: str) -> str`` method.  If provided, the
        ``STYLE.md`` output will be synthesised by the LLM for a more
        natural, readable result.  If ``None``, a structured template is
        used instead.
    """

    def __init__(self, llm=None) -> None:
        self.llm = llm

    # ------------------------------------------------------------------
    # Emoji helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_emojis(text: str) -> list[str]:
        """Return all emoji characters / sequences found in *text*.

        Uses a broad Unicode-range regex to capture emoticons, symbols,
        flags, and ZWJ sequences.

        Parameters
        ----------
        text:
            The string to scan for emojis.

        Returns
        -------
        list[str]
            Individual emoji characters found (may contain duplicates).
        """
        if not text:
            return []

        # The regex captures contiguous runs — split into individual chars
        # but preserve ZWJ sequences.
        matches = _EMOJI_RE.findall(text)
        emojis: list[str] = []
        for match in matches:
            # Split multi-emoji runs that aren't joined by ZWJ.
            # We keep ZWJ sequences intact.
            i = 0
            while i < len(match):
                ch = match[i]
                # Look ahead for ZWJ or variation selectors to keep sequences
                seq = ch
                j = i + 1
                while j < len(match) and match[j] in ("\u200d", "\ufe0f"):
                    seq += match[j]
                    j += 1
                    if j < len(match):
                        seq += match[j]
                        j += 1
                emojis.append(seq)
                i = j if j > i + 1 else i + 1

        return emojis

    # ------------------------------------------------------------------
    # Abbreviation detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_abbreviations(text: str) -> dict[str, int]:
        """Scan *text* for common texting abbreviations.

        Parameters
        ----------
        text:
            A single message string.

        Returns
        -------
        dict[str, int]
            Mapping of detected abbreviation → count within *text*.
        """
        if not text:
            return {}

        counts: dict[str, int] = {}
        words = re.findall(r"\b\w+\b", text.lower())
        for word in words:
            if word in _ABBREVIATION_WORDS:
                counts[word] = counts.get(word, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    def analyze(
        self,
        user_messages: list[ChatMessage],
        all_messages: Optional[list[ChatMessage]] = None,
    ) -> dict:
        """Compute comprehensive texting statistics.

        Parameters
        ----------
        user_messages:
            A list of :class:`ChatMessage` objects where ``is_user`` is
            ``True``.  Media-only messages (``[photo]``, etc.) are included
            in counts but excluded from text-based analysis where it would
            skew results.
        all_messages:
            Optional full list of messages across both speakers, used to
            accurately calculate conversational metrics like double-texting.

        Returns
        -------
        dict
            A rich statistics dictionary.  See module docstring for the
            full schema.
        """
        if not user_messages:
            return self._empty_stats()

        total = len(user_messages)

        # Filter to text-only messages for linguistic analysis.
        text_msgs = [
            m for m in user_messages
            if m.content and not m.content.startswith("[") and m.media_type is None
        ]
        text_count = len(text_msgs) or 1  # avoid division by zero

        # ---- Length stats ----
        lengths = [len(m.content) for m in text_msgs]
        word_counts = [len(m.content.split()) for m in text_msgs]
        avg_len = sum(lengths) / text_count if lengths else 0
        avg_words = sum(word_counts) / text_count if word_counts else 0

        # ---- Length distribution ----
        short = sum(1 for l in lengths if l <= 20)
        medium = sum(1 for l in lengths if 21 <= l <= 100)
        long_ = sum(1 for l in lengths if l > 100)
        length_dist = {
            "short_1_20": round(short / text_count * 100, 1),
            "medium_21_100": round(medium / text_count * 100, 1),
            "long_100_plus": round(long_ / text_count * 100, 1),
        }

        # ---- Capitalisation ----
        cap_lower = 0
        cap_upper = 0
        cap_mixed = 0
        cap_proper = 0
        for m in text_msgs:
            c = m.content.strip()
            if not c:
                continue
            if c == c.lower():
                cap_lower += 1
            elif c == c.upper():
                cap_upper += 1
            elif c[0].isupper() and c[1:] == c[1:].lower():
                cap_proper += 1
            else:
                cap_mixed += 1
        capitalisation = {
            "mostly_lowercase": round(cap_lower / text_count * 100, 1),
            "mostly_uppercase": round(cap_upper / text_count * 100, 1),
            "mixed": round(cap_mixed / text_count * 100, 1),
            "proper": round(cap_proper / text_count * 100, 1),
        }

        # ---- Emojis ----
        emoji_counter: Counter = Counter()
        total_emojis = 0
        emoji_standalone = 0

        for m in user_messages:
            emojis = self._extract_emojis(m.content)
            total_emojis += len(emojis)
            emoji_counter.update(emojis)
            # Check if message is *only* emoji (+ optional whitespace)
            stripped = _EMOJI_RE.sub("", m.content).strip()
            if not stripped and emojis:
                emoji_standalone += 1

        emoji_freq = total_emojis / total if total else 0
        top_emojis = emoji_counter.most_common(15)

        # ---- Abbreviations ----
        abbrev_counter: Counter = Counter()
        for m in text_msgs:
            abbrev_counter.update(self._detect_abbreviations(m.content))
        top_abbreviations = abbrev_counter.most_common(30)

        # ---- Punctuation ----
        punc_period = 0
        punc_excl = 0
        punc_question = 0
        punc_none = 0
        for m in text_msgs:
            c = m.content.rstrip()
            if not c:
                punc_none += 1
                continue
            last_char = c[-1]
            if last_char == ".":
                punc_period += 1
            elif last_char == "!":
                punc_excl += 1
            elif last_char == "?":
                punc_question += 1
            else:
                punc_none += 1
        punctuation = {
            "uses_periods": round(punc_period / text_count * 100, 1),
            "uses_exclamation": round(punc_excl / text_count * 100, 1),
            "uses_question_marks": round(punc_question / text_count * 100, 1),
            "no_punctuation": round(punc_none / text_count * 100, 1),
        }

        # ---- Greeting patterns ----
        greeting_counter: Counter = Counter()
        for m in text_msgs:
            words = m.content.strip().split()
            if words:
                first_word = words[0].lower().rstrip("!.,?")
                greeting_counter[first_word] += 1
        greeting_patterns = greeting_counter.most_common(15)

        # ---- Filler words ----
        filler_counter: Counter = Counter()
        for m in text_msgs:
            words_lower = [w.lower().strip(".,!?") for w in m.content.split()]
            for w in words_lower:
                if w in _FILLER_WORDS:
                    filler_counter[w] += 1
        filler_words = filler_counter.most_common(20)

        # ---- Double texting ----
        consecutive = 0
        total_user_in_thread = 0
        if all_messages:
            for i in range(1, len(all_messages)):
                if all_messages[i].is_user:
                    total_user_in_thread += 1
                    if all_messages[i - 1].is_user:
                        consecutive += 1
            double_texting_rate = (
                round(consecutive / total_user_in_thread * 100, 1)
                if total_user_in_thread > 0
                else 0.0
            )
        else:
            double_texting_rate = 0.0

        # ---- Laughing style ----
        laugh_counter: Counter = Counter()
        for m in user_messages:
            for label, pattern in _LAUGH_PATTERNS.items():
                count = len(pattern.findall(m.content))
                if count:
                    laugh_counter[label] += count
        laughing_style = laugh_counter.most_common()

        return {
            "total_messages_analyzed": total,
            "text_messages": len(text_msgs),
            "avg_message_length": round(avg_len, 1),
            "avg_word_count": round(avg_words, 1),
            "capitalization": capitalisation,
            "emoji_frequency": round(emoji_freq, 2),
            "top_emojis": top_emojis,
            "abbreviations": top_abbreviations,
            "punctuation": punctuation,
            "greeting_patterns": greeting_patterns,
            "filler_words": filler_words,
            "message_length_distribution": length_dist,
            "double_texting_rate": double_texting_rate,
            "emoji_as_standalone": round(emoji_standalone / total * 100, 1) if total else 0.0,
            "laughing_style": laughing_style,
        }

    @staticmethod
    def _empty_stats() -> dict:
        """Return a zeroed-out stats dict for the empty-input case."""
        return {
            "total_messages_analyzed": 0,
            "text_messages": 0,
            "avg_message_length": 0,
            "avg_word_count": 0,
            "capitalization": {
                "mostly_lowercase": 0, "mostly_uppercase": 0,
                "mixed": 0, "proper": 0,
            },
            "emoji_frequency": 0,
            "top_emojis": [],
            "abbreviations": [],
            "punctuation": {
                "uses_periods": 0, "uses_exclamation": 0,
                "uses_question_marks": 0, "no_punctuation": 0,
            },
            "greeting_patterns": [],
            "filler_words": [],
            "message_length_distribution": {
                "short_1_20": 0, "medium_21_100": 0, "long_100_plus": 0,
            },
            "double_texting_rate": 0,
            "emoji_as_standalone": 0,
            "laughing_style": [],
        }

    # ------------------------------------------------------------------
    # STYLE.md generation
    # ------------------------------------------------------------------

    def generate_style_md(self, stats: dict) -> str:
        """Produce a Markdown texting-fingerprint document from *stats*.

        If an LLM is available, the raw statistics are sent to the model
        for natural-language synthesis.  Otherwise, a structured template
        is used.

        Parameters
        ----------
        stats:
            The dict returned by :meth:`analyze`.

        Returns
        -------
        str
            The full contents of the ``STYLE.md`` file.
        """
        if self.llm is not None:
            return self._generate_with_llm(stats)
        return self._generate_template(stats)

    def _generate_with_llm(self, stats: dict) -> str:
        """Use the LLM to synthesise a natural-language STYLE.md."""
        system_instruction = (
            "You are a writing-style analyst.  Given the following quantitative "
            "statistics about a person's texting style, produce a detailed, well-"
            "organised Markdown document titled '# Texting Fingerprint'.\n\n"
            "The document should have sections for:\n"
            "- Capitalization\n"
            "- Emoji Usage (frequency, top emojis, standalone usage)\n"
            "- Abbreviations & Slang\n"
            "- Punctuation Habits\n"
            "- Message Length & Structure\n"
            "- Greeting Patterns\n"
            "- Filler Words\n"
            "- Double Texting Tendency\n"
            "- Laughing Style\n\n"
            "Write as concise bullet points under each heading.  Include the "
            "exact numbers/percentages from the stats.  Do NOT invent data."
        )
        user_message = f"Statistics:\n```json\n{self._stats_to_json_str(stats)}\n```"
        try:
            result = self.llm.generate(system_instruction, user_message)
            return result.strip()
        except Exception as exc:
            logger.warning("LLM generation failed, falling back to template: %s", exc)
            return self._generate_template(stats)

    @staticmethod
    def _stats_to_json_str(stats: dict) -> str:
        """Serialise stats to a JSON-like string for the LLM prompt."""
        import json
        # Convert tuples to lists for JSON serialisation.
        serialisable = {}
        for key, value in stats.items():
            if isinstance(value, list) and value and isinstance(value[0], tuple):
                serialisable[key] = [[item[0], item[1]] for item in value]
            else:
                serialisable[key] = value
        return json.dumps(serialisable, indent=2, ensure_ascii=False)

    @staticmethod
    def _generate_template(stats: dict) -> str:
        """Build STYLE.md from a fixed template and the stats dict."""
        cap = stats.get("capitalization", {})
        punc = stats.get("punctuation", {})
        dist = stats.get("message_length_distribution", {})

        lines = [
            "# Texting Fingerprint",
            "",
            f"*Based on {stats.get('total_messages_analyzed', 0):,} messages "
            f"({stats.get('text_messages', 0):,} text messages analysed)*",
            "",
            "## Capitalization",
            f"- Mostly lowercase: {cap.get('mostly_lowercase', 0)}%",
            f"- Mostly UPPERCASE: {cap.get('mostly_uppercase', 0)}%",
            f"- Mixed case: {cap.get('mixed', 0)}%",
            f"- Proper (first letter capitalised): {cap.get('proper', 0)}%",
            "",
            "## Emoji Usage",
            f"- Average emojis per message: {stats.get('emoji_frequency', 0)}",
            f"- Messages that are just emoji(s): {stats.get('emoji_as_standalone', 0)}%",
        ]

        top_emojis = stats.get("top_emojis", [])
        if top_emojis:
            emoji_str = ", ".join(
                f"{e} ({c})" for e, c in top_emojis
            )
            lines.append(f"- Top emojis: {emoji_str}")
        else:
            lines.append("- Top emojis: (none detected)")

        lines += [
            "",
            "## Abbreviations & Slang",
        ]
        abbreviations = stats.get("abbreviations", [])
        if abbreviations:
            for abbr, count in abbreviations:
                lines.append(f"- **{abbr}**: {count} uses")
        else:
            lines.append("- (none detected)")

        lines += [
            "",
            "## Punctuation",
            f"- Ends with period: {punc.get('uses_periods', 0)}%",
            f"- Ends with exclamation mark: {punc.get('uses_exclamation', 0)}%",
            f"- Ends with question mark: {punc.get('uses_question_marks', 0)}%",
            f"- No terminal punctuation: {punc.get('no_punctuation', 0)}%",
            "",
            "## Message Length",
            f"- Average characters: {stats.get('avg_message_length', 0)}",
            f"- Average words: {stats.get('avg_word_count', 0)}",
            f"- Short (1–20 chars): {dist.get('short_1_20', 0)}%",
            f"- Medium (21–100 chars): {dist.get('medium_21_100', 0)}%",
            f"- Long (100+ chars): {dist.get('long_100_plus', 0)}%",
            "",
            "## Greeting Patterns",
        ]
        greetings = stats.get("greeting_patterns", [])
        if greetings:
            for word, count in greetings[:10]:
                lines.append(f"- **{word}**: {count}")
        else:
            lines.append("- (none detected)")

        lines += [
            "",
            "## Filler Words",
        ]
        fillers = stats.get("filler_words", [])
        if fillers:
            for word, count in fillers[:10]:
                lines.append(f"- **{word}**: {count}")
        else:
            lines.append("- (none detected)")

        lines += [
            "",
            "## Message Patterns",
            f"- Double texting rate: {stats.get('double_texting_rate', 0)}%",
            "",
            "## Laughing Style",
        ]
        laughs = stats.get("laughing_style", [])
        if laughs:
            for style, count in laughs:
                lines.append(f"- **{style}**: {count}")
        else:
            lines.append("- (none detected)")

        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # All-in-one extraction
    # ------------------------------------------------------------------

    def extract_and_save(
        self,
        user_messages: list[ChatMessage],
        output_path: str,
        all_messages: Optional[list[ChatMessage]] = None,
    ) -> dict:
        """Analyse messages, generate STYLE.md, and write to disk.

        Parameters
        ----------
        user_messages:
            The user's messages (``is_user=True``).
        output_path:
            File path to write the ``STYLE.md`` document to.  Parent
            directories are created automatically.
        all_messages:
            Optional full message list for multi-speaker metrics.

        Returns
        -------
        dict
            The raw statistics dict (same as :meth:`analyze`).
        """
        stats = self.analyze(user_messages, all_messages=all_messages)
        md = self.generate_style_md(stats)

        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")

        logger.info("STYLE.md written to %s (%d bytes)", out, len(md))
        return stats
