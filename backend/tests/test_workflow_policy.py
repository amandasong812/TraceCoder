from app.agent.workflow_policy import WorkflowPolicy
from app.models import AgentAction, ToolObservation, TraceRun


def test_repair_workflow_blocks_final_without_validation() -> None:
    run = TraceRun(task="修复失败的测试")
    action = AgentAction(kind="final", final_report="done")

    decision = WorkflowPolicy().evaluate(run, action)

    assert decision.allowed is False
    assert "尚未读取相关文件" in (decision.reason or "")


def test_repair_workflow_allows_final_after_write_and_passing_validation() -> None:
    run = TraceRun(task="fix failing tests")
    run.observations.extend(
        [
            ToolObservation(node_id="inspect", tool="read_file", ok=True, summary="read"),
            ToolObservation(node_id="validate_before", tool="run_command", ok=False, summary="failed"),
            ToolObservation(node_id="edit", tool="write_file", ok=True, summary="wrote"),
            ToolObservation(node_id="validate_after", tool="run_command", ok=True, summary="passed"),
        ]
    )
    action = AgentAction(kind="final", final_report="done")

    decision = WorkflowPolicy().evaluate(run, action)

    assert decision.allowed is True


def test_explain_workflow_allows_final_without_write() -> None:
    run = TraceRun(task="阅读 README.md 并总结")
    run.observations.append(ToolObservation(node_id="inspect", tool="read_file", ok=True, summary="read"))
    action = AgentAction(kind="final", final_report="summary")

    decision = WorkflowPolicy().evaluate(run, action)

    assert decision.allowed is True
