from pathlib import Path

import pytest

from app.tools.sandbox import SandboxError, WorkspaceSandbox


def test_resolve_allows_workspace_child(tmp_path: Path) -> None:
    sandbox = WorkspaceSandbox(tmp_path)
    assert sandbox.resolve("src/app.py") == tmp_path / "src" / "app.py"


def test_resolve_rejects_parent_escape(tmp_path: Path) -> None:
    sandbox = WorkspaceSandbox(tmp_path)
    with pytest.raises(SandboxError):
        sandbox.resolve("../outside.txt")

