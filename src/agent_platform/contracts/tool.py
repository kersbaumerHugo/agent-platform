from typing import Any, Protocol


class ToolContract(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    async def invoke(self, arguments: dict[str, Any]) -> dict[str, Any]: ...
