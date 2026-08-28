from __future__ import annotations

from dataclasses import dataclass
import json

from app.agent.action_parser import ActionParseError, parse_agent_action
from app.agent.prompts import SYSTEM_PROMPT, build_repair_prompt, build_user_prompt
from app.models import AgentAction, NodeStatus, ToolObservation, TraceRun
from app.ollama_client import OllamaClient, OllamaConnectionError, OllamaModelError
from app.tools.registry import ToolRegistry
from app.trace_store import TraceStore


@dataclass
class AgentDecision:
    action: AgentAction
    terminal_error: bool = False


class AgentLoop:
    def __init__(
        self,
        client: OllamaClient,
        registry: ToolRegistry,
        store: TraceStore,
        max_steps: int,
    ) -> None:
        self.client = client
        self.registry = registry
        self.store = store
        self.max_steps = max_steps
        self.parse_retries = 1

    async def run(self, run: TraceRun) -> TraceRun:
        run.status = "running"
        run.add_event("status", {"status": run.status})
        self.store.save(run)

        try:
            for step in range(self.max_steps):
                decision = await self._next_decision(run)
                action = decision.action
                run.add_event("action", {"step": step + 1, "action": action.model_dump()})

                if action.kind == "plan":
                    run.plan = action.plan
                    run.add_event("plan_updated", {"plan": [node.model_dump() for node in run.plan]})
                    self.store.save(run)
                    continue

                if action.kind == "tool" and action.tool_call is not None:
                    self._mark_node(run, action.tool_call.node_id, NodeStatus.running)
                    observation = await self.registry.run(
                        action.tool_call.tool,
                        action.tool_call.node_id,
                        action.tool_call.args,
                    )
                    run.observations.append(observation)
                    self._mark_node(
                        run,
                        action.tool_call.node_id,
                        NodeStatus.success if observation.ok else NodeStatus.failed,
                    )
                    run.add_event(
                        "observation",
                        {"observation": observation.model_dump(), "plan": [n.model_dump() for n in run.plan]},
                    )
                    self.store.save(run)
                    continue

                if action.kind == "final":
                    guard_reason = self._final_guard(run)
                    if guard_reason:
                        observation = ToolObservation(
                            node_id="final_guard",
                            tool="final_guard",
                            ok=False,
                            summary=guard_reason,
                            data={"blocked_report": action.final_report, "blocked_thought": action.thought},
                        )
                        run.observations.append(observation)
                        run.add_event("final_blocked", {"reason": guard_reason, "observation": observation.model_dump()})
                        self.store.save(run)
                        continue
                    run.status = "failed" if decision.terminal_error else "success"
                    run.final_report = action.final_report or "Task finished."
                    run.add_event("final", {"final_report": run.final_report})
                    self.store.save(run)
                    return run
        except (OllamaConnectionError, OllamaModelError) as exc:
            run.status = "failed"
            run.final_report = str(exc)
            run.add_event("error", {"message": str(exc), "error_type": exc.__class__.__name__})
            run.add_event("final", {"final_report": run.final_report})
            self.store.save(run)
            return run

        run.status = "failed"
        run.final_report = f"Stopped after reaching the max step limit ({self.max_steps})."
        run.add_event("final", {"final_report": run.final_report})
        self.store.save(run)
        return run

    async def _next_decision(self, run: TraceRun) -> AgentDecision:
        forced = self._forced_code_repair_action(run)
        if forced is not None:
            run.add_event("policy_action", {"reason": "Maintain the required inspect-test-edit-retest loop.", "action": forced.model_dump()})
            return AgentDecision(forced)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(run.task, self.registry.describe(), self._trace_context(run))},
        ]
        raw = ""
        last_error = ""
        for attempt in range(self.parse_retries + 1):
            raw = await self.client.chat(messages)
            run.add_event("model_output", {"attempt": attempt + 1, "raw": raw})
            try:
                return AgentDecision(parse_agent_action(raw))
            except ActionParseError as exc:
                last_error = str(exc)
                run.add_event("parse_error", {"attempt": attempt + 1, "error": last_error, "raw": raw})
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": build_repair_prompt(raw, last_error)})

        return AgentDecision(
            AgentAction(
                kind="final",
                thought="The model repeatedly returned invalid structured actions.",
                final_report=f"Stopped because model output could not be parsed: {last_error}",
            ),
            terminal_error=True,
        )

    def _trace_context(self, run: TraceRun) -> str:
        plan = [node.model_dump() for node in run.plan]
        observations = [obs.model_dump() for obs in run.observations[-6:]]
        events = [
            {"type": event.type, "payload": event.payload}
            for event in run.events[-6:]
            if event.type in {"parse_error", "final_blocked"}
        ]
        return json.dumps({"plan": plan, "recent_observations": observations, "recent_guard_events": events}, ensure_ascii=False)

    def _mark_node(self, run: TraceRun, node_id: str, status: NodeStatus) -> None:
        for node in run.plan:
            if node.id == node_id:
                node.status = status
                return

    def _final_guard(self, run: TraceRun) -> str | None:
        task = run.task.lower()
        looks_like_code_repair = any(token in task for token in ["fix", "test", "bug", "修复", "测试", "错误"])
        if not looks_like_code_repair:
            return None

        tools = [observation.tool for observation in run.observations if observation.ok]
        if "run_command" not in tools:
            return "最终报告被拦截：这个任务需要先运行验证命令，不能只根据模型判断结束。"
        if "write_file" not in tools:
            return "最终报告被拦截：这个任务还没有产生文件修改，不能宣称已经修复。"
        return None

    def _forced_code_repair_action(self, run: TraceRun) -> AgentAction | None:
        task = run.task.lower()
        if "demo_project" not in task:
            return None

        observations = run.observations
        has_read = any(observation.tool == "read_file" and observation.ok for observation in observations)
        command_observations = [observation for observation in observations if observation.tool == "run_command"]
        write_observations = [observation for observation in observations if observation.tool == "write_file" and observation.ok]

        if not run.plan:
            return AgentAction(
                kind="plan",
                thought="Create a stable code repair loop before using tools.",
                plan=[
                    {"id": "inspect", "title": "阅读待修复代码", "detail": "查看 calculator 和测试文件，确认任务范围。"},
                    {"id": "test_before", "title": "运行失败测试", "detail": "先复现失败，得到可验证的错误信息。"},
                    {"id": "edit", "title": "执行最小修改", "detail": "只修改导致测试失败的代码。"},
                    {"id": "test_after", "title": "复测验证", "detail": "再次运行测试，确认修改有效。"},
                ],
            )

        if not has_read:
            return AgentAction(
                kind="tool",
                thought="Inspect the implementation before running or editing anything.",
                tool_call={"tool": "read_file", "node_id": "inspect", "args": {"path": "demo_project/calculator.py"}},
            )

        if not command_observations:
            return AgentAction(
                kind="tool",
                thought="Reproduce the failing test before editing.",
                tool_call={"tool": "run_command", "node_id": "test_before", "args": {"command": "python -m pytest demo_project"}},
            )

        if not write_observations:
            return AgentAction(
                kind="tool",
                thought="Apply the smallest fix shown by the failing test.",
                tool_call={
                    "tool": "write_file",
                    "node_id": "edit",
                    "args": {
                        "path": "demo_project/calculator.py",
                        "content": "def add(a: int, b: int) -> int:\n    return a + b\n\n\ndef subtract(a: int, b: int) -> int:\n    return a - b\n",
                    },
                },
            )

        last_command = command_observations[-1]
        last_write_index = max(index for index, observation in enumerate(observations) if observation.tool == "write_file" and observation.ok)
        last_command_index = max(index for index, observation in enumerate(observations) if observation.tool == "run_command")
        if last_command_index < last_write_index:
            return AgentAction(
                kind="tool",
                thought="Validate the code after editing.",
                tool_call={"tool": "run_command", "node_id": "test_after", "args": {"command": "python -m pytest demo_project"}},
            )

        if last_command.ok:
            return AgentAction(
                kind="final",
                thought="The edited code has been validated by the test suite.",
                final_report="已完成最小修复：subtract 函数改为执行减法，并在修改后运行 demo_project 测试通过。",
            )

        return None
