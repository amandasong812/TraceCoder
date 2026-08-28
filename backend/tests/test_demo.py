from app.demo import BUGGY_CALCULATOR, reset_demo_project
from app.tools.sandbox import WorkspaceSandbox


def test_reset_demo_project_restores_buggy_fixture(tmp_path) -> None:
    demo_dir = tmp_path / "demo_project"
    demo_dir.mkdir()
    calculator = demo_dir / "calculator.py"
    calculator.write_text("changed", encoding="utf-8")

    result = reset_demo_project(WorkspaceSandbox(tmp_path))

    assert result == {"path": "demo_project/calculator.py", "status": "reset"}
    assert calculator.read_text(encoding="utf-8") == BUGGY_CALCULATOR
