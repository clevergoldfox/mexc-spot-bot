from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, List

from .base import Signal
from ..mexc.client import MexcSpotClient

@dataclass
class H1TrendPullbackParams:
    candles_limit: int = 300
    ema_fast: int = 50
    ema_slow: int = 200
    rsi_period: int = 14
    rsi_buy_max: float = 62.0
    atr_period: int = 14
    min_atr: float = 0.01
    pullback_atr_mult: float = 0.35

def _ema(values: List[float], period: int) -> float:
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e

def _rsi(closes: List[float], period: int) -> float:
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        diff = closes[-i] - closes[-i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses += -diff
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - (100.0 / (1.0 + rs))

def _atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> float:
    trs = []
    for i in range(1, period + 1):
        h = highs[-i]
        l = lows[-i]
        prev = closes[-i - 1]
        trs.append(max(h - l, abs(h - prev), abs(l - prev)))
    return sum(trs) / period

class H1TrendPullbackStrategy:
    name = "h1_trend_pullback"

    def __init__(self, client: MexcSpotClient, params: H1TrendPullbackParams, quote_per_trade: Decimal):
        self.client = client
        self.p = params
        self.quote_per_trade = quote_per_trade

    def generate(self, symbol: str) -> Optional[Signal]:
        kl = self.client.klines(symbol=symbol, interval="1h", limit=self.p.candles_limit)
        if not isinstance(kl, list) or len(kl) < max(self.p.ema_slow, self.p.rsi_period, self.p.atr_period) + 10:
            return None

        closes = [float(x[4]) for x in kl]
        highs  = [float(x[2]) for x in kl]
        lows   = [float(x[3]) for x in kl]

        ema_fast = _ema(closes[-self.p.ema_fast*3:], self.p.ema_fast)
        ema_slow = _ema(closes[-self.p.ema_slow*2:], self.p.ema_slow)
        rsi = _rsi(closes, self.p.rsi_period)
        atr = _atr(highs, lows, closes, self.p.atr_period)

        if atr < self.p.min_atr:
            return None

        if not (ema_fast > ema_slow):
            return None

        close1 = closes[-2]
        if abs(close1 - ema_fast) > atr * self.p.pullback_atr_mult:
            return None

        if rsi > self.p.rsi_buy_max:
            return None

        return Signal(
            side="BUY",
            symbol=symbol,
            reason=f"H1 pullback: EMA{self.p.ema_fast}>{self.p.ema_slow}, RSI={rsi:.1f}, ATR={atr:.4f}",
            size_quote=self.quote_per_trade,
        )
