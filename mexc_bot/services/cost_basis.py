"""
Cost basis tracking for live trading (mirrors backtest wallet cost basis logic).
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict
import json
import os
import logging

log = logging.getLogger(__name__)


@dataclass
class CostBasisTracker:
    """
    Tracks weighted average cost basis per symbol (like SpotWallet in backtest).
    """
    cost_basis: Dict[str, Decimal] = field(default_factory=dict)  # symbol -> avg price
    total_cost: Dict[str, Decimal] = field(default_factory=dict)  # symbol -> total USDT spent
    total_qty: Dict[str, Decimal] = field(default_factory=dict)  # symbol -> total base qty
    state_file: str | None = None

    def __post_init__(self):
        if self.state_file and os.path.exists(self.state_file):
            self.load()

    def load(self):
        """Load state from file"""
        if not self.state_file:
            return
        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
            self.cost_basis = {k: Decimal(str(v)) for k, v in data.get("cost_basis", {}).items()}
            self.total_cost = {k: Decimal(str(v)) for k, v in data.get("total_cost", {}).items()}
            self.total_qty = {k: Decimal(str(v)) for k, v in data.get("total_qty", {}).items()}
            log.info("Loaded cost basis state: %s symbols", len(self.cost_basis))
        except Exception as e:
            log.warning("Failed to load cost basis: %s", e)

    def save(self):
        """Save state to file"""
        if not self.state_file:
            return
        try:
            data = {
                "cost_basis": {k: str(v) for k, v in self.cost_basis.items()},
                "total_cost": {k: str(v) for k, v in self.total_cost.items()},
                "total_qty": {k: str(v) for k, v in self.total_qty.items()},
            }
            with open(self.state_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.warning("Failed to save cost basis: %s", e)

    def record_buy(self, symbol: str, price: Decimal, usdt_amount: Decimal, base_qty: Decimal):
        """Record a buy (update cost basis)"""
        old_qty = self.total_qty.get(symbol, Decimal("0"))
        old_cost = self.total_cost.get(symbol, Decimal("0"))
        self.total_qty[symbol] = old_qty + base_qty
        self.total_cost[symbol] = old_cost + usdt_amount
        if self.total_qty[symbol] > 0:
            self.cost_basis[symbol] = self.total_cost[symbol] / self.total_qty[symbol]
        log.debug("Recorded BUY %s: price=%s usdt=%s qty=%s avg_cost=%s", 
                 symbol, price, usdt_amount, base_qty, self.cost_basis.get(symbol))

    def record_sell(self, symbol: str, sell_pct: Decimal, actual_sell_qty: Decimal):
        """Record a partial sell (reduce cost basis proportionally)"""
        # Use actual sell qty (from exchange) rather than computed, in case of rounding
        sell_cost = self.total_cost.get(symbol, Decimal("0")) * sell_pct
        self.total_qty[symbol] = self.total_qty.get(symbol, Decimal("0")) - actual_sell_qty
        self.total_cost[symbol] = self.total_cost.get(symbol, Decimal("0")) - sell_cost
        if self.total_qty[symbol] > 0:
            self.cost_basis[symbol] = self.total_cost[symbol] / self.total_qty[symbol]
        else:
            self.cost_basis[symbol] = Decimal("0")
            self.total_cost[symbol] = Decimal("0")
        log.debug("Recorded SELL %s: pct=%s qty=%s remaining_qty=%s remaining_cost=%s", 
                 symbol, sell_pct, actual_sell_qty, self.total_qty.get(symbol), self.total_cost.get(symbol))

    def get_avg_cost(self, symbol: str) -> Decimal:
        """Get average cost basis"""
        return self.cost_basis.get(symbol, Decimal("0"))

    def is_profitable(self, symbol: str, current_price: Decimal, min_profit_pct: Decimal = Decimal("0.05")) -> bool:
        """Check if selling would be profitable"""
        avg_cost = self.get_avg_cost(symbol)
        if avg_cost <= 0:
            return False
        profit_pct = (current_price - avg_cost) / avg_cost
        return profit_pct >= min_profit_pct
