from typing import Protocol


class ModelContract(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...
