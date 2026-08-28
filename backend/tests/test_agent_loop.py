import asyncio
from pathlib import Path

from app.agent.loop import AgentLoop
from app.models import ToolObservation, TraceRun
from app.tools.registry import ToolRegistry
from app.trace_store import TraceStore


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    async def chat(self, messages: list[dict[str, str]]) -> str:
        response = self.responses[self.calls]
        self.calls += 1
        return response


def make_loop(tmp_path: Path, responses: list[str]) -> tuple[AgentLoop, TraceRun]:
    store = TraceStore(tmp_path / "traces")
    run = TraceRun(task="say hello")
    loop = AgentLoop(FakeClient(responses), ToolRegistry(), store, max_steps=3)  # type: ignore[arg-type]
    return loop, run


def test_agent_loop_repairs_invalid_model_action(tmp_path: Path) -> None:
    loop, run = make_loop(
        tmp_path,
        [
            "not json",
            '{"kind":"final","final_report":"done"}',
        ],
    )

    result = asyncio.run(loop.run(run))

    assert result.status == "success"
    assert result.final_report == "done"
    assert [event.type for event in result.events].count("parse_error") == 1
    assert [event.type for event in result.events].count("model_output") == 2


def test_agent_loop_records_parse_failure_after_retry(tmp_path: Path) -> None:
    loop, run = make_loop(tmp_path, ["not json", "still not json"])

    result = asyncio.run(loop.run(run))

    assert result.status == "failed"
    assert result.final_report is not None
    assert "could not be parsed" in result.final_report
    assert [event.type for event in result.events].count("parse_error") == 2


def test_agent_loop_blocks_unverified_code_repair_final(tmp_path: Path) -> None:
    loop, run = make_loop(
        tmp_path,
        [
            '{"kind":"final","final_report":"fixed"}',
            '{"kind":"final","final_report":"fixed again"}',
            '{"kind":"final","final_report":"still fixed"}',
        ],
    )
    run.task = "修复失败的测试"

    result = asyncio.run(loop.run(run))

    assert result.status == "failed"
    assert any(event.type == "final_blocked" for event in result.events)
    assert any(observation.tool == "final_guard" for observation in result.observations)


def test_agent_loop_forces_demo_repair_sequence(tmp_path: Path) -> None:
    loop, run = make_loop(tmp_path, [])
    run.task = "修复 demo_project 中失败的测试"

    first = asyncio.run(loop._next_decision(run))
    assert first.action.kind == "plan"

    run.plan = first.action.plan
    second = asyncio.run(loop._next_decision(run))
    assert second.action.tool_call is not None
    assert second.action.tool_call.tool == "read_file"

    run.observations.append(
        ToolObservation(
            node_id="inspect",
            tool="read_file",
            ok=True,
            summary="read",
        )
    )
    third = asyncio.run(loop._next_decision(run))
    assert third.action.tool_call is not None
    assert third.action.tool_call.tool == "run_command"
    assert third.action.tool_call.node_id == "test_before"
