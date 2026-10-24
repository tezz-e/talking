"""
Talking — Telegram Chat Export Parser
=====================================
Parses Telegram Desktop JSON exports (e.g. result.json) into normalised
ChatMessage objects, with automated PII scrubbing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from backend.models import ChatMessage
from .pii_scrubber import PIIScrubber

logger = logging.getLogger(__name__)


class TelegramParser:
    """
    Parses Telegram Desktop JSON export files (single chat or multi-chat account exports)
    into standard ChatMessage objects.
    """

    def __init__(self, user_name: str) -> None:
        """
        Parameters
        ----------
        user_name:
            Display name of the user in the export (used to determine is_user).
        """
        self.user_name = user_name.strip()

    @staticmethod
    def _extract_text(raw_text: Union[str, List[Any]]) -> str:
        """
        Telegram export 'text' field can be either a plain string or a list
        containing plain strings and entity dictionaries (bold, italic, links, etc.).
        """
        if isinstance(raw_text, str):
            return raw_text.strip()
        if isinstance(raw_text, list):
            parts = []
            for item in raw_text:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
            return "".join(parts).strip()
        return ""

    @staticmethod
    def _parse_timestamp(msg_dict: Dict[str, Any]) -> datetime:
        """Parse timestamp from ISO string or unix epoch fallback."""
        date_str = msg_dict.get("date")
        if date_str:
            try:
                # Replace space with T if needed
                normalized = date_str.replace(" ", "T")
                return datetime.fromisoformat(normalized)
            except (ValueError, TypeError):
                pass

        unix_time = msg_dict.get("date_unixtime")
        if unix_time:
            try:
                return datetime.fromtimestamp(float(unix_time))
            except (ValueError, TypeError):
                pass

        return datetime.utcnow()

    def parse_messages(self, raw_messages: List[Dict[str, Any]]) -> List[ChatMessage]:
        """Parse a list of raw message objects from a Telegram chat."""
        parsed: List[ChatMessage] = []

        for m in raw_messages:
            # Skip non-message service events (e.g. phone calls, user joined, pin changed)
            if m.get("type") != "message":
                continue

            sender = str(m.get("from") or m.get("actor") or "Unknown").strip()
            raw_text = m.get("text", "")
            content = self._extract_text(raw_text)

            media_type: Optional[str] = None
            raw_media = m.get("media_type")
            if raw_media:
                if "voice" in str(raw_media) or "audio" in str(raw_media):
                    media_type = "audio"
                elif "video" in str(raw_media) or "animation" in str(raw_media):
                    media_type = "video"
                elif "sticker" in str(raw_media):
                    media_type = "sticker"
                else:
                    media_type = str(raw_media)
            elif m.get("photo"):
                media_type = "photo"
            elif m.get("file"):
                media_type = "file"

            if not content and media_type:
                content = f"[{media_type.capitalize()}]"

            # Skip empty entries with no text and no media
            if not content:
                continue

            # Scrub PII
            clean_content = PIIScrubber.scrub(content)

            dt = self._parse_timestamp(m)
            is_user = (
                sender.lower() == self.user_name.lower()
                or (not sender and m.get("from_id") == "user_self")
            )

            parsed.append(
                ChatMessage(
                    sender=sender,
                    content=clean_content,
                    timestamp=dt,
                    is_user=is_user,
                    reactions=m.get("reactions"),
                    media_type=media_type,
                )
            )

        return parsed

    def parse_file(self, file_path: str) -> Dict[str, List[ChatMessage]]:
        """
        Parse a single Telegram result.json file.
        Returns a dictionary mapping chat/contact name to a list of ChatMessage objects.
        """
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Telegram export file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        conversations: Dict[str, List[ChatMessage]] = {}

        # Case 1: Account-wide export with chats list
        if isinstance(data, dict) and "chats" in data and isinstance(data["chats"], dict):
            chat_list = data["chats"].get("list", [])
            for chat in chat_list:
                chat_name = chat.get("name") or f"Chat_{chat.get('id', 'unknown')}"
                raw_msgs = chat.get("messages", [])
                msgs = self.parse_messages(raw_msgs)
                if msgs:
                    conversations[chat_name] = msgs

        # Case 2: Single chat export
        elif isinstance(data, dict) and "messages" in data:
            chat_name = data.get("name") or path.parent.name or "Contact"
            raw_msgs = data.get("messages", [])
            msgs = self.parse_messages(raw_msgs)
            if msgs:
                conversations[chat_name] = msgs

        return conversations

    def parse_folder(self, folder_path: str) -> Dict[str, List[ChatMessage]]:
        """
        Search for result.json or any *.json files in folder and parse all conversations.
        """
        folder = Path(folder_path).resolve()
        if not folder.is_dir():
            raise NotADirectoryError(f"Not a directory: {folder}")

        # Look for result.json first
        result_file = folder / "result.json"
        if result_file.is_file():
            return self.parse_file(str(result_file))

        # Look recursively for result.json in subdirectories
        sub_results = list(folder.rglob("result.json"))
        if sub_results:
            merged: Dict[str, List[ChatMessage]] = {}
            for res_path in sub_results:
                try:
                    convs = self.parse_file(str(res_path))
                    for k, v in convs.items():
                        merged[k] = v
                except Exception as exc:
                    logger.warning("Error parsing %s: %s", res_path, exc)
            return merged

        # Fallback: parse any json files in the directory
        merged: Dict[str, List[ChatMessage]] = {}
        for json_file in folder.glob("*.json"):
            try:
                convs = self.parse_file(str(json_file))
                for k, v in convs.items():
                    merged[k] = v
            except Exception as exc:
                logger.warning("Error parsing %s: %s", json_file, exc)
        return merged
