from functools import lru_cache
from pathlib import Path
import os

from pydantic import BaseModel


class Settings(BaseModel):
    workspace_root: Path
    trace_dir: Path
    model_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str | None = None
    api_base_url: str | None = None
    api_model: str | None = None
    api_key: str | None = None
    max_agent_steps: int = 12


@lru_cache
def get_settings() -> Settings:
    repo_root = Path(__file__).resolve().parents[2]
    load_dotenv(repo_root / ".env")
    workspace_root = Path(os.getenv("TRACECODER_WORKSPACE", repo_root)).resolve()
    trace_dir = Path(os.getenv("TRACECODER_TRACE_DIR", repo_root / "traces")).resolve()
    return Settings(
        workspace_root=workspace_root,
        trace_dir=trace_dir,
        model_provider=os.getenv("TRACECODER_MODEL_PROVIDER", "ollama"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=os.getenv("TRACECODER_MODEL"),
        api_base_url=os.getenv("TRACECODER_API_BASE_URL"),
        api_model=os.getenv("TRACECODER_API_MODEL"),
        api_key=os.getenv("TRACECODER_API_KEY"),
        max_agent_steps=int(os.getenv("TRACECODER_MAX_STEPS", "12")),
    )


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
