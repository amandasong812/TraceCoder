from functools import lru_cache
from pathlib import Path
import os

from pydantic import BaseModel


class Settings(BaseModel):
    workspace_root: Path
    trace_dir: Path
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str | None = None
    max_agent_steps: int = 12


@lru_cache
def get_settings() -> Settings:
    repo_root = Path(__file__).resolve().parents[2]
    workspace_root = Path(os.getenv("TRACECODER_WORKSPACE", repo_root)).resolve()
    trace_dir = Path(os.getenv("TRACECODER_TRACE_DIR", repo_root / "traces")).resolve()
    return Settings(
        workspace_root=workspace_root,
        trace_dir=trace_dir,
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=os.getenv("TRACECODER_MODEL"),
        max_agent_steps=int(os.getenv("TRACECODER_MAX_STEPS", "12")),
    )
