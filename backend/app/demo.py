from __future__ import annotations

from pathlib import Path

from app.tools.sandbox import WorkspaceSandbox


BUGGY_CALCULATOR = """def add(a: int, b: int) -> int:
    return a + b


def subtract(a: int, b: int) -> int:
    return a + b
"""


def reset_demo_project(sandbox: WorkspaceSandbox) -> dict[str, str]:
    path = sandbox.resolve("demo_project/calculator.py")
    path.write_text(BUGGY_CALCULATOR, encoding="utf-8")
    return {"path": sandbox.display_path(path), "status": "reset"}
