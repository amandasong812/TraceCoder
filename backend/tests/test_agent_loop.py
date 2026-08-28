import asyncio
from pathlib import Path

from app.agent.loop import AgentLoop
from app.models import TraceRun
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
    run = TraceRun(task="test task")
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
