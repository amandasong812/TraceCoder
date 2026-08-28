from __future__ import annotations

import json

from pydantic import ValidationError

from app.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from app.models import AgentAction, NodeStatus, TraceRun
from app.ollama_client import OllamaClient, OllamaConnectionError, OllamaModelError
from app.tools.registry import ToolRegistry
from app.trace_store import TraceStore


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

    async def run(self, run: TraceRun) -> TraceRun:
        run.status = "running"
        run.add_event("status", {"status": run.status})
        self.store.save(run)

        try:
            for step in range(self.max_steps):
                action = await self._next_action(run)
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
                    run.status = "success"
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

    async def _next_action(self, run: TraceRun) -> AgentAction:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(run.task, self.registry.describe(), self._trace_context(run))},
        ]
        raw = await self.client.chat(messages)
        try:
            payload = json.loads(self._extract_json(raw))
            return AgentAction.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            return AgentAction(
                kind="final",
                thought="The model returned an invalid structured action.",
                final_report=f"Stopped because model output could not be parsed: {exc}",
            )

    def _trace_context(self, run: TraceRun) -> str:
        plan = [node.model_dump() for node in run.plan]
        observations = [obs.model_dump() for obs in run.observations[-6:]]
        return json.dumps({"plan": plan, "recent_observations": observations}, ensure_ascii=False)

    def _mark_node(self, run: TraceRun, node_id: str, status: NodeStatus) -> None:
        for node in run.plan:
            if node.id == node_id:
                node.status = status
                return

    def _extract_json(self, raw: str) -> str:
        stripped = raw.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            return stripped
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object found")
        return stripped[start : end + 1]
