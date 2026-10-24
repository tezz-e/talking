"""
Talking — Gemini API Wrapper (google-genai SDK)

Provides LLM generation and embedding via the NEW google-genai package.
Includes retry logic with exponential backoff for rate limits.
"""

import os
import time
import logging
from typing import Optional, Any, Dict, List
import requests

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class GeminiLLM:
    """
    Wrapper around the google-genai SDK for text generation and embedding.

    Uses:
      - gemini-2.5-flash for generation (configurable)
      - text-embedding-004 for embeddings

    API key is read from the GEMINI_API_KEY environment variable by default.
    """

    DEFAULT_MODEL = "gemini-2.5-flash"
    EMBEDDING_MODEL = "gemini-embedding-2"
    MAX_RETRIES = 8
    BASE_BACKOFF = 1.5  # seconds

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "Gemini API key is required. Set GEMINI_API_KEY env var "
                "or pass api_key= to GeminiLLM()."
            )
        self.model = model or self.DEFAULT_MODEL
        self.client = genai.Client(api_key=self.api_key)
        logger.info("GeminiLLM initialized — model=%s", self.model)

    # ── Retry helper ──────────────────────────────────────────────────────

    def _retry(self, fn, *args, **kwargs):
        """
        Execute `fn` with exponential backoff on rate-limit (429) errors.
        """
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                error_str = str(exc).lower()
                is_transient = any(
                    term in error_str
                    for term in [
                        "429",
                        "resource_exhausted",
                        "rate",
                        "503",
                        "unavailable",
                        "spikes in demand",
                        "overloaded",
                        "500",
                        "internal",
                        "timeout",
                        "connectionreset",
                    ]
                )

                if is_transient and attempt < self.MAX_RETRIES:
                    wait = self.BASE_BACKOFF * (2 ** (attempt - 1))
                    msg = f"[LLM API] Transient error / rate limited (attempt {attempt}/{self.MAX_RETRIES}). Retrying in {wait:.1f}s..."
                    print(msg)
                    logger.warning(msg)
                    time.sleep(wait)
                    continue

                err_msg = f"[LLM API] Gemini API error: {exc}"
                print(err_msg)
                logger.error(err_msg)
                raise

    # ── Generation ────────────────────────────────────────────────────────

    def generate(
        self,
        system_instruction: str,
        user_message: str,
        temperature: float = 0.8,
    ) -> str:
        """
        Single-turn generation with a system instruction.

        Args:
            system_instruction: The system prompt.
            user_message:       The user's input.
            temperature:        Sampling temperature (0-2).

        Returns:
            The model's text response.
        """

        def _call():
            response = self.client.models.generate_content(
                model=self.model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                ),
            )
            return response.text

        return self._retry(_call)

    @staticmethod
    def _clean_json_text(raw: str) -> str:
        """Extract and sanitize JSON from model output, handling fences, preamble and trailing commas."""
        import re
        cleaned = raw.strip()
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
        if match:
            cleaned = match.group(1)
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        # Remove trailing commas before closing braces or brackets
        cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)
        return cleaned

    def generate_variants(
        self,
        system_instruction: str,
        user_message: str,
        temperature: float = 0.7,
    ) -> dict[str, dict[str, Any]]:
        """
        Generate 3 calibrated energy drafts in one API call:
          - chill: low-effort, casual, relaxed, short (1-6 words)
          - direct: natural, clear, moving conversation forward
          - banter: witty, playful, teasing, or callback banter

        Supports multi-bubble bursts (double-texting / split messages).
        Returns dict where each key maps to {'text': str, 'bubbles': list[str]}.
        """
        import json

        prompt = (
            f"{user_message}\n\n"
            "Generate 3 distinct reply options following STYLE.md and the conversation context:\n"
            "1. 'chill': Low-effort, super relaxed, casual, short (1 to 6 words).\n"
            "2. 'direct': Natural, balanced, clear, moving the conversation forward.\n"
            "3. 'banter': Playful, witty, light teasing, or inside-joke / callback energy.\n\n"
            "MULTI-BUBBLE BURSTS:\n"
            "If a reply naturally flows as 2 or 3 quick message bursts (e.g. ['wait really', 'i thought that was closed monday'] "
            "or ['nah that's wild', 'where did you find that 💀']), return it as a list of strings. "
            "Otherwise, a single string or 1-item list is fine.\n\n"
            "Output strictly valid JSON with keys: \"chill\", \"direct\", \"banter\".\n"
            "Values can be a list of strings (e.g. [\"bubble 1\", \"bubble 2\"]) or a single string."
        )

        def _call():
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                    response_mime_type="application/json",
                ),
            )
            return response.text

        raw = self._retry(_call)
        result: dict[str, dict[str, Any]] = {}
        try:
            cleaned = self._clean_json_text(raw)
            data = json.loads(cleaned)
            for label in ("chill", "direct", "banter"):
                val = data.get(label, "")
                if isinstance(val, list):
                    bubbles = [str(b).strip() for b in val if str(b).strip()]
                    text = "\n".join(bubbles)
                elif isinstance(val, str):
                    val_s = val.strip()
                    if "\n" in val_s:
                        bubbles = [b.strip() for b in val_s.split("\n") if b.strip()]
                    elif " // " in val_s:
                        bubbles = [b.strip() for b in val_s.split(" // ") if b.strip()]
                    else:
                        bubbles = [val_s] if val_s else []
                    text = "\n".join(bubbles)
                else:
                    bubbles = []
                    text = ""
                result[label] = {"text": text, "bubbles": bubbles}
            return result
        except Exception as exc:
            logger.warning("Variant JSON parsing failed, using raw output: %s", exc)
            fallback_text = raw.strip()
            return {
                "direct": {"text": fallback_text, "bubbles": [fallback_text] if fallback_text else []},
                "chill": {"text": "", "bubbles": []},
                "banter": {"text": "", "bubbles": []},
            }

    def generate_with_google_search(
        self,
        system_instruction: str,
        user_message: str,
        temperature: float = 0.1,
    ) -> tuple[str, bool]:
        """
        Generate with Google Search grounding enabled.

        Returns:
            (response_text, had_grounding_metadata)
        """

        def _call():
            response = self.client.models.generate_content(
                model=self.model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
            grounded = False
            if response.candidates:
                grounded = bool(getattr(response.candidates[0], "grounding_metadata", None))
            return response.text, grounded

        return self._retry(_call)

    def generate_chat(
        self,
        system_instruction: str,
        history: list[dict],
        new_message: str,
        temperature: float = 0.8,
    ) -> str:
        """
        Multi-turn chat generation.

        Replays the conversation history then sends the new message.

        Args:
            system_instruction: The system prompt.
            history:            List of {'role': 'user'|'model', 'parts': [str]}.
            new_message:        The latest user message.
            temperature:        Sampling temperature.

        Returns:
            The model's text response.
        """

        def _call():
            # Build content list from history
            contents = []
            for msg in history:
                role = msg.get("role", "user")
                text = msg.get("parts", [msg.get("content", "")])[0] if isinstance(msg.get("parts"), list) else msg.get("parts", msg.get("content", ""))
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=text)],
                    )
                )

            # Append the new message
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=new_message)],
                )
            )

            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                ),
            )
            return response.text

        return self._retry(_call)

    def extract_text_from_image(self, image_bytes: bytes, mime_type: str) -> str:
        """
        Extract the incoming text messages from a chat screenshot.
        """
        system_instruction = (
            "Extract the text messages sent by the other person from this screenshot. "
            "If there are multiple, combine them into a single string separated by spaces. "
            "Do NOT include your own messages, timestamps, UI elements, or headers. "
            "Just output the raw text they sent."
        )
        def _call():
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    types.Part.from_text(text="Extract their messages.")
                ],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1, # Low temperature for accurate OCR
                ),
            )
            return response.text

        return self._retry(_call)

    def describe_image(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
        """
        Produce a concise, natural description of an image or reel thumbnail
        for conversational context.
        """
        system_instruction = (
            "You are a multimodal vision engine for a casual texting assistant. "
            "Analyze the image or reel preview. Output a single, concise descriptive sentence "
            "describing what is shown, who or what is doing what, any meme text or punchline, "
            "or the general topic (e.g. 'A video of an orange cat knocking a cup off the counter' "
            "or 'A meme joking about debugging code at 3am' or 'A photo of a sunset at the beach'). "
            "Do NOT include boilerplate or preamble. Just the concise description."
        )

        def _call():
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    types.Part.from_text(text="Describe this media briefly for chat context.")
                ],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,
                ),
            )
            return response.text.strip() if response.text else "media"

        return self._retry(_call)

    def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
        """
        Transcribe an incoming voice note using Gemini's native multimodal audio understanding.
        """
        system_instruction = (
            "You are an accurate audio transcription engine for casual voice notes. "
            "Transcribe the spoken audio verbatim in its original language. "
            "Do not add commentary, speaker labels, or preambles. Output only the transcribed text."
        )

        def _call():
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    types.Part.from_text(text="Transcribe this voice note verbatim.")
                ],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.0,
                ),
            )
            return response.text.strip() if response.text else ""

        return self._retry(_call)

    # ── Embeddings ────────────────────────────────────────────────────────

    def embed(self, text: str) -> list[float]:
        """
        Generate an embedding vector for a single text.

        Returns:
            List of floats (embedding vector).
        """

        def _call():
            result = self.client.models.embed_content(
                model=self.EMBEDDING_MODEL,
                contents=text,
            )
            return list(result.embeddings[0].values)

        return self._retry(_call)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts in a single API call.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors (one per input text).
        """
        if not texts:
            return []

        def _call():
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.EMBEDDING_MODEL}:batchEmbedContents?key={self.api_key}"
            requests_list = [
                {"model": f"models/{self.EMBEDDING_MODEL}", "content": {"parts": [{"text": t}]}}
                for t in texts
            ]
            response = requests.post(url, json={"requests": requests_list}, timeout=60)
            if response.status_code == 429:
                raise Exception(f"429 RESOURCE_EXHAUSTED: {response.text[:200]}")
            response.raise_for_status()
            data = response.json()
            return [list(e["values"]) for e in data.get("embeddings", [])]

        return self._retry(_call)
