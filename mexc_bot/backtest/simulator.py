# mexc_bot/backtest/simulator.py
from decimal import Decimal
from typing import Dict, List

class SpotWallet:
    def __init__(self, initial_usdt: Decimal):
        self.usdt = initial_usdt
        self.assets: Dict[str, Decimal] = {}
        self.trades: List[dict] = []
        # Track cost basis for each asset (weighted average)
        self.cost_basis: Dict[str, Decimal] = {}  # symbol -> average buy price
        self.total_cost: Dict[str, Decimal] = {}  # symbol -> total USDT spent

    def buy(self, symbol: str, price: Decimal, usdt_amount: Decimal, ts: int):
        if self.usdt < usdt_amount:
            return

        base = symbol.replace("USDT", "")
        qty = usdt_amount / price
        old_qty = self.assets.get(base, Decimal("0"))
        old_cost = self.total_cost.get(symbol, Decimal("0"))

        self.usdt -= usdt_amount
        self.assets[base] = old_qty + qty
        
        # Update cost basis (weighted average)
        self.total_cost[symbol] = old_cost + usdt_amount
        if self.assets[base] > 0:
            self.cost_basis[symbol] = self.total_cost[symbol] / self.assets[base]

        self.trades.append({
            "time": ts,
            "side": "BUY",
            "symbol": symbol,
            "price": price,
            "qty": qty,
            "usdt": self.usdt
        })

    def sell_all(self, symbol: str, price: Decimal, ts: int):
        base = symbol.replace("USDT", "")
        qty = self.assets.get(base, Decimal("0"))

        if qty <= 0:
            return

        self.usdt += qty * price
        self.assets[base] = Decimal("0")

        self.trades.append({
            "time": ts,
            "side": "SELL",
            "symbol": symbol,
            "price": price,
            "qty": qty,
            "usdt": self.usdt
        })

    def sell_partial(self, symbol: str, price: Decimal, sell_pct: Decimal, ts: int):
        """
        Sell a percentage of holdings (0.0 to 1.0)
        e.g., sell_pct=0.5 means sell 50% of holdings
        """
        base = symbol.replace("USDT", "")
        total_qty = self.assets.get(base, Decimal("0"))

        if total_qty <= 0:
            return

        sell_qty = total_qty * sell_pct
        if sell_qty <= 0:
            return

        # Update cost basis proportionally
        sell_cost = self.total_cost.get(symbol, Decimal("0")) * sell_pct
        self.total_cost[symbol] = self.total_cost.get(symbol, Decimal("0")) - sell_cost
        
        self.usdt += sell_qty * price
        self.assets[base] = total_qty - sell_qty
        
        # Recalculate cost basis
        if self.assets[base] > 0:
            self.cost_basis[symbol] = self.total_cost[symbol] / self.assets[base]
        else:
            self.cost_basis[symbol] = Decimal("0")

        self.trades.append({
            "time": ts,
            "side": "SELL",
            "symbol": symbol,
            "price": price,
            "qty": sell_qty,
            "usdt": self.usdt
        })
    
    def get_avg_cost(self, symbol: str) -> Decimal:
        """Get average cost basis for an asset"""
        return self.cost_basis.get(symbol, Decimal("0"))
    
    def is_profitable(self, symbol: str, current_price: Decimal, min_profit_pct: Decimal = Decimal("0.05")) -> bool:
        """
        Check if selling would be profitable
        min_profit_pct: minimum profit percentage required (e.g., 0.05 = 5%)
        """
        avg_cost = self.get_avg_cost(symbol)
        if avg_cost <= 0:
            return False
        profit_pct = (current_price - avg_cost) / avg_cost
        return profit_pct >= min_profit_pct
