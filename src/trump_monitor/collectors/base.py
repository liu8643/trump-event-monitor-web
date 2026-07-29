from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from trump_monitor.models import RawItem


class SourceError(RuntimeError):
    pass


class SourceAdapter(ABC):
    name: str

    @abstractmethod
    def collect(self, start: datetime, end: datetime) -> list[RawItem]:
        raise NotImplementedError
