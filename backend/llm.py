"""
Talking — Gemini API Wrapper (google-genai SDK)

Provides LLM generation and embedding via the NEW google-genai package.
Includes retry logic with exponential backoff for rate limits.
"""

import os
import time
import logging
from typing import Optional
from pathlib import Path
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
    Supports a comma-separated list of keys for automatic rate-limit rotation.
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
        self.model = model or self.DEFAULT_MODEL
        self.last_provider_used = "gemini"
        
        # Load API keys from environment
        self.api_keys = []
        self.groq_api_keys = []
        self.groq_api_key = ""
        self._reload_keys_from_env(initial=True)
        
        if api_key:
            # If explicit API key passed, use it primarily
            self.api_keys = [api_key]
            self.current_key_index = 0
            self.api_key = api_key
            self.client = genai.Client(api_key=self.api_key)
            
        logger.info("GeminiLLM initialized — model=%s, keys_count=%d, groq_keys_count=%d", self.model, len(self.api_keys), len(self.groq_api_keys))

    def _reload_keys_from_env(self, initial: bool = False) -> None:
        """Reload GEMINI_API_KEY / GEMINI_API_KEYS from the .env file dynamically."""
        try:
            from dotenv import load_dotenv
            base_dir = Path(__file__).resolve().parent.parent
            env_path = base_dir / ".env"
            if env_path.exists():
                load_dotenv(dotenv_path=env_path, override=True)
        except Exception as e:
            logger.warning("Could not reload dotenv dynamically: %s", e)

        api_key_str = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEYS", "")
        
        new_keys = []
        if "," in api_key_str:
            new_keys = [k.strip() for k in api_key_str.split(",") if k.strip()]
        elif api_key_str.strip():
            new_keys = [api_key_str.strip()]

        if not new_keys and initial:
            raise ValueError(
                "Gemini API key is required. Set GEMINI_API_KEY in .env "
                "or pass api_key= to GeminiLLM()."
            )

        # Reload Groq settings dynamically
        groq_str = os.environ.get("GROQ_API_KEY", "") or os.environ.get("GROQ_API_KEYS", "")
        new_groq_keys = []
        if "," in groq_str:
            new_groq_keys = [k.strip() for k in groq_str.split(",") if k.strip()]
        elif groq_str.strip():
            new_groq_keys = [groq_str.strip()]
            
        self.groq_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

        if new_groq_keys and new_groq_keys != self.groq_api_keys:
            msg = f"[LLM API] Detected change in Groq API keys in .env. Loaded {len(new_groq_keys)} keys."
            print(msg)
            logger.info(msg)
            self.groq_api_keys = new_groq_keys
            self.current_groq_index = 0
            self.groq_api_key = self.groq_api_keys[0]
        elif not new_groq_keys:
            self.groq_api_keys = []
            self.groq_api_key = ""
            self.current_groq_index = 0

        if new_keys and new_keys != self.api_keys:
            msg = f"[LLM API] Detected change in API keys in .env. Loaded {len(new_keys)} keys."
            print(msg)
            logger.info(msg)
            self.api_keys = new_keys
            # Reset rotation index
            self.current_key_index = 0
            self.api_key = self.api_keys[0]
            self.client = genai.Client(api_key=self.api_key)

    def _rotate_key(self) -> bool:
        """Rotate to the next API key in the list. Returns True if rotated, False otherwise."""
        if len(self.api_keys) <= 1:
            return False
        
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        self.api_key = self.api_keys[self.current_key_index]
        self.client = genai.Client(api_key=self.api_key)
        
        masked_key = f"...{self.api_key[-5:]}" if len(self.api_key) > 5 else "..."
        msg = f"[LLM API] Rotated to API key index {self.current_key_index} (ending in {masked_key})"
        print(msg)
        logger.info(msg)
        return True

    def _rotate_groq_key(self) -> bool:
        """Rotate to the next Groq API key in the list. Returns True if rotated, False otherwise."""
        if len(self.groq_api_keys) <= 1:
            return False
        
        self.current_groq_index = (self.current_groq_index + 1) % len(self.groq_api_keys)
        self.groq_api_key = self.groq_api_keys[self.current_groq_index]
        
        masked_key = f"...{self.groq_api_key[-5:]}" if len(self.groq_api_key) > 5 else "..."
        msg = f"[LLM API] Rotated to Groq API key index {self.current_groq_index} (ending in {masked_key})"
        print(msg)
        logger.info(msg)
        return True


    # ── Retry helper ──────────────────────────────────────────────────────

    def _retry(self, fn, *args, **kwargs):
        """
        Execute `fn` with key rotation and exponential backoff on rate-limit (429) errors.
        """
        keys_tried = 0
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                # Reload env to pick up any runtime edits to .env file before making the call
                self._reload_keys_from_env()
                return fn(*args, **kwargs)
            except Exception as exc:
                error_str = str(exc).lower()
                is_rate_limit = (
                    "429" in error_str
                    or "resource_exhausted" in error_str
                    or "rate" in error_str
                )

                if is_rate_limit:
                    # Check if we have alternative keys to rotate to
                    if keys_tried < len(self.api_keys) - 1:
                        if self._rotate_key():
                            keys_tried += 1
                            msg = f"[LLM API] Rate limit hit. Rotated API key. Retrying immediately..."
                            print(msg)
                            logger.warning(msg)
                            continue

                    # If we tried all Gemini keys and we have a Groq fallback available, raise immediately
                    if self.groq_api_key:
                        msg = "[LLM API] All Gemini keys rate-limited. Raising error to trigger Groq fallback instantly..."
                        print(msg)
                        logger.warning(msg)
                        raise exc

                    # Otherwise, backoff and retry
                    if attempt < self.MAX_RETRIES:
                        keys_tried = 0  # reset for next attempt
                        wait = self.BASE_BACKOFF * (2 ** (attempt - 1))
                        msg = f"[LLM API] All keys rate limited. Retrying in {wait:.1f}s (attempt {attempt}/{self.MAX_RETRIES})..."
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
        provider_mode: str = "auto",
    ) -> str:
        """
        Single-turn generation with a system instruction.

        Args:
            system_instruction: The system prompt.
            user_message:       The user's input.
            temperature:        Sampling temperature (0-2).
            provider_mode:      Provider mode ('auto', 'gemini', 'groq').

        Returns:
            The model's text response.
        """
        if provider_mode == "groq":
            self.last_provider_used = "groq"
            if not self.groq_api_key:
                raise ValueError("No Groq API key is configured in the environment.")
            return self._generate_via_groq(system_instruction, user_message, temperature)

        self.last_provider_used = "gemini"

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

        try:
            return self._retry(_call)
        except Exception as exc:
            if provider_mode == "auto" and self.groq_api_key:
                self.last_provider_used = "groq"
                msg = f"[LLM API] Gemini generate failed. Falling back to Groq ({self.groq_model})..."
                print(msg)
                logger.warning(msg)
                return self._generate_via_groq(system_instruction, user_message, temperature)
            raise

    def generate_with_google_search(
        self,
        system_instruction: str,
        user_message: str,
        temperature: float = 0.1,
        provider_mode: str = "auto",
    ) -> tuple[str, bool]:
        """
        Generate with Google Search grounding enabled.

        Returns:
            (response_text, had_grounding_metadata)
        """
        if provider_mode == "groq":
            self.last_provider_used = "groq"
            if not self.groq_api_key:
                raise ValueError("No Groq API key is configured in the environment.")
            text = self._generate_via_groq(system_instruction, user_message, temperature)
            return text, False

        self.last_provider_used = "gemini"

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

        try:
            return self._retry(_call)
        except Exception as exc:
            if provider_mode == "auto" and self.groq_api_key:
                self.last_provider_used = "groq"
                msg = f"[LLM API] Gemini search grounding failed. Falling back to Groq without grounding..."
                print(msg)
                logger.warning(msg)
                text = self._generate_via_groq(system_instruction, user_message, temperature)
                return text, False
            raise

    def generate_chat(
        self,
        system_instruction: str,
        history: list[dict],
        new_message: str,
        temperature: float = 0.8,
        provider_mode: str = "auto",
    ) -> str:
        """
        Multi-turn chat generation.

        Replays the conversation history then sends the new message.

        Args:
            system_instruction: The system prompt.
            history:            List of {'role': 'user'|'model', 'parts': [str]}.
            new_message:        The latest user message.
            temperature:        Sampling temperature.
            provider_mode:      Provider mode ('auto', 'gemini', 'groq').

        Returns:
            The model's text response.
        """
        if provider_mode == "groq":
            self.last_provider_used = "groq"
            if not self.groq_api_key:
                raise ValueError("No Groq API key is configured in the environment.")
            return self._generate_chat_via_groq(system_instruction, history, new_message, temperature)

        self.last_provider_used = "gemini"

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

        try:
            return self._retry(_call)
        except Exception as exc:
            if provider_mode == "auto" and self.groq_api_key:
                self.last_provider_used = "groq"
                msg = f"[LLM API] Gemini generate_chat failed. Falling back to Groq ({self.groq_model})..."
                print(msg)
                logger.warning(msg)
                return self._generate_chat_via_groq(system_instruction, history, new_message, temperature)
            raise


    def _groq_request(self, payload: dict) -> dict:
        """Execute a Groq API request with key rotation on 429 rate limit errors."""
        url = "https://api.groq.com/openai/v1/chat/completions"
        max_groq_retries = 5
        groq_keys_tried = 0
        
        for attempt in range(1, max_groq_retries + 1):
            # Ensure we reload env variables in case of changes
            self._reload_keys_from_env()
            if not self.groq_api_key:
                raise Exception("No Groq API key configured.")

            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=30)
                
                if response.status_code == 429:
                    # Rate limit hit, try rotating
                    if groq_keys_tried < len(self.groq_api_keys) - 1:
                        if self._rotate_groq_key():
                            groq_keys_tried += 1
                            continue
                            
                    # If all Groq keys are exhausted, sleep and try again
                    if attempt < max_groq_retries:
                        groq_keys_tried = 0  # reset for next attempt
                        wait = 2.0 * (2 ** (attempt - 1))
                        msg = f"[LLM API] All Groq keys rate limited. Retrying in {wait:.1f}s..."
                        print(msg)
                        logger.warning(msg)
                        time.sleep(wait)
                        continue
                        
                if response.status_code != 200:
                    err_msg = f"API Error {response.status_code}: {response.text}"
                    raise Exception(err_msg)
                    
                return response.json()
            except Exception as e:
                if attempt == max_groq_retries:
                    raise e
                # Rotate key on network errors as well
                if groq_keys_tried < len(self.groq_api_keys) - 1:
                    if self._rotate_groq_key():
                        groq_keys_tried += 1
                        continue
                raise e


    def _generate_via_groq(
        self,
        system_instruction: str,
        user_message: str,
        temperature: float = 0.8,
    ) -> str:
        """Helper to generate text using the Groq API with key rotation."""
        payload = {
            "model": self.groq_model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_message}
            ],
            "temperature": temperature
        }
        try:
            data = self._groq_request(payload)
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            err_msg = f"[LLM API] Groq fallback failed: {e}"
            print(err_msg)
            logger.error(err_msg)
            raise Exception(err_msg) from e

    def _generate_chat_via_groq(
        self,
        system_instruction: str,
        history: list[dict],
        new_message: str,
        temperature: float = 0.8,
    ) -> str:
        """Helper to run a multi-turn chat using the Groq API with key rotation."""
        messages = [{"role": "system", "content": system_instruction}]
        
        for msg in history:
            role = msg.get("role", "user")
            mapped_role = "assistant" if role == "model" else "user"
            text = msg.get("parts", [msg.get("content", "")])[0] if isinstance(msg.get("parts"), list) else msg.get("parts", msg.get("content", ""))
            messages.append({"role": mapped_role, "content": text})
            
        messages.append({"role": "user", "content": new_message})
        
        payload = {
            "model": self.groq_model,
            "messages": messages,
            "temperature": temperature
        }
        try:
            data = self._groq_request(payload)
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            err_msg = f"[LLM API] Groq fallback chat failed: {e}"
            print(err_msg)
            logger.error(err_msg)
            raise Exception(err_msg) from e




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
