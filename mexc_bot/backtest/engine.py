# mexc_bot/backtest/engine.py
from decimal import Decimal
from typing import List
from mexc_bot.backtest.simulator import SpotWallet
from mexc_bot.strategies.base import Signal

class BacktestEngine:
    def __init__(self, wallet: SpotWallet, strategy, trade_usdt: Decimal):
        self.wallet = wallet
        self.strategy = strategy
        self.trade_usdt = trade_usdt

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

            if signal and signal.side == "BUY":
                # Use signal.size_quote if available, otherwise fallback to trade_usdt
                usdt_amount = signal.size_quote if signal.size_quote else self.trade_usdt
                self.wallet.buy(symbol, close_price, usdt_amount, ts)
                print(f"[{i}] {symbol} BUY @ {close_price:.4f} | {signal.reason}")

            elif signal and signal.side == "SELL":
                # For accumulation strategy: sell partial to lock in profit
                # while keeping some holdings for further growth
                base = symbol.replace("USDT", "")
                holdings_before = self.wallet.assets.get(base, Decimal("0"))
                
                if holdings_before > 0:
                    # For ETH: very conservative selling strategy
                    if symbol == "ETHUSDT":
                        min_holdings = Decimal("0.15")  # Minimum 0.15 ETH before selling
                        min_profit = Decimal("0.15")  # Require 15% profit (very high threshold)
                        
                        if holdings_before < min_holdings:
                            # Too small to sell, keep accumulating
                            pass
                        elif not self.wallet.is_profitable(symbol, close_price, min_profit):
                            # Not profitable enough, skip
                            pass
                        else:
                            # Very profitable and have enough holdings - sell only 15% (ultra conservative)
                            sell_pct = Decimal("0.15")
                            self.wallet.sell_partial(symbol, close_price, sell_pct, ts)
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
