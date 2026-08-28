from __future__ import annotations

from pathlib import Path


class SandboxError(ValueError):
    pass


class WorkspaceSandbox:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def resolve(self, relative_path: str | None = ".") -> Path:
        raw = relative_path or "."
        candidate = (self.root / raw).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise SandboxError(f"Path escapes workspace: {relative_path}")
        return candidate

    def display_path(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

