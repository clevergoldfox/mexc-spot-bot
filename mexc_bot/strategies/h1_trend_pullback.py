from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, List

from .base import Signal
from ..mexc.client import MexcSpotClient


# =========================
# Strategy Parameters
# =========================

@dataclass
class H1TrendPullbackParams:
    candles_limit: int = 300
    ema_fast: int = 50
    ema_slow: int = 200
    rsi_period: int = 14
    rsi_buy_max: float = 70.0
    atr_period: int = 14
    min_atr: float = 0.01
    pullback_atr_mult: float = 1.2


# =========================
# Indicator Helpers
# =========================

def _ema(values: List[float], period: int) -> float:
    k = 2.0 / (period + 1.0)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
    return ema


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


# =========================
# Strategy Implementation
# =========================

class H1TrendPullbackStrategy:
    """
    H1 Trend + Pullback strategy
    Designed for both LIVE trading and BACKTESTING
    """

    name = "h1_trend_pullback"

    def __init__(
        self,
        client: Optional[MexcSpotClient],
        params: H1TrendPullbackParams,
        quote_per_trade: Decimal,
    ):
        self.client = client
        self.p = params
        self.quote_per_trade = quote_per_trade

    # -------------------------------------------------
    # Shared core logic (LIVE + BACKTEST)
    # -------------------------------------------------

    def _generate_from_lists(
        self,
        symbol: str,
        closes: List[float],
        highs: List[float],
        lows: List[float],
    ) -> Optional[Signal]:

        if len(closes) < max(
            self.p.ema_slow,
            self.p.rsi_period,
            self.p.atr_period,
        ) + 10:
            return None

        ema_fast = _ema(closes[-self.p.ema_fast * 3 :], self.p.ema_fast)
        ema_slow = _ema(closes[-self.p.ema_slow * 2 :], self.p.ema_slow)
        rsi = _rsi(closes, self.p.rsi_period)
        atr = _atr(highs, lows, closes, self.p.atr_period)

        # --- Volatility filter ---
        if atr < self.p.min_atr:
            return None

        # --- Trend filter ---
        if ema_fast <= ema_slow:
            return None

        # --- Pullback condition ---
        close_prev = closes[-2]
        if abs(close_prev - ema_fast) > atr * self.p.pullback_atr_mult:
            return None

        # --- RSI guard ---
        if rsi > self.p.rsi_buy_max:
            return None

        return Signal(
            side="BUY",
            symbol=symbol,
            reason=(
                f"H1 Pullback | EMA{self.p.ema_fast}>{self.p.ema_slow} "
                f"RSI={rsi:.1f} ATR={atr:.4f}"
            ),
            size_quote=self.quote_per_trade,
        )

    # -------------------------------------------------
    # LIVE trading entry point
    # -------------------------------------------------

    def generate(self, symbol: str) -> Optional[Signal]:
        """
        Live trading signal generation (uses API)
        """
        if not self.client:
            return None

        klines = self.client.klines(
            symbol=symbol,
            interval="60m",
            limit=self.p.candles_limit,
        )

        if not isinstance(klines, list):
            return None

        return self.generate_from_klines(symbol, klines)

    # -------------------------------------------------
    # BACKTEST entry point
    # -------------------------------------------------

    def generate_from_klines(self, symbol: str, klines: list) -> Optional[Signal]:
        """
        Backtest signal generation (uses provided klines)
        """
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]

        return self._generate_from_lists(symbol, closes, highs, lows)
