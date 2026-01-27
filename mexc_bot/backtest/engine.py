# mexc_bot/backtest/engine.py
from decimal import Decimal
from typing import List
from mexc_bot.backtest.simulator import SpotWallet

class BacktestEngine:
    def __init__(self, wallet: SpotWallet, strategy, trade_usdt: Decimal):
        self.wallet = wallet
        self.strategy = strategy
        self.trade_usdt = trade_usdt

    def generate_from_klines(self, symbol: str, klines: list):
        """
        klines: historical candles up to now
        """
        # extract OHLC
        closes = [float(k[4]) for k in klines]
        highs  = [float(k[2]) for k in klines]
        lows   = [float(k[3]) for k in klines]

        print(
            f"{symbol} | close={close1:.4f} "
            f"ema50={ema_fast:.4f} ema200={ema_slow:.4f} "
            f"atr={atr:.4f} rsi={rsi:.1f}"
        )

        # reuse same indicator logic
        return self._generate_signal_from_arrays(closes, highs, lows)


    def run(self, symbol: str, klines: List[list]):
        """
        Replay candles one by one
        """
        for i in range(200, len(klines)):
            window = klines[:i]
            candle = klines[i]

            ts = candle[0]
            close_price = Decimal(candle[4])

            signal = self.strategy.generate_from_klines(symbol, window)

            if signal == "BUY":
                self.wallet.buy(symbol, close_price, self.trade_usdt, ts)

            elif signal == "SELL":
                self.wallet.sell_all(symbol, close_price, ts)
