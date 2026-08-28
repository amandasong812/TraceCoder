from __future__ import annotations

from app.models import ToolObservation
from app.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def describe(self) -> list[dict[str, object]]:
        return [
            {"name": tool.name, "description": tool.description, "schema": tool.schema}
            for tool in self._tools.values()
        ]

    async def run(self, tool_name: str, node_id: str, args: dict[str, object]) -> ToolObservation:
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolObservation(
                node_id=node_id,
                tool=tool_name,
                ok=False,
                summary=f"Unknown tool: {tool_name}",
            )
        try:
            return await tool.run(node_id, args)
        except Exception as exc:
            return ToolObservation(
                node_id=node_id,
                tool=tool_name,
                ok=False,
                summary=str(exc),
                data={"error_type": exc.__class__.__name__},
            )

