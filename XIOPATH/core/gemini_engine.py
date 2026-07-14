import os
import json
import httpx
import asyncio
import logging
from typing import Dict, Any, List

from core.api_manager import ApiManager

logger = logging.getLogger(__name__)


class GeminiEngine:
    """
    Hybrid Smart LLM Engine (Phase 25: F-18 — Full async httpx).
    Connects to the Gemini REST API directly to avoid Pydantic/Langchain schema bugs.
    Dynamically rotates API keys.

    Provides both sync and async methods:
    - ask() / ask_raw() / get_embedding() — sync (dedicated httpx.Client, no event loop tricks)
    - ask_async() / ask_raw_async() / get_embedding_async() — native async (for API server)
    """
    def __init__(self):
        self.api_manager = ApiManager()
        self.model = "gemini-2.0-flash"
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        self._async_client = httpx.AsyncClient(timeout=30.0)
        self._sync_client = httpx.Client(timeout=30.0)  # Fix 5.1: Dedicated sync client

    # =========================================================================
    # ASYNC METHODS (for FastAPI / async callers)
    # =========================================================================

    async def ask_async(self, system_instruction: str, prompt: str) -> Dict[str, Any]:
        """Async JSON-mode request to Gemini."""
        max_retries = len(self.api_manager.keys) + 2

        payload = {
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        for attempt in range(max_retries):
            current_key = self.api_manager.get_next_key()
            url = f"{self.base_url}/{self.model}:generateContent?key={current_key}"

            try:
                response = await self._async_client.post(
                    url, json=payload, headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    data = response.json()
                    usage = data.get("usageMetadata", {})
                    if usage:
                        self.api_manager.update_tokens(current_key, usage.get("totalTokenCount", 0))

                    text_response = data["candidates"][0]["content"]["parts"][0]["text"]
                    if text_response.startswith("```json"):
                        text_response = text_response.strip("`").replace("json\n", "", 1).strip()

                    return json.loads(text_response)

                elif response.status_code == 429:
                    logger.warning(f"Rate limit on key ...{current_key[-4:]}, rotating...")
                    self.api_manager.mark_cooling(current_key, "quota")
                    continue
                else:
                    logger.warning(f"API Error ({response.status_code}): {response.text}")
                    if response.status_code == 400:
                        self.api_manager.mark_expired(current_key)
                    continue

            except Exception as e:
                logger.error(f"Request exception: {e}")

        raise Exception("GeminiEngine: Exhausted all retries and keys.")

    async def ask_raw_async(self, system_instruction: str, prompt: str) -> str:
        """Async raw text request to Gemini."""
        max_retries = len(self.api_manager.keys) + 2

        payload = {
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.1
            }
        }

        for attempt in range(max_retries):
            current_key = self.api_manager.get_next_key()
            url = f"{self.base_url}/{self.model}:generateContent?key={current_key}"

            try:
                response = await self._async_client.post(
                    url, json=payload, headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    data = response.json()
                    usage = data.get("usageMetadata", {})
                    if usage:
                        self.api_manager.update_tokens(current_key, usage.get("totalTokenCount", 0))

                    return data["candidates"][0]["content"]["parts"][0]["text"]

                elif response.status_code == 429:
                    logger.warning(f"Rate limit on key ...{current_key[-4:]}, rotating...")
                    self.api_manager.mark_cooling(current_key, response.text)
                elif response.status_code in [403, 401]:
                    logger.warning(f"Key ...{current_key[-4:]} expired or invalid. Removing...")
                    self.api_manager.mark_expired(current_key)
                else:
                    logger.warning(f"API Error {response.status_code}: {response.text}")

            except Exception as e:
                logger.error(f"Request Error: {e}")

        raise Exception(f"Gemini API request failed after {max_retries} attempts.")

    async def get_embedding_async(self, text: str) -> List[float]:
        """Async embedding request."""
        max_retries = len(self.api_manager.keys) + 2
        payload = {
            "model": "models/gemini-embedding-001",
            "content": {
                "parts": [{"text": text}]
            }
        }

        for attempt in range(max_retries):
            current_key = self.api_manager.get_next_key()
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={current_key}"

            try:
                response = await self._async_client.post(
                    url, json=payload, headers={"Content-Type": "application/json"}
                )
                if response.status_code == 200:
                    data = response.json()
                    return data["embedding"]["values"]
                elif response.status_code == 429:
                    self.api_manager.mark_cooling(current_key, "quota")
                    continue
                else:
                    logger.warning(f"Embedding API Error ({response.status_code}): {response.text}")
                    if response.status_code == 400:
                        self.api_manager.mark_expired(current_key)
                    continue
            except Exception as e:
                logger.error(f"Embedding exception: {e}")

        raise Exception("GeminiEngine: Exhausted keys while getting embedding.")

    async def close(self):
        """Gracefully close the async HTTP client and flush API key state."""
        await self._async_client.aclose()
        self.api_manager.flush()

    # =========================================================================
    # SYNC METHODS (for CLI / non-async callers — uses dedicated sync client)
    # =========================================================================

    def ask(self, system_instruction: str, prompt: str) -> Dict[str, Any]:
        """Sync JSON-mode request to Gemini using dedicated sync httpx.Client."""
        max_retries = len(self.api_manager.keys) + 2

        payload = {
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        for attempt in range(max_retries):
            current_key = self.api_manager.get_next_key()
            url = f"{self.base_url}/{self.model}:generateContent?key={current_key}"

            try:
                response = self._sync_client.post(
                    url, json=payload, headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    data = response.json()
                    usage = data.get("usageMetadata", {})
                    if usage:
                        self.api_manager.update_tokens(current_key, usage.get("totalTokenCount", 0))

                    text_response = data["candidates"][0]["content"]["parts"][0]["text"]
                    if text_response.startswith("```json"):
                        text_response = text_response.strip("`").replace("json\n", "", 1).strip()

                    return json.loads(text_response)

                elif response.status_code == 429:
                    logger.warning(f"Rate limit on key ...{current_key[-4:]}, rotating...")
                    self.api_manager.mark_cooling(current_key, "quota")
                    continue
                else:
                    logger.warning(f"API Error ({response.status_code}): {response.text}")
                    if response.status_code == 400:
                        self.api_manager.mark_expired(current_key)
                    continue

            except Exception as e:
                logger.error(f"Request exception: {e}")

        raise Exception("GeminiEngine: Exhausted all retries and keys.")

    def ask_raw(self, system_instruction: str, prompt: str) -> str:
        """Sync raw text request to Gemini using dedicated sync httpx.Client."""
        max_retries = len(self.api_manager.keys) + 2

        payload = {
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.1
            }
        }

        for attempt in range(max_retries):
            current_key = self.api_manager.get_next_key()
            url = f"{self.base_url}/{self.model}:generateContent?key={current_key}"

            try:
                response = self._sync_client.post(
                    url, json=payload, headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    data = response.json()
                    usage = data.get("usageMetadata", {})
                    if usage:
                        self.api_manager.update_tokens(current_key, usage.get("totalTokenCount", 0))

                    return data["candidates"][0]["content"]["parts"][0]["text"]

                elif response.status_code == 429:
                    logger.warning(f"Rate limit on key ...{current_key[-4:]}, rotating...")
                    self.api_manager.mark_cooling(current_key, response.text)
                elif response.status_code in [403, 401]:
                    logger.warning(f"Key ...{current_key[-4:]} expired or invalid. Removing...")
                    self.api_manager.mark_expired(current_key)
                else:
                    logger.warning(f"API Error {response.status_code}: {response.text}")

            except Exception as e:
                logger.error(f"Request Error: {e}")

        raise Exception(f"Gemini API request failed after {max_retries} attempts.")

    def get_embedding(self, text: str) -> List[float]:
        """Sync embedding request using dedicated sync httpx.Client."""
        max_retries = len(self.api_manager.keys) + 2
        payload = {
            "model": "models/gemini-embedding-001",
            "content": {
                "parts": [{"text": text}]
            }
        }

        for attempt in range(max_retries):
            current_key = self.api_manager.get_next_key()
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={current_key}"

            try:
                response = self._sync_client.post(
                    url, json=payload, headers={"Content-Type": "application/json"}
                )
                if response.status_code == 200:
                    data = response.json()
                    return data["embedding"]["values"]
                elif response.status_code == 429:
                    self.api_manager.mark_cooling(current_key, "quota")
                    continue
                else:
                    logger.warning(f"Embedding API Error ({response.status_code}): {response.text}")
                    if response.status_code == 400:
                        self.api_manager.mark_expired(current_key)
                    continue
            except Exception as e:
                logger.error(f"Embedding exception: {e}")

        raise Exception("GeminiEngine: Exhausted keys while getting embedding.")

    def close_sync(self):
        """Gracefully close the sync HTTP client."""
        self._sync_client.close()


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculates cosine similarity between two vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm_a = sum(a * a for a in vec1) ** 0.5
    norm_b = sum(b * b for b in vec2) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)
