from __future__ import annotations

import asyncio
import shlex

from app.models import ToolObservation
from app.tools.base import Tool
from app.tools.sandbox import WorkspaceSandbox


class RunCommandTool(Tool):
    name = "run_command"
    description = "Run an allowlisted command in the workspace and capture stdout, stderr, and exit code."
    schema = {"command": "string", "timeout_seconds": "integer, optional"}
    allowed_executables = {"python", "pytest", "pip", "node", "npm"}

    def __init__(self, sandbox: WorkspaceSandbox) -> None:
        self.sandbox = sandbox

    async def run(self, node_id: str, args: dict[str, object]) -> ToolObservation:
        command = str(args["command"])
        timeout = int(args.get("timeout_seconds", 30))
        parts = shlex.split(command, posix=False)
        if not parts:
            raise ValueError("Command is empty")
        executable = parts[0].lower()
        if executable.endswith(".exe"):
            executable = executable[:-4]
        if executable not in self.allowed_executables:
            raise ValueError(f"Command executable is not allowed: {parts[0]}")

        proc = await asyncio.create_subprocess_exec(
            *parts,
            cwd=str(self.sandbox.root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolObservation(
                node_id=node_id,
                tool=self.name,
                ok=False,
                summary=f"Command timed out after {timeout}s",
                data={"command": command, "exit_code": None, "stdout": "", "stderr": "timeout"},
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        return ToolObservation(
            node_id=node_id,
            tool=self.name,
            ok=proc.returncode == 0,
            summary=f"Command exited with {proc.returncode}: {command}",
            data={"command": command, "exit_code": proc.returncode, "stdout": stdout, "stderr": stderr},
        )

