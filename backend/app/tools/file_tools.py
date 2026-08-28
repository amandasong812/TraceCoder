from __future__ import annotations

from app.models import ToolObservation
from app.tools.base import Tool
from app.tools.sandbox import WorkspaceSandbox


class ListFilesTool(Tool):
    name = "list_files"
    description = "List files and directories under a workspace path."
    schema = {"path": "string, optional, defaults to ."}

    def __init__(self, sandbox: WorkspaceSandbox) -> None:
        self.sandbox = sandbox

    async def run(self, node_id: str, args: dict[str, object]) -> ToolObservation:
        path = self.sandbox.resolve(str(args.get("path", ".")))
        if not path.exists():
            return ToolObservation(node_id=node_id, tool=self.name, ok=False, summary="Path does not exist")
        entries = [
            {"name": item.name, "path": self.sandbox.display_path(item), "is_dir": item.is_dir()}
            for item in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        ]
        return ToolObservation(
            node_id=node_id,
            tool=self.name,
            ok=True,
            summary=f"Listed {len(entries)} entries in {self.sandbox.display_path(path) or '.'}",
            data={"entries": entries},
        )


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a UTF-8 text file from the workspace."
    schema = {"path": "string"}

    def __init__(self, sandbox: WorkspaceSandbox) -> None:
        self.sandbox = sandbox

    async def run(self, node_id: str, args: dict[str, object]) -> ToolObservation:
        path = self.sandbox.resolve(str(args["path"]))
        text = path.read_text(encoding="utf-8")
        return ToolObservation(
            node_id=node_id,
            tool=self.name,
            ok=True,
            summary=f"Read {self.sandbox.display_path(path)}",
            data={"path": self.sandbox.display_path(path), "content": text},
        )


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write UTF-8 text to a workspace file, creating parent directories when needed."
    schema = {"path": "string", "content": "string"}

    def __init__(self, sandbox: WorkspaceSandbox) -> None:
        self.sandbox = sandbox

    async def run(self, node_id: str, args: dict[str, object]) -> ToolObservation:
        path = self.sandbox.resolve(str(args["path"]))
        before = path.read_text(encoding="utf-8") if path.exists() else ""
        content = str(args["content"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ToolObservation(
            node_id=node_id,
            tool=self.name,
            ok=True,
            summary=f"Wrote {self.sandbox.display_path(path)}",
            data={"path": self.sandbox.display_path(path), "before": before, "after": content},
        )

