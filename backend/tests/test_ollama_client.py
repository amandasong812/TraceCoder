import asyncio

import pytest

from app.ollama_client import OllamaClient, OllamaModelError


class FakeOllamaClient(OllamaClient):
    def __init__(self, models: list[str], configured_model: str | None = None) -> None:
        super().__init__("http://testserver", configured_model)
        self._models = models

    async def list_models(self) -> list[str]:
        return self._models


def test_resolve_model_prefers_installed_coder_model() -> None:
    client = FakeOllamaClient(["qwen2.5:1.5b", "qwen3-coder:480b-cloud"])
    assert asyncio.run(client.resolve_model()) == "qwen2.5:1.5b"


def test_resolve_model_prefers_local_model_over_cloud_fallback() -> None:
    client = FakeOllamaClient(["custom-cloud", "local-model"])
    assert asyncio.run(client.resolve_model()) == "local-model"


def test_resolve_model_uses_configured_model_when_installed() -> None:
    client = FakeOllamaClient(["qwen2.5:1.5b"], configured_model="qwen2.5:1.5b")
    assert asyncio.run(client.resolve_model()) == "qwen2.5:1.5b"


def test_resolve_model_rejects_missing_configured_model() -> None:
    client = FakeOllamaClient(["qwen2.5:1.5b"], configured_model="missing:model")
    with pytest.raises(OllamaModelError):
        asyncio.run(client.resolve_model())
