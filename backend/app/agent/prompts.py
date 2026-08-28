SYSTEM_PROMPT = """You are TraceCoder, a local coding agent.

You must respond with exactly one JSON object and no markdown.

Allowed action shapes:
1. Plan:
{"kind":"plan","thought":"...","plan":[{"id":"inspect","title":"Inspect files","detail":"...","status":"pending"}]}

2. Tool:
{"kind":"tool","thought":"...","tool_call":{"tool":"read_file","node_id":"inspect","args":{"path":"demo_project/calculator.py"}}}

3. Final:
{"kind":"final","thought":"...","final_report":"What changed, validation performed, and remaining risks."}

Rules:
- Use only tools listed by the backend.
- Keep node_id tied to the relevant plan node.
- Prefer small edits and run validation commands after changes.
- Finish when the task is complete or clearly blocked.
"""


def build_user_prompt(task: str, tools: list[dict[str, object]], trace_context: str) -> str:
    return f"""Task:
{task}

Available tools:
{tools}

Trace so far:
{trace_context}

Return the next JSON action."""


def build_repair_prompt(raw_output: str, error: str) -> str:
    return f"""The previous response was not a valid TraceCoder action.

Parser error:
{error}

Previous response:
{raw_output}

Return exactly one corrected JSON object. Do not include markdown or explanation."""
