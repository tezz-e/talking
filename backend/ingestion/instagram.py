"""
Instagram DM Export Parser
===========================

Parses Instagram's JSON data export format to extract direct message
conversations into normalised ChatMessage objects.

Instagram exports encode non-ASCII text (emojis, accented characters) using
a broken latin-1 / UTF-8 double-encoding scheme.  Every string field is run
through ``fix_encoding()`` which reverses this damage using a latin-1 →
UTF-8 round-trip, falling back to the ``ftfy`` library for any remaining
mojibake.

Export layout handled
---------------------
The parser searches for the ``inbox/`` directory in three locations:

1. ``<export_path>/inbox/``
2. ``<export_path>/your_instagram_activity/messages/inbox/``
3. ``<export_path>/messages/inbox/``

Within each conversation folder it reads every ``message_*.json`` file,
merges, deduplicates and sorts the messages chronologically (Instagram ships
them in **reverse** chronological order).
"""

from __future__ import annotations

import json
import logging
import sys
import os
from pathlib import Path
from typing import Optional

import ftfy

# ---------------------------------------------------------------------------
# Robust import of ChatMessage – works regardless of working directory or
# whether the package is invoked as a module or a script.
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from models import ChatMessage  # noqa: E402

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

def fix_encoding(text: Optional[str]) -> str:
    """Fix Instagram's broken UTF-8-as-latin-1 encoding.

    Instagram data exports encode multi-byte UTF-8 characters by storing each
    byte as a latin-1 code-point.  This function reverses that process.  When
    the simple round-trip fails (e.g. a mix of encodings) we fall back to
    ``ftfy.fix_text``.

    Parameters
    ----------
    text:
        Raw string from the JSON export. ``None`` is treated as empty string.

    Returns
    -------
    str
        The correctly decoded string.
    """
    if text is None:
        return ""
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return ftfy.fix_text(text)


# ---------------------------------------------------------------------------
# Instagram Parser
# ---------------------------------------------------------------------------

class InstagramParser:
    """Parse an unzipped Instagram data export into :class:`ChatMessage` lists.

    Parameters
    ----------
    export_path:
        Absolute or relative path to the root of the unzipped Instagram
        data export folder.
    user_display_name:
        The user's display name **exactly** as it appears in the export's
        ``sender_name`` / ``participants`` fields (before encoding fix).
        The parser will apply ``fix_encoding`` before comparison so you
        should supply the *decoded* (human-readable) version of the name.
    """

    # Possible relative locations of the inbox directory inside the export.
    _INBOX_CANDIDATES = (
        "inbox",
        Path("your_instagram_activity") / "messages" / "inbox",
        Path("messages") / "inbox",
    )

    def __init__(self, export_path: str, user_display_name: str) -> None:
        self.export_path = Path(export_path).resolve()
        self.user_display_name = user_display_name
        self._inbox_path: Optional[Path] = None

        if not self.export_path.exists():
            raise FileNotFoundError(
                f"Instagram export path does not exist: {self.export_path}"
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_inbox(self) -> Path:
        """Locate the ``inbox/`` directory inside the export.

        Raises
        ------
        FileNotFoundError
            If no inbox directory is found in any of the candidate locations.
        """
        if self._inbox_path is not None:
            return self._inbox_path

        for candidate in self._INBOX_CANDIDATES:
            full = self.export_path / candidate
            if full.is_dir():
                self._inbox_path = full
                logger.info("Found inbox at %s", full)
                return full

        raise FileNotFoundError(
            f"Could not locate inbox/ directory inside {self.export_path}. "
            f"Searched: {[str(self.export_path / c) for c in self._INBOX_CANDIDATES]}"
        )

    @staticmethod
    def _read_message_files(conversation_dir: Path) -> list[dict]:
        """Read and merge all ``message_*.json`` files in *conversation_dir*.

        Returns a flat list of raw message dicts (unsorted).
        """
        all_messages: list[dict] = []
        json_files = sorted(conversation_dir.glob("message_*.json"))

        if not json_files:
            logger.warning("No message_*.json files in %s", conversation_dir)
            return all_messages

        for jf in json_files:
            try:
                with open(jf, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                all_messages.extend(data.get("messages", []))
            except (json.JSONDecodeError, OSError) as exc:
                logger.error("Failed to read %s: %s", jf, exc)

        return all_messages

    @staticmethod
    def _get_conversation_metadata(conversation_dir: Path) -> dict:
        """Extract title and participant names from the first message file."""
        first_file = conversation_dir / "message_1.json"
        if not first_file.exists():
            # Fallback: try any message_*.json
            candidates = sorted(conversation_dir.glob("message_*.json"))
            if not candidates:
                return {"title": conversation_dir.name, "participants": []}
            first_file = candidates[0]

        try:
            with open(first_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return {"title": conversation_dir.name, "participants": []}

        title = fix_encoding(data.get("title", conversation_dir.name))
        participants = [
            fix_encoding(p.get("name", ""))
            for p in data.get("participants", [])
        ]
        return {"title": title, "participants": participants}

    def _raw_to_chat_message(self, raw: dict) -> ChatMessage:
        """Convert a single raw Instagram message dict to a :class:`ChatMessage`."""
        sender = fix_encoding(raw.get("sender_name", ""))
        timestamp_ms: int = raw.get("timestamp_ms", 0)

        # --- Determine content & media type ---
        content = ""
        media_type: Optional[str] = None

        if "content" in raw:
            content = fix_encoding(raw["content"])
        elif "photos" in raw:
            content = "[photo]"
            media_type = "photo"
        elif "videos" in raw:
            content = "[video]"
            media_type = "video"
        elif "audio_files" in raw:
            content = "[audio]"
            media_type = "audio"
        elif "share" in raw:
            share = raw["share"]
            link = share.get("link", "")
            share_text = share.get("share_text", "")
            content = fix_encoding(share_text) if share_text else link
            if not content:
                content = "[shared content]"
        elif "sticker" in raw:
            content = "[sticker]"
            media_type = "sticker"
        elif "gifs" in raw:
            content = "[gif]"
            media_type = "gif"

        # If we detected media via photos/videos/audio but also have content,
        # keep the content and just note the media type.
        if "content" in raw and "photos" in raw:
            media_type = "photo"
        elif "content" in raw and "videos" in raw:
            media_type = "video"
        elif "content" in raw and "audio_files" in raw:
            media_type = "audio"

        # --- Reactions ---
        reactions: Optional[list[dict[str, str]]] = None
        if "reactions" in raw:
            reactions = [
                {
                    "reaction": fix_encoding(r.get("reaction", "")),
                    "actor": fix_encoding(r.get("actor", "")),
                }
                for r in raw["reactions"]
            ]

        is_user = sender == self.user_display_name

        return ChatMessage(
            sender=sender,
            content=content,
            timestamp=timestamp_ms,
            is_user=is_user,
            reactions=reactions,
            media_type=media_type,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_conversations(self) -> list[dict]:
        """Scan the inbox and return metadata for every conversation.

        Returns
        -------
        list[dict]
            Each dict contains:

            - **path** (*str*): absolute path to the conversation directory.
            - **title** (*str*): conversation title from the export.
            - **participant_names** (*list[str]*): decoded participant names.
            - **message_count** (*int*): total messages across all JSON files.
        """
        inbox = self._find_inbox()
        conversations: list[dict] = []

        for conv_dir in sorted(inbox.iterdir()):
            if not conv_dir.is_dir():
                continue

            meta = self._get_conversation_metadata(conv_dir)
            msg_count = len(self._read_message_files(conv_dir))

            conversations.append(
                {
                    "path": str(conv_dir),
                    "title": meta["title"],
                    "participant_names": meta["participants"],
                    "message_count": msg_count,
                }
            )

        logger.info("Found %d conversations in %s", len(conversations), inbox)
        return conversations

    def parse_conversation(self, conversation_path: str) -> list[ChatMessage]:
        """Parse a single conversation folder into sorted ChatMessage objects.

        Parameters
        ----------
        conversation_path:
            Absolute path to the conversation directory (e.g.
            ``…/inbox/username_abc123/``).

        Returns
        -------
        list[ChatMessage]
            Messages sorted in chronological order (oldest first).
        """
        conv_dir = Path(conversation_path).resolve()
        if not conv_dir.is_dir():
            raise NotADirectoryError(
                f"Conversation path is not a directory: {conv_dir}"
            )

        raw_messages = self._read_message_files(conv_dir)
        if not raw_messages:
            return []

        chat_messages = [self._raw_to_chat_message(m) for m in raw_messages]

        # De-duplicate by (sender, timestamp, content) — Instagram sometimes
        # duplicates messages across split JSON files.
        seen: set[tuple] = set()
        unique: list[ChatMessage] = []
        for msg in chat_messages:
            key = (msg.sender, msg.timestamp, msg.content)
            if key not in seen:
                seen.add(key)
                unique.append(msg)

        # Instagram exports are reverse-chronological → sort ascending.
        unique.sort(key=lambda m: m.timestamp)
        return unique

    def parse_all(self) -> dict[str, list[ChatMessage]]:
        """Parse every conversation in the inbox.

        Returns
        -------
        dict[str, list[ChatMessage]]
            Keyed by conversation title (or participant name for 1-on-1 DMs).
        """
        conversations = self.find_conversations()
        result: dict[str, list[ChatMessage]] = {}

        for conv in conversations:
            title = conv["title"]
            try:
                messages = self.parse_conversation(conv["path"])
            except Exception as exc:
                logger.error("Failed to parse '%s': %s", title, exc)
                continue

            if not messages:
                continue

            # Avoid key collisions by appending a counter if needed.
            key = title
            counter = 2
            while key in result:
                key = f"{title} ({counter})"
                counter += 1

            result[key] = messages

        logger.info(
            "Parsed %d conversations with %d total messages",
            len(result),
            sum(len(v) for v in result.values()),
        )
        return result

    @staticmethod
    def get_user_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
        """Filter a message list to only the user's own messages.

        Parameters
        ----------
        messages:
            A list of :class:`ChatMessage` objects (e.g. from
            ``parse_conversation``).

        Returns
        -------
        list[ChatMessage]
            Only messages where ``is_user is True``.
        """
        return [m for m in messages if m.is_user]
