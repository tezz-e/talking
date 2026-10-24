"""
WhatsApp Chat Export Parser
============================

Parses WhatsApp's plain-text ``.txt`` chat export files into normalised
:class:`ChatMessage` objects.

WhatsApp export format
----------------------
::

    [DD/MM/YYYY, HH:MM:SS] Sender Name: Message body here
    [DD/MM/YYYY, HH:MM:SS] Sender Name: Multi line
    message continues here
    [15/03/2024, 10:02:10] Alice: IMG-20240315-WA0001.jpg (file attached)

The parser handles:

* **Both date orderings**: ``DD/MM/YYYY`` and ``MM/DD/YYYY`` — it auto-detects
  which format is in use by trying both and picking the one that produces no
  invalid dates.
* **12-hour and 24-hour clocks**: times with ``AM``/``PM`` suffixes are
  converted to 24-hour format automatically.
* **Multi-line messages**: continuation lines (those that do *not* match the
  timestamp pattern) are appended to the preceding message.
* **System messages**: lines without a colon-separated sender (e.g.
  "Messages and calls are end-to-end encrypted") are silently discarded.
* **Media placeholders**: ``<Media omitted>``, ``(file attached)`` and
  WhatsApp media filenames are detected and tagged with a ``media_type``.
* **UTF-8 BOM**: the file is opened with ``utf-8-sig`` to strip any BOM.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.models import ChatMessage

from .pii_scrubber import PIIScrubber

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants & compiled patterns
# ---------------------------------------------------------------------------

# Matches a WhatsApp message header (iOS brackets or Android dash).
# Group 1: date   Group 2: time (may include AM/PM)   Group 3: sender   Group 4: first line of body
_MSG_HEADER_RE = re.compile(
    r"\[?(\d{1,2}/\d{1,2}/\d{2,4}),\s"           # [date,
    r"(\d{1,2}:\d{2}(?::\d{2})?(?:\s?[APap][Mm]|\u202f?[APap][Mm])?)\]?\s?(?:-\s)?"  # time] -
    r"(.+?):\s"                                   # Sender:
    r"(.*)",                                      # Body
    re.DOTALL,
)

# Lines that match the timestamp-bracket prefix but have **no** sender
# (system messages like encryption notices, group changes, etc.).
_SYSTEM_LINE_RE = re.compile(
    r"\[?(\d{1,2}/\d{1,2}/\d{2,4}),\s"
    r"(\d{1,2}:\d{2}(?::\d{2})?(?:\s?[APap][Mm]|\u202f?[APap][Mm])?)\]?\s?(?:-\s)?"
    r"(.+)"
)

# Media detection patterns
_MEDIA_OMITTED_RE = re.compile(r"<Media omitted>", re.IGNORECASE)
_FILE_ATTACHED_RE = re.compile(
    r"([\w\-]+\.\w{2,5})\s*\(file attached\)", re.IGNORECASE
)
_MEDIA_EXT_MAP: dict[str, str] = {
    ".jpg": "photo", ".jpeg": "photo", ".png": "photo", ".gif": "photo",
    ".webp": "photo",
    ".mp4": "video", ".3gp": "video", ".avi": "video", ".mkv": "video",
    ".mov": "video",
    ".opus": "audio", ".mp3": "audio", ".m4a": "audio", ".aac": "audio",
    ".ogg": "audio", ".wav": "audio", ".ptt": "audio",
    ".pdf": "document", ".doc": "document", ".docx": "document",
    ".xls": "document", ".xlsx": "document", ".ppt": "document",
    ".pptx": "document",
    ".vcf": "contact",
    ".webm": "video",
}


# ---------------------------------------------------------------------------
# Date / time helpers
# ---------------------------------------------------------------------------

_DATE_FORMATS_DMY = [
    "%d/%m/%Y", "%d/%m/%y",
]
_DATE_FORMATS_MDY = [
    "%m/%d/%Y", "%m/%d/%y",
]

_TIME_FORMATS = [
    "%H:%M:%S",       # 24h with seconds
    "%H:%M",          # 24h without seconds
    "%I:%M:%S %p",    # 12h with seconds
    "%I:%M %p",       # 12h without seconds
    "%I:%M:%S%p",     # 12h no-space
    "%I:%M%p",        # 12h no-space no-seconds
]


def _parse_datetime(date_str: str, time_str: str, prefer_dmy: bool = True) -> datetime:
    """Parse a WhatsApp date + time string pair into a :class:`datetime`.

    Tries DD/MM/YYYY first (``prefer_dmy=True``) then MM/DD/YYYY, combined
    with all known time formats.

    Raises
    ------
    ValueError
        If no combination produces a valid datetime.
    """
    time_str_clean = time_str.strip().upper()
    date_orders = (_DATE_FORMATS_DMY + _DATE_FORMATS_MDY) if prefer_dmy else (
        _DATE_FORMATS_MDY + _DATE_FORMATS_DMY
    )

    for dfmt in date_orders:
        for tfmt in _TIME_FORMATS:
            try:
                combined = f"{date_str.strip()} {time_str_clean}"
                fmt = f"{dfmt} {tfmt}"
                return datetime.strptime(combined, fmt)
            except ValueError:
                continue

    raise ValueError(f"Unable to parse date/time: '{date_str}' / '{time_str}'")


def _detect_date_order(raw_lines: list[tuple[str, str, str, str]]) -> bool:
    """Heuristically decide whether the export uses DD/MM or MM/DD.

    Returns ``True`` for DD/MM/YYYY (i.e. ``prefer_dmy``).
    """
    dmy_ok = 0
    mdy_ok = 0

    for date_str, time_str, _, _ in raw_lines[:50]:  # sample first 50
        try:
            _parse_datetime(date_str, time_str, prefer_dmy=True)
            dmy_ok += 1
        except ValueError:
            pass
        try:
            _parse_datetime(date_str, time_str, prefer_dmy=False)
            mdy_ok += 1
        except ValueError:
            pass

    # If only one works, use it.  If both work equally, prefer DMY (more
    # common worldwide and in WhatsApp exports).
    return dmy_ok >= mdy_ok


def _detect_media(content: str) -> tuple[str, Optional[str]]:
    """Detect whether *content* represents a media message.

    Returns
    -------
    tuple[str, str | None]
        ``(display_content, media_type)`` — *media_type* is ``None`` when
        the message is plain text.
    """
    if _MEDIA_OMITTED_RE.search(content):
        return "[media]", "media"

    match = _FILE_ATTACHED_RE.search(content)
    if match:
        filename = match.group(1)
        ext = Path(filename).suffix.lower()
        media_type = _MEDIA_EXT_MAP.get(ext, "document")
        label = {
            "photo": "[photo]", "video": "[video]", "audio": "[audio]",
            "document": "[document]", "contact": "[contact]",
        }.get(media_type, "[file]")
        return label, media_type

    return content, None


# ---------------------------------------------------------------------------
# WhatsApp Parser
# ---------------------------------------------------------------------------

class WhatsAppParser:
    """Parse WhatsApp ``.txt`` chat exports into :class:`ChatMessage` lists.

    Parameters
    ----------
    user_display_name:
        The user's display name **exactly** as it appears in the WhatsApp
        export (i.e. the name shown before the colon in each message line).
    """

    def __init__(self, user_display_name: str) -> None:
        self.user_display_name = user_display_name

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_lines(file_path: Path) -> list[str]:
        """Read the file handling UTF-8 BOM and common encoding variants."""
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                return file_path.read_text(encoding=encoding).splitlines()
            except (UnicodeDecodeError, OSError):
                continue
        raise OSError(f"Unable to read {file_path} with any supported encoding")

    def _parse_raw_lines(self, lines: list[str]) -> list[tuple[str, str, str, str]]:
        """First pass: extract (date, time, sender, body) tuples.

        Continuation lines (those without a header) are merged into the
        preceding message body.  System messages are skipped.
        """
        entries: list[tuple[str, str, str, str]] = []

        for line in lines:
            header_match = _MSG_HEADER_RE.match(line)
            if header_match:
                entries.append((
                    header_match.group(1),  # date
                    header_match.group(2),  # time
                    header_match.group(3),  # sender
                    header_match.group(4),  # body (first line)
                ))
                continue

            # Check if it's a system message (has timestamp but no sender).
            if _SYSTEM_LINE_RE.match(line):
                # skip system messages
                continue

            # Continuation line — append to the previous message body.
            if entries:
                date, time, sender, body = entries[-1]
                entries[-1] = (date, time, sender, body + "\n" + line)

        return entries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_file(self, file_path: str) -> list[ChatMessage]:
        """Parse a single WhatsApp chat export file.

        Parameters
        ----------
        file_path:
            Path to the ``.txt`` export file.

        Returns
        -------
        list[ChatMessage]
            Messages in chronological order.
        """
        fp = Path(file_path).resolve()
        if not fp.is_file():
            raise FileNotFoundError(f"WhatsApp export file not found: {fp}")

        lines = self._read_lines(fp)
        if not lines:
            return []

        raw_entries = self._parse_raw_lines(lines)
        if not raw_entries:
            return []

        # Detect date order from the entries themselves.
        prefer_dmy = _detect_date_order(raw_entries)

        messages: list[ChatMessage] = []
        for date_str, time_str, sender, body in raw_entries:
            try:
                dt = _parse_datetime(date_str, time_str, prefer_dmy=prefer_dmy)
            except ValueError:
                logger.warning(
                    "Skipping unparseable date/time: %s / %s", date_str, time_str
                )
                continue

            content, media_type = _detect_media(body.strip())
            content = PIIScrubber.scrub(content)
            is_user = sender.strip() == self.user_display_name

            messages.append(
                ChatMessage(
                    sender=sender.strip(),
                    content=content,
                    timestamp=dt,
                    is_user=is_user,
                    reactions=None,
                    media_type=media_type,
                )
            )

        return messages

    def parse_folder(self, folder_path: str) -> dict[str, list[ChatMessage]]:
        """Parse every ``.txt`` file in a folder.

        Parameters
        ----------
        folder_path:
            Path to a directory containing one or more WhatsApp ``.txt``
            export files.

        Returns
        -------
        dict[str, list[ChatMessage]]
            Keyed by filename (without extension).
        """
        folder = Path(folder_path).resolve()
        if not folder.is_dir():
            raise NotADirectoryError(f"Not a directory: {folder}")

        result: dict[str, list[ChatMessage]] = {}

        for txt_file in sorted(folder.glob("*.txt")):
            key = txt_file.stem
            try:
                messages = self.parse_file(str(txt_file))
            except Exception as exc:
                logger.error("Failed to parse %s: %s", txt_file.name, exc)
                continue
            if messages:
                result[key] = messages

        logger.info("Parsed %d chat files from %s", len(result), folder)
        return result

    @staticmethod
    def get_user_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
        """Filter a message list to only the user's own messages.

        Parameters
        ----------
        messages:
            A list of :class:`ChatMessage` objects.

        Returns
        -------
        list[ChatMessage]
            Only messages where ``is_user is True``.
        """
        return [m for m in messages if m.is_user]
