import asyncio
from pathlib import Path

from app.tools.command_tools import RunCommandTool
from app.tools.sandbox import WorkspaceSandbox


def test_normalize_pytest_command_adds_python_module_and_basetemp(tmp_path: Path) -> None:
    tool = RunCommandTool(WorkspaceSandbox(tmp_path))

    assert tool._normalize_command(["pytest", "demo_project"]) == [
        "python",
        "-m",
        "pytest",
        "demo_project",
        "--basetemp",
        ".pytest_tmp",
    ]


def test_run_command_sets_pythonpath_for_workspace_imports(tmp_path: Path) -> None:
    package = tmp_path / "samplepkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "value.py").write_text("VALUE = 42\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_value.py").write_text(
        "from samplepkg.value import VALUE\n\n\ndef test_value() -> None:\n    assert VALUE == 42\n",
        encoding="utf-8",
    )
    tool = RunCommandTool(WorkspaceSandbox(tmp_path))

    observation = asyncio.run(tool.run("verify", {"command": "pytest tests"}))

    assert observation.ok is True
    assert observation.data["command"] == "python -m pytest tests --basetemp .pytest_tmp"
