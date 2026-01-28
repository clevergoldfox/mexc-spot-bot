# mexc_bot/backtest/run_backtest.py

import argparse
from decimal import Decimal
from mexc_bot.mexc.client import MexcSpotClient
from mexc_bot.backtest.data_provider import fetch_klines
from mexc_bot.backtest.simulator import SpotWallet
from mexc_bot.backtest.engine import BacktestEngine
from mexc_bot.strategies.mq4_eth_xrp import (
    EthMq4Strategy,
    EthMq4Params,
    XrpMq4Strategy,
    XrpMq4Params,
)


def run(symbols=None, years=3):
    # Public client (no auth needed for klines)
    client = MexcSpotClient("", "")

    symbols = symbols or ["XRPUSDT", "ETHUSDT"]
    # Backtest each symbol with its own wallet
    for symbol in symbols:
        print(f"\n=== Backtesting {symbol} (separate wallet) ===")

        # Independent virtual wallet per symbol
        wallet = SpotWallet(initial_usdt=Decimal("1000"))

        # Strategy (client not required in backtest)
        # Optimized parameters for better accumulation (best performing so far)
        if symbol == "ETHUSDT":
            strategy = EthMq4Strategy(
                client=None,
                params=EthMq4Params(
                    rsi_buy_level=38.0,   # Slightly relaxed for more entries
                    rsi_buy_ceiling=54.0, # Avoid chasing (RSI_1 < 54)
                    rsi_sell_min=70.0,
                    sell_require_premium=False,
                    sell_require_downtrend=False,  # SELL on overbought reversal only
                    pullback_atr_mult=0.6,
                ),
                quote_per_trade=Decimal("50"),
            )
            interval = "60m"  # H1
        else:  # XRPUSDT
            strategy = XrpMq4Strategy(
                client=None,
                params=XrpMq4Params(
                    dev_atr_mult=2.5,  # Optimized (was 3.0)
                    rsi_oversold=35.0,  # Optimized (was 28.0)
                    min_atr=0.003,  # Lower minimum ATR (was 0.005)
                ),
                quote_per_trade=Decimal("40"),  # Allows ~25 trades
            )
            interval = "4h"  # H4

        engine = BacktestEngine(
            wallet=wallet,
            strategy=strategy,
            trade_usdt=Decimal("50") if symbol == "ETHUSDT" else Decimal("40"),  # Match quote_per_trade
        )

        # Calculate how many candles we need
        if symbol == "ETHUSDT":
            needed_candles = 24 * 365 * years  # H1
        else:  # XRPUSDT H4
            needed_candles = 6 * 365 * years  # 6 candles/day
        
        klines = fetch_klines(
            client=client,
            symbol=symbol,
            interval=interval,
            limit=5000,
            max_candles=needed_candles + 1000,  # Request extra for safety
        )
        print(f"Fetched candles: {len(klines)}")

        if len(klines) < 300:
            print("Not enough data, skipping.")
            continue

        # Restrict to last N years of data
        if symbol == "ETHUSDT":
            lookback_candles = 24 * 365 * years
        else:  # XRPUSDT H4
            lookback_candles = 6 * 365 * years

        if len(klines) > lookback_candles:
            klines = klines[-lookback_candles:]
            print(f"Using last {lookback_candles} candles (~{years} year{'s' if years != 1 else ''})")

        engine.run(symbol, klines)

        # Per-symbol results: mark-to-market value in USDT for accumulation
        base = symbol.replace("USDT", "")
        last_close = Decimal(klines[-1][4])
        base_qty = wallet.assets.get(base, Decimal("0"))
        portfolio_value = wallet.usdt + base_qty * last_close
        start_capital = Decimal("1000")
        profit_pct = (portfolio_value / start_capital - Decimal("1")) * Decimal("100")

        print("\n--- RESULT", symbol, "---")
        print("Final USDT:", wallet.usdt)
        print("Base holdings:", wallet.assets)
        print("Portfolio value (USDT):", portfolio_value)
        print(f"Profit % over ~{years} year{'s' if years != 1 else ''}:", profit_pct)
        print("Trades:", len(wallet.trades))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run MEXC spot backtest (XRP H4, ETH H1).")
    parser.add_argument("--symbols", nargs="+", default=["XRPUSDT", "ETHUSDT"], help="Symbols to backtest")
    parser.add_argument("--years", type=int, default=3, help="Years of history (default: 3)")
    args = parser.parse_args()
    run(symbols=args.symbols, years=args.years)
