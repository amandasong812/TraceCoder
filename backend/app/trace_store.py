from __future__ import annotations

import json
from pathlib import Path

from app.models import TraceRun


class TraceStore:
    def __init__(self, trace_dir: Path) -> None:
        self.trace_dir = trace_dir
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self._runs: dict[str, TraceRun] = {}

    def create(self, task: str) -> TraceRun:
        run = TraceRun(task=task)
        run.add_message("user", "用户任务", task, "created")
        run.add_event("created", {"task": task})
        self._runs[run.id] = run
        self.save(run)
        return run

    def get(self, run_id: str) -> TraceRun | None:
        if run_id in self._runs:
            return self._runs[run_id]
        path = self.trace_dir / f"{run_id}.json"
        if not path.exists():
            return None
        run = TraceRun.model_validate_json(path.read_text(encoding="utf-8"))
        self._runs[run.id] = run
        return run

    def save(self, run: TraceRun) -> None:
        self._runs[run.id] = run
        path = self.trace_dir / f"{run.id}.json"
        path.write_text(json.dumps(run.model_dump(), indent=2), encoding="utf-8")

    def list(self) -> list[TraceRun]:
        runs = dict(self._runs)
        for path in self.trace_dir.glob("*.json"):
            run_id = path.stem
            if run_id not in runs:
                runs[run_id] = TraceRun.model_validate_json(path.read_text(encoding="utf-8"))
        ordered = sorted(runs.values(), key=lambda run: run.updated_at, reverse=True)
        self._runs = {run.id: run for run in ordered}
        return ordered
