# mexc_bot/backtest/engine.py
from decimal import Decimal
from typing import List
from mexc_bot.backtest.simulator import SpotWallet
from mexc_bot.strategies.base import Signal

class BacktestEngine:
    COOLDOWN_BARS = 24         # Min bars between opposite-side trades (ETH H1: 24 = 1 day)
    ETH_BUY_SPACING_BARS = 12  # Min bars between consecutive ETH BUYs (avoid clustering)
    ETH_SELL_SPACING_BARS = 6  # Min bars between consecutive ETH SELLs (avoid churning)

    def __init__(self, wallet: SpotWallet, strategy, trade_usdt: Decimal):
        self.wallet = wallet
        self.strategy = strategy
        self.trade_usdt = trade_usdt

    def run(self, symbol: str, klines: List[list]):
        """
        Replay candles one by one
        """
        last_buy_bar = -9999
        last_sell_bar = -9999

        for i in range(200, len(klines)):
            window = klines[:i]
            candle = klines[i]

            ts = candle[0]
            close_price = Decimal(candle[4])

            signal = self.strategy.generate_from_klines(symbol, window)

            if signal and signal.side == "BUY":
                if symbol == "ETHUSDT":
                    if (i - last_sell_bar) < self.COOLDOWN_BARS:
                        continue
                    if (i - last_buy_bar) < self.ETH_BUY_SPACING_BARS:
                        continue
                usdt_amount = signal.size_quote if signal.size_quote else self.trade_usdt
                self.wallet.buy(symbol, close_price, usdt_amount, ts)
                last_buy_bar = i
                print(f"[{i}] {symbol} BUY @ {close_price:.4f} | {signal.reason}")

            elif signal and signal.side == "SELL":
                base = symbol.replace("USDT", "")
                holdings_before = self.wallet.assets.get(base, Decimal("0"))

                if holdings_before > 0:
                    if symbol == "ETHUSDT":
                        if (i - last_buy_bar) < self.COOLDOWN_BARS:
                            continue
                        if (i - last_sell_bar) < self.ETH_SELL_SPACING_BARS:
                            continue
                        min_holdings = Decimal("0.10")
                        min_profit = Decimal("0.05")   # Require 5% profit (was 10%; rarely met)
                        sell_pct = Decimal("0.15")     # Sell 15% of holdings

                        if holdings_before < min_holdings:
                            pass
                        elif not self.wallet.is_profitable(symbol, close_price, min_profit):
                            pass
                        else:
                            self.wallet.sell_partial(symbol, close_price, sell_pct, ts)
                            last_sell_bar = i
                            holdings_after = self.wallet.assets.get(base, Decimal("0"))
                            avg_cost = self.wallet.get_avg_cost(symbol)
                            profit_pct = (close_price - avg_cost) / avg_cost * Decimal("100") if avg_cost > 0 else Decimal("0")
                            print(f"[{i}] {symbol} SELL {float(sell_pct)*100:.0f}% @ {close_price:.4f} | {signal.reason} | Holdings: {holdings_before:.4f} -> {holdings_after:.4f} | Profit: {profit_pct:.1f}%")
                    else:
                        # XRP: sell 50% (working well)
                        sell_pct = Decimal("0.5")
                        self.wallet.sell_partial(symbol, close_price, sell_pct, ts)
                        holdings_after = self.wallet.assets.get(base, Decimal("0"))
                        print(f"[{i}] {symbol} SELL {float(sell_pct)*100:.0f}% @ {close_price:.4f} | {signal.reason} | Holdings: {holdings_before:.4f} -> {holdings_after:.4f}")
                else:
                    # No holdings to sell, skip
                    pass
