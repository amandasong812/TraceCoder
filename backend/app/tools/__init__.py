from app.tools.command_tools import RunCommandTool
from app.tools.file_tools import ListFilesTool, ReadFileTool, WriteFileTool
from app.tools.registry import ToolRegistry
from app.tools.sandbox import WorkspaceSandbox


def build_tool_registry(sandbox: WorkspaceSandbox) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ListFilesTool(sandbox))
    registry.register(ReadFileTool(sandbox))
    registry.register(WriteFileTool(sandbox))
    registry.register(RunCommandTool(sandbox))
    return registry

