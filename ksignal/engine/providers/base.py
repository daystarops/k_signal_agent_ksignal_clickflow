from dataclasses import dataclass
from typing import Any
from ..models import ProviderStatus

@dataclass
class ProviderResult:
    status: ProviderStatus
    items: list[Any]
    failure_mode: str | None = None
    elapsed_ms: int = 0

class ProviderFailure(RuntimeError):
    def __init__(self, failure_mode: str, status: ProviderStatus = ProviderStatus.DOWN):
        super().__init__(failure_mode); self.failure_mode=failure_mode; self.status=status

