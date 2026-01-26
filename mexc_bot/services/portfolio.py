from dataclasses import dataclass
from typing import Dict
from decimal import Decimal

@dataclass
class Portfolio:
    free: Dict[str, Decimal]
    locked: Dict[str, Decimal]

    def asset_free(self, asset: str) -> Decimal:
        return self.free.get(asset, Decimal("0"))
