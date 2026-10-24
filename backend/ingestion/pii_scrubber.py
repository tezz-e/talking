"""
PII Scrubber for Talking
========================
Masks sensitive personal and financial information (credit/debit cards,
phone numbers, passwords/tokens, government IDs) before text is ingested,
vectorized, or sent to language models.
"""

import re
from typing import Optional


class PIIScrubber:
    # ── Regular Expressions ───────────────────────────────────────────────────

    # Credit cards: 13-19 digits, with spaces or hyphens, matching common BINs
    _CC_PATTERN = re.compile(
        r"\b(?:4[0-9]{12}(?:[0-9]{3})?|"         # Visa
        r"5[1-5][0-9]{14}|"                       # MasterCard
        r"3[47][0-9]{13}|"                        # American Express
        r"3(?:0[0-5]|[68][0-9])[0-9]{11}|"        # Diners Club
        r"6(?:011|5[0-9]{2})[0-9]{12}|"           # Discover
        r"(?:2131|1800|35\d{3})\d{11})"           # JCB
        r"\b"
    )
    _FORMATTED_CC_PATTERN = re.compile(
        r"\b(?:\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}|\d{4}[ -]?\d{6}[ -]?\d{5})\b"
    )

    # Phone numbers: International (+91, +1, etc.) and domestic formatted numbers
    _PHONE_PATTERN = re.compile(
        r"(?:(?:\+|00)[1-9]\d{0,2}[ -]?)?"       # Optional country code
        r"(?:\(?\d{2,5}\)?[ -]?)?"               # Optional area code
        r"\d{3,5}[ -]?\d{3,5}\b"                  # Local number
    )
    # Stricter standalone phone number (at least 10 digits to avoid matching short numbers or dates)
    _STRICT_PHONE_PATTERN = re.compile(
        r"(?:\+?\d{1,3}[ -]?)?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}\b"
        r"|\b(?:\+91[ -]?)?[6-9]\d{9}\b"          # Common Indian mobile pattern
    )

    # Passwords and auth tokens (e.g., "password: ...", "api_key: ...")
    _SECRET_PATTERN = re.compile(
        r"(?i)\b(password|passwd|pwd|passcode|secret|api[_-]?key|token)\s*[:=]\s*(\S+)"
    )

    # Common API key formats (Google AI, GitHub, OpenAI)
    _API_KEY_PATTERN = re.compile(
        r"\b(AIza[0-9A-Za-z_\-]{30,45}|ghp_[0-9A-Za-z]{30,45}|sk-[0-9A-Za-z]{30,64})\b"
    )

    # US SSN (XXX-XX-XXXX)
    _SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

    # Indian Aadhaar (XXXX XXXX XXXX)
    _AADHAAR_PATTERN = re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")

    @classmethod
    def _is_luhn_valid(cls, card_str: str) -> bool:
        """Validate potential credit card digits using Luhn algorithm."""
        digits = [int(c) for c in card_str if c.isdigit()]
        if len(digits) < 13 or len(digits) > 19:
            return False
        checksum = 0
        reverse_digits = digits[::-1]
        for idx, digit in enumerate(reverse_digits):
            if idx % 2 == 1:
                doubled = digit * 2
                checksum += (doubled - 9) if doubled > 9 else doubled
            else:
                checksum += digit
        return checksum % 10 == 0

    @classmethod
    def scrub(cls, text: Optional[str]) -> str:
        """
        Scrub sensitive personal and financial identifiers from text.

        Replaces matching sensitive segments with safe semantic placeholders:
        [CREDIT_CARD], [PHONE_NUMBER], [PASSWORD], [API_KEY], [GOV_ID].
        """
        if not text:
            return ""

        scrubbed = str(text)

        # 1. API Keys and Tokens
        scrubbed = cls._API_KEY_PATTERN.sub("[API_KEY]", scrubbed)

        # 2. Key-value secrets (e.g. password: xyz)
        scrubbed = cls._SECRET_PATTERN.sub(r"\1: [PASSWORD]", scrubbed)

        # 3. Credit / Debit Cards (with Luhn validation for raw 16-digit blocks)
        def _replace_cc(match):
            val = match.group(0)
            clean_digits = re.sub(r"\D", "", val)
            if cls._is_luhn_valid(clean_digits):
                return "[CREDIT_CARD]"
            return val

        scrubbed = cls._FORMATTED_CC_PATTERN.sub(_replace_cc, scrubbed)

        # 4. Government IDs
        scrubbed = cls._SSN_PATTERN.sub("[GOV_ID]", scrubbed)
        scrubbed = cls._AADHAAR_PATTERN.sub("[GOV_ID]", scrubbed)

        # 5. Phone numbers (only scrub sequences that look like phone numbers and not dates)
        scrubbed = cls._STRICT_PHONE_PATTERN.sub("[PHONE_NUMBER]", scrubbed)

        return scrubbed
