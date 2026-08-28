from __future__ import annotations

import httpx


PREFERRED_MODELS = ["qwen2.5-coder:7b", "qwen3-coder:480b-cloud", "qwen2.5:1.5b"]


class OllamaConnectionError(RuntimeError):
    pass


class OllamaModelError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str, model: str | None = None, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaConnectionError(f"Could not connect to Ollama at {self.base_url}: {exc}") from exc

        data = response.json()
        return [model["name"] for model in data.get("models", []) if "name" in model]

    async def resolve_model(self) -> str:
        models = await self.list_models()
        if self.model:
            if self.model not in models:
                raise OllamaModelError(f"Configured model is not installed: {self.model}. Installed models: {models}")
            return self.model
        for preferred in PREFERRED_MODELS:
            if preferred in models:
                self.model = preferred
                return preferred
        if not models:
            raise OllamaModelError("No Ollama models are installed.")
        self.model = models[0]
        return self.model

    async def status(self) -> dict[str, object]:
        models = await self.list_models()
        selected = None
        error = None
        try:
            selected = await self.resolve_model()
        except OllamaModelError as exc:
            error = str(exc)
        return {"base_url": self.base_url, "models": models, "selected_model": selected, "error": error}

    async def chat(self, messages: list[dict[str, str]]) -> str:
        model = await self.resolve_model()
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise OllamaConnectionError(f"Ollama chat request failed: {exc}") from exc
        return data.get("message", {}).get("content", "")
