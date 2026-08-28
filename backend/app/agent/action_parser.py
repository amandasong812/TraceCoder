from __future__ import annotations

import json

from pydantic import ValidationError

from app.models import AgentAction


class ActionParseError(ValueError):
    pass


def parse_agent_action(raw: str) -> AgentAction:
    try:
        payload = json.loads(extract_json_object(raw))
        return AgentAction.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ActionParseError(str(exc)) from exc


def extract_json_object(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ActionParseError("No JSON object found in model output.")
    return stripped[start : end + 1]

