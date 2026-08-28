from __future__ import annotations

import os
from typing import Protocol

import httpx

from app.ollama_client import OllamaClient


class ModelClient(Protocol):
    async def chat(self, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError

    async def status(self) -> dict[str, object]:
        raise NotImplementedError


class ModelProviderError(RuntimeError):
    pass


class OpenAICompatibleClient:
    def __init__(self, base_url: str, model: str, api_key: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    async def chat(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise ModelProviderError(f"OpenAI-compatible chat request failed: {exc}") from exc
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    async def status(self) -> dict[str, object]:
        return {
            "provider": "openai_compatible",
            "base_url": self.base_url,
            "models": [self.model],
            "selected_model": self.model,
            "error": None,
        }


def build_model_client(
    provider: str,
    ollama_base_url: str,
    ollama_model: str | None,
    api_base_url: str | None,
    api_model: str | None,
    api_key: str | None,
) -> ModelClient:
    if provider == "ollama":
        return OllamaClient(ollama_base_url, ollama_model)
    if provider == "openai_compatible":
        if not api_base_url:
            raise ModelProviderError("TRACECODER_API_BASE_URL is required for openai_compatible provider.")
        if not api_model:
            raise ModelProviderError("TRACECODER_API_MODEL is required for openai_compatible provider.")
        if not api_key:
            raise ModelProviderError("TRACECODER_API_KEY is required for openai_compatible provider.")
        return OpenAICompatibleClient(api_base_url, api_model, api_key)
    raise ModelProviderError(f"Unknown model provider: {provider}")


def redact_env_value(name: str) -> str | None:
    value = os.getenv(name)
    if not value:
        return None
    return f"{value[:3]}...{value[-4:]}" if len(value) >= 8 else "***"
