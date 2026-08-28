from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent.action_parser import ActionParseError, parse_agent_action
from app.agent.loop import AgentLoop
from app.agent.prompts import SYSTEM_PROMPT
from app.config import get_settings
from app.demo import reset_demo_project
from app.ollama_client import OllamaClient, OllamaConnectionError, OllamaModelError
from app.tools import build_tool_registry
from app.tools.sandbox import WorkspaceSandbox
from app.trace_store import TraceStore


class TaskRequest(BaseModel):
    task: str


class ProbeRequest(BaseModel):
    prompt: str = "Return a two-step plan for checking backend health. Do not call tools."


settings = get_settings()
sandbox = WorkspaceSandbox(settings.workspace_root)
store = TraceStore(settings.trace_dir)
registry = build_tool_registry(sandbox)
client = OllamaClient(settings.ollama_base_url, settings.ollama_model)
agent = AgentLoop(client, registry, store, settings.max_agent_steps)

app = FastAPI(title="TraceCoder API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {"status": "ok", "workspace": str(settings.workspace_root), "configured_model": settings.ollama_model}


@app.get("/api/ollama")
async def ollama_status() -> dict[str, object]:
    try:
        status = await client.status()
    except Exception as exc:
        return {
            "base_url": settings.ollama_base_url,
            "models": [],
            "selected_model": None,
            "error": str(exc),
        }
    return status


@app.post("/api/ollama/probe")
async def ollama_probe(request: ProbeRequest) -> dict[str, object]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{request.prompt}\n\n"
                "Return exactly one JSON plan action. The action must use kind='plan' and include at least one node."
            ),
        },
    ]
    try:
        raw = await client.chat(messages)
    except (OllamaConnectionError, OllamaModelError) as exc:
        return {"ok": False, "raw": "", "error": str(exc)}
    try:
        action = parse_agent_action(raw)
    except ActionParseError as exc:
        return {"ok": False, "raw": raw, "error": str(exc)}
    return {"ok": True, "model": await client.resolve_model(), "raw": raw, "action": action.model_dump()}


@app.get("/api/tools")
async def tools() -> list[dict[str, object]]:
    return registry.describe()


@app.post("/api/uploads")
async def upload_file(file: UploadFile = File(...)) -> dict[str, object]:
    filename = Path(file.filename or "uploaded_file").name
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    target_dir = sandbox.resolve("uploads")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = sandbox.resolve(f"uploads/{filename}")
    content = await file.read()
    target_path.write_bytes(content)
    return {
        "path": sandbox.display_path(target_path),
        "filename": filename,
        "size": len(content),
    }


@app.post("/api/runs")
async def create_run(request: TaskRequest) -> dict[str, str]:
    run = store.create(request.task)
    asyncio.create_task(agent.run(run))
    return {"run_id": run.id}


@app.post("/api/demo/reset")
async def reset_demo() -> dict[str, str]:
    return reset_demo_project(sandbox)


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, object]:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run.model_dump()


@app.get("/api/runs/{run_id}/events")
async def stream_events(run_id: str) -> StreamingResponse:
    async def event_source():
        seen = 0
        while True:
            run = store.get(run_id)
            if run is None:
                yield "event: error\ndata: {\"detail\":\"Run not found\"}\n\n"
                return
            for event in run.events[seen:]:
                yield f"event: {event.type}\ndata: {json.dumps(event.model_dump(), ensure_ascii=False)}\n\n"
            seen = len(run.events)
            if run.status in {"success", "failed"}:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(event_source(), media_type="text/event-stream")
