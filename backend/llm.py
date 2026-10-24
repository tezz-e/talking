"""
Talking — Gemini API Wrapper (google-genai SDK)

Provides LLM generation and embedding via the NEW google-genai package.
Includes retry logic with exponential backoff for rate limits.
"""

import os
import time
import logging
from typing import Optional
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
                is_rate_limit = (
                    "429" in error_str
                    or "resource_exhausted" in error_str
                    or "rate" in error_str
                )

                if is_rate_limit and attempt < self.MAX_RETRIES:
                    wait = self.BASE_BACKOFF * (2 ** (attempt - 1))
                    msg = f"[LLM API] Rate limited (attempt {attempt}/{self.MAX_RETRIES}). Retrying in {wait:.1f}s..."
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

    def generate_variants(
        self,
        system_instruction: str,
        user_message: str,
        temperature: float = 0.7,
    ) -> dict[str, str]:
        """
        Generate 3 calibrated energy drafts in one API call:
          - chill: low-effort, casual, relaxed, short (1-6 words)
          - direct: natural, clear, moving conversation forward
          - banter: witty, playful, teasing, or callback banter

        Returns dict with keys: 'chill', 'direct', 'banter'.
        """
        import json
        import re

        prompt = (
            f"{user_message}\n\n"
            "Generate 3 distinct reply options following STYLE.md and the conversation context:\n"
            "1. 'chill': Low-effort, super relaxed, casual, short (1 to 6 words).\n"
            "2. 'direct': Natural, balanced, clear, moving the conversation forward.\n"
            "3. 'banter': Playful, witty, light teasing, or inside-joke / callback energy.\n\n"
            "Output strictly valid JSON with keys: \"chill\", \"direct\", \"banter\"."
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
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
                cleaned = re.sub(r"```$", "", cleaned).strip()
            data = json.loads(cleaned)
            return {
                "chill": str(data.get("chill", "")).strip(),
                "direct": str(data.get("direct", "")).strip(),
                "banter": str(data.get("banter", "")).strip(),
            }
        except Exception as exc:
            logger.warning("Variant JSON parsing failed, using raw output: %s", exc)
            return {"direct": raw.strip(), "chill": "", "banter": ""}

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
