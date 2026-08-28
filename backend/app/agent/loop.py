from __future__ import annotations

from dataclasses import dataclass
import json

from app.agent.action_parser import ActionParseError, parse_agent_action
from app.agent.prompts import SYSTEM_PROMPT, build_repair_prompt, build_user_prompt
from app.agent.workflow_policy import WorkflowPolicy
from app.model_client import ModelProviderError
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
        self.policy = WorkflowPolicy()

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
                    policy_decision = self.policy.evaluate(run, action)
                    if not policy_decision.allowed:
                        observation = ToolObservation(
                            node_id="final_guard",
                            tool="final_guard",
                            ok=False,
                            summary=policy_decision.reason or "最终报告被拦截：证据不足。",
                            data={
                                "blocked_report": action.final_report,
                                "blocked_thought": action.thought,
                                "guidance": policy_decision.guidance,
                            },
                        )
                        run.observations.append(observation)
                        run.add_event(
                            "final_blocked",
                            {"reason": observation.summary, "guidance": policy_decision.guidance, "observation": observation.model_dump()},
                        )
                        self.store.save(run)
                        continue
                    run.status = "failed" if decision.terminal_error else "success"
                    run.final_report = action.final_report or "Task finished."
                    run.add_event("final", {"final_report": run.final_report})
                    self.store.save(run)
                    return run
        except (OllamaConnectionError, OllamaModelError, ModelProviderError) as exc:
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
                action = parse_agent_action(raw)
                policy_decision = self.policy.evaluate(run, action)
                if policy_decision.allowed:
                    return AgentDecision(action)
                run.add_event(
                    "policy_blocked",
                    {"reason": policy_decision.reason, "guidance": policy_decision.guidance, "action": action.model_dump()},
                )
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": self._policy_repair_prompt(policy_decision)})
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
        workflow = self.policy.state(run). __dict__
        events = [
            {"type": event.type, "payload": event.payload}
            for event in run.events[-6:]
            if event.type in {"parse_error", "final_blocked"}
        ]
        return json.dumps(
            {
                "workflow": workflow,
                "next_step_guidance": self.policy.guidance(run),
                "plan": plan,
                "recent_observations": observations,
                "recent_guard_events": events,
            },
            ensure_ascii=False,
        )

    def _mark_node(self, run: TraceRun, node_id: str, status: NodeStatus) -> None:
        for node in run.plan:
            if node.id == node_id:
                node.status = status
                return

    def _policy_repair_prompt(self, decision) -> str:
        return f"""The previous action was blocked by the workflow policy.

Reason:
{decision.reason}

Required next step:
{decision.guidance}

Return exactly one corrected JSON action that follows this requirement."""
