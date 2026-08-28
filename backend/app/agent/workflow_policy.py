from __future__ import annotations

from dataclasses import dataclass

from app.models import AgentAction, ToolObservation, TraceRun


@dataclass(frozen=True)
class WorkflowState:
    kind: str
    has_plan: bool
    has_read: bool
    has_failed_validation: bool
    has_write: bool
    has_validation_after_write: bool
    last_validation_ok: bool | None
    repeated_action: bool


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str | None = None
    guidance: str | None = None


class WorkflowPolicy:
    def classify(self, task: str) -> str:
        text = task.lower()
        if any(token in text for token in ["fix", "bug", "failing", "修复", "错误", "失败"]):
            return "repair"
        if any(token in text for token in ["test", "pytest", "测试"]):
            return "test"
        if any(token in text for token in ["explain", "summarize", "阅读", "解释", "总结"]):
            return "explain"
        if any(token in text for token in ["refactor", "重构"]):
            return "refactor"
        if any(token in text for token in ["add", "implement", "feature", "新增", "实现"]):
            return "feature"
        return "explore"

    def state(self, run: TraceRun, action: AgentAction | None = None) -> WorkflowState:
        kind = self.classify(run.task)
        observations = run.observations
        write_index = self._last_index(observations, "write_file")
        validation_indices = [index for index, observation in enumerate(observations) if observation.tool == "run_command"]
        last_validation = observations[validation_indices[-1]] if validation_indices else None

        return WorkflowState(
            kind=kind,
            has_plan=bool(run.plan),
            has_read=any(observation.tool in {"list_files", "read_file"} and observation.ok for observation in observations),
            has_failed_validation=any(observation.tool == "run_command" and not observation.ok for observation in observations),
            has_write=write_index is not None,
            has_validation_after_write=write_index is not None and any(index > write_index for index in validation_indices),
            last_validation_ok=last_validation.ok if last_validation is not None else None,
            repeated_action=self._is_repeated_tool_action(run, action),
        )

    def evaluate(self, run: TraceRun, action: AgentAction) -> PolicyDecision:
        state = self.state(run, action)

        if state.repeated_action:
            return PolicyDecision(
                allowed=False,
                reason="检测到重复工具调用，继续执行不会带来新证据。",
                guidance=self.guidance(run),
            )

        if action.kind != "final":
            return PolicyDecision(allowed=True)

        if state.kind in {"repair", "test", "feature", "refactor"}:
            missing = self._missing_completion_evidence(state)
            if missing:
                return PolicyDecision(
                    allowed=False,
                    reason=f"最终报告被拦截：还缺少证据 - {missing}。",
                    guidance=self.guidance(run),
                )

        return PolicyDecision(allowed=True)

    def guidance(self, run: TraceRun) -> str:
        state = self.state(run)
        if not state.has_plan:
            return "先返回 kind=plan，列出 inspect、validate_before、edit、validate_after 等节点。"
        if not state.has_read:
            return "下一步应使用 list_files 或 read_file 收集项目结构和相关代码。"
        if state.kind in {"repair", "test", "feature", "refactor"} and not state.has_failed_validation:
            return "下一步应使用 run_command 运行项目测试或构建，先获得可验证的失败或基线结果。"
        if state.kind in {"repair", "feature", "refactor"} and not state.has_write:
            return "下一步应根据已有证据使用 write_file 做最小必要修改。"
        if state.has_write and not state.has_validation_after_write:
            return "下一步必须使用 run_command 在修改后再次验证。"
        if state.last_validation_ok is False:
            return "验证仍失败，应读取失败信息，继续定位并做最小修改。"
        return "证据已经足够，可以返回 kind=final，总结修改和验证结果。"

    def _missing_completion_evidence(self, state: WorkflowState) -> str | None:
        if not state.has_read:
            return "尚未读取相关文件"
        if not state.has_failed_validation:
            return "尚未运行验证命令获得失败或基线结果"
        if state.kind in {"repair", "feature", "refactor"} and not state.has_write:
            return "尚未修改文件"
        if state.has_write and not state.has_validation_after_write:
            return "修改后尚未复测"
        if state.last_validation_ok is False:
            return "最后一次验证仍然失败"
        return None

    def _is_repeated_tool_action(self, run: TraceRun, action: AgentAction | None) -> bool:
        if action is None or action.kind != "tool" or action.tool_call is None:
            return False
        previous_tools = [observation for observation in run.observations if observation.tool == action.tool_call.tool]
        if not previous_tools:
            return False
        if action.tool_call.tool in {"read_file", "list_files"}:
            requested_path = str(action.tool_call.args.get("path", "."))
            return any(str(observation.data.get("path", ".")) == requested_path for observation in previous_tools)
        return False

    def _last_index(self, observations: list[ToolObservation], tool: str) -> int | None:
        for index in range(len(observations) - 1, -1, -1):
            if observations[index].tool == tool and observations[index].ok:
                return index
        return None
