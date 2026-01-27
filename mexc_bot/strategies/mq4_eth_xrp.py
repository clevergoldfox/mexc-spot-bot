from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

from .base import Signal
from .h1_trend_pullback import _ema, _rsi, _atr
from ..mexc.client import MexcSpotClient


# =========================
# ETHUSDT H1 (ported from ETHUSD_H1.mq4 / CryptoEA_M30)
# =========================


@dataclass
class EthMq4Params:
    ema_fast: int = 50
    ema_slow: int = 200
    rsi_period: int = 14
    rsi_buy_level: float = 45.0
    rsi_sell_level: float = 55.0
    atr_period: int = 14
    pullback_atr_mult: float = 0.6  # pullbackRange = atr * 0.6


class EthMq4Strategy:
    """
    ETHUSDT H1 strategy ported from MT4 CryptoEA (EMA trend + pullback + RSI reversal).

    This version focuses on ENTRY / EXIT signals, not on lot sizing or broker-specific
    SL/TP placement. Side "BUY" means go long / accumulate; side "SELL" means exit
    (no shorting in spot).
    """

    name = "eth_mq4_h1"

    def __init__(
        self,
        client: Optional[MexcSpotClient],
        params: EthMq4Params,
        quote_per_trade: Decimal,
    ) -> None:
        self.client = client
        self.p = params
        self.quote_per_trade = quote_per_trade

    # --- Core shared logic (arrays) ---

    def _generate_from_lists(
        self,
        symbol: str,
        closes: List[float],
        highs: List[float],
        lows: List[float],
    ) -> Optional[Signal]:
        # Need enough history for EMA/RSI/ATR + a bit of buffer
        need = max(self.p.ema_slow, self.p.rsi_period, self.p.atr_period) + 5
        if len(closes) < need:
            return None

        # Approximate MT4 iMA(..., shift=1/2) using slices
        ema_fast_1 = _ema(closes[-self.p.ema_fast :], self.p.ema_fast)
        ema_fast_2 = _ema(closes[-self.p.ema_fast - 1 : -1], self.p.ema_fast)
        ema_slow_1 = _ema(closes[-self.p.ema_slow :], self.p.ema_slow)

        close_1 = closes[-2]
        close_2 = closes[-3]

        # RSI at bar 1 and 2 (approx)
        rsi_1 = _rsi(closes, self.p.rsi_period)
        rsi_2 = _rsi(closes[:-1], self.p.rsi_period)

        atr = _atr(highs, lows, closes, self.p.atr_period)
        if atr <= 0:
            return None

        # Trend
        up_trend = (ema_fast_1 > ema_slow_1) and (ema_fast_1 > ema_fast_2)
        down_trend = (ema_fast_1 < ema_slow_1) and (ema_fast_1 < ema_fast_2)

        # Pullback
        pullback_range = atr * self.p.pullback_atr_mult
        price_pullback_buy = close_1 <= ema_fast_1 + pullback_range
        price_pullback_sell = close_1 >= ema_fast_1 - pullback_range

        # RSI reversal
        rsi_buy = (
            (rsi_2 < self.p.rsi_buy_level)
            and (rsi_1 > rsi_2)
            and (rsi_1 < 55.0)
        )
        rsi_sell = (
            (rsi_2 > self.p.rsi_sell_level)
            and (rsi_1 < rsi_2)
            and (rsi_1 > 45.0)
        )

        # Final signals (buy-low, sell-high for accumulation)
        # BUY: uptrend + pullback + RSI reversal (buy the dip)
        # More selective: require RSI to be lower (better entry)
        rsi_buy_strict = (
            (rsi_2 < self.p.rsi_buy_level)
            and (rsi_1 > rsi_2)
            and (rsi_1 < 50.0)  # Stricter upper limit
        )
        if up_trend and price_pullback_buy and rsi_buy_strict:
            return Signal(
                side="BUY",
                symbol=symbol,
                reason="ETH MQ4: uptrend + pullback + RSI buy",
                size_quote=self.quote_per_trade,
            )

        # SELL: Only sell when RSI is very high (strongly overbought) to lock in profit
        # Very conservative: require RSI > 70 (extremely overbought) and downtrend confirmed
        # Also require price to be well above EMA fast (strong premium)
        price_premium = close_1 > ema_fast_1 + atr * 0.5  # Price significantly above EMA
        if down_trend and price_pullback_sell and rsi_sell and rsi_1 > 70.0 and price_premium:
            return Signal(
                side="SELL",
                symbol=symbol,
                reason="ETH MQ4: downtrend + pullback + RSI sell (strong overbought)",
                size_quote=self.quote_per_trade,
            )

        return None

    # --- Live entry point (H1 klines) ---

    def generate(self, symbol: str) -> Optional[Signal]:
        if not self.client:
            return None

        klines = self.client.klines(symbol=symbol, interval="60m", limit=300)
        if not isinstance(klines, list):
            return None

        return self.generate_from_klines(symbol, klines)

    # --- Backtest entry point ---

    def generate_from_klines(self, symbol: str, klines: List[list]) -> Optional[Signal]:
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        return self._generate_from_lists(symbol, closes, highs, lows)


# =========================
# XRPUSDT H4 (ported from XRPUSD_H4.mq4)
# =========================


@dataclass
class XrpMq4Params:
    ema_slow: int = 200
    ema_mid: int = 50
    atr_period: int = 14
    rsi_period: int = 14
    dev_atr_mult: float = 3.0
    rsi_oversold: float = 28.0
    rsi_overbought: float = 72.0
    min_atr: float = 0.005


class XrpMq4Strategy:
    """
    XRPUSDT H4 mean-reversion style strategy from MT4 file.

    BUY: close << EMA200 (by ATR*Dev), RSI oversold, EMA50 >= EMA200
    SELL: close >> EMA200 (by ATR*Dev), RSI overbought, EMA50 <= EMA200
    """

    name = "xrp_mq4_h4"

    def __init__(
        self,
        client: Optional[MexcSpotClient],
        params: XrpMq4Params,
        quote_per_trade: Decimal,
    ) -> None:
        self.client = client
        self.p = params
        self.quote_per_trade = quote_per_trade

    def _generate_from_lists(
        self,
        symbol: str,
        closes: List[float],
        highs: List[float],
        lows: List[float],
    ) -> Optional[Signal]:
        need = max(self.p.ema_slow, self.p.rsi_period, self.p.atr_period) + 5
        if len(closes) < need:
            return None

        ema200 = _ema(closes[-self.p.ema_slow :], self.p.ema_slow)
        ema50 = _ema(closes[-self.p.ema_mid :], self.p.ema_mid)
        atr = _atr(highs, lows, closes, self.p.atr_period)
        rsi = _rsi(closes, self.p.rsi_period)
        close = closes[-2]  # use last closed candle

        if atr < self.p.min_atr:
            return None

        # BUY side (buy the dip for accumulation)
        if (
            close < ema200 - atr * self.p.dev_atr_mult
            and rsi < self.p.rsi_oversold
            and ema50 >= ema200
        ):
            return Signal(
                side="BUY",
                symbol=symbol,
                reason="XRP MQ4: deep discount + oversold (buy dip)",
                size_quote=self.quote_per_trade,
            )

        # SELL side (sell the peak, lock in profit)
        # This frees USDT to buy more on next dip, accumulating more over time
        if (
            close > ema200 + atr * self.p.dev_atr_mult
            and rsi > self.p.rsi_overbought
            and ema50 <= ema200
        ):
            return Signal(
                side="SELL",
                symbol=symbol,
                reason="XRP MQ4: premium + overbought (profit-taking)",
                size_quote=self.quote_per_trade,
            )

        return None

    def generate(self, symbol: str) -> Optional[Signal]:
        if not self.client:
            return None

        klines = self.client.klines(symbol=symbol, interval="4h", limit=300)
        if not isinstance(klines, list):
            return None

        return self.generate_from_klines(symbol, klines)

    def generate_from_klines(self, symbol: str, klines: List[list]) -> Optional[Signal]:
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        return self._generate_from_lists(symbol, closes, highs, lows)

