import pytest

from app.model_client import ModelProviderError, OpenAICompatibleClient, build_model_client
from app.ollama_client import OllamaClient


def test_build_model_client_defaults_to_ollama() -> None:
    client = build_model_client("ollama", "http://localhost:11434", None, None, None, None)
    assert isinstance(client, OllamaClient)


def test_build_model_client_requires_api_key_for_openai_compatible() -> None:
    with pytest.raises(ModelProviderError):
        build_model_client("openai_compatible", "http://localhost:11434", None, "https://example.com/v1", "model", None)


def test_build_model_client_creates_openai_compatible_client() -> None:
    client = build_model_client(
        "openai_compatible",
        "http://localhost:11434",
        None,
        "https://example.com/v1",
        "model",
        "secret",
    )
    assert isinstance(client, OpenAICompatibleClient)
