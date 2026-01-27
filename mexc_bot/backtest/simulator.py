# mexc_bot/backtest/simulator.py
from decimal import Decimal
from typing import Dict, List

class SpotWallet:
    def __init__(self, initial_usdt: Decimal):
        self.usdt = initial_usdt
        self.assets: Dict[str, Decimal] = {}
        self.trades: List[dict] = []

    def buy(self, symbol: str, price: Decimal, usdt_amount: Decimal, ts: int):
        if self.usdt < usdt_amount:
            return

        base = symbol.replace("USDT", "")
        qty = usdt_amount / price

        self.usdt -= usdt_amount
        self.assets[base] = self.assets.get(base, Decimal("0")) + qty

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
