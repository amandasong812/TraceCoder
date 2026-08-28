from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models import ToolObservation


class Tool(ABC):
    name: str
    description: str
    schema: dict[str, Any]

    @abstractmethod
    async def run(self, node_id: str, args: dict[str, Any]) -> ToolObservation:
        raise NotImplementedError

