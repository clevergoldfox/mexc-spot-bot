from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Optional

@dataclass
class Signal:
    side: str
    symbol: str
    reason: str
    size_quote: Decimal

class Strategy(Protocol):
    name: str
    def generate(self, symbol: str) -> Optional[Signal]:
        ...
