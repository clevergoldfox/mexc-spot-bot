# mexc_bot/backtest/run_backtest.py

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


def run():
    # Public client (no auth needed for klines)
    client = MexcSpotClient("", "")

    # Backtest each symbol with its own wallet
    for symbol in ["XRPUSDT", "ETHUSDT"]:
        print(f"\n=== Backtesting {symbol} (separate wallet) ===")

        # Independent virtual wallet per symbol
        wallet = SpotWallet(initial_usdt=Decimal("1000"))

        # Strategy (client not required in backtest)
        # Optimized parameters for better accumulation (best performing so far)
        if symbol == "ETHUSDT":
            strategy = EthMq4Strategy(
                client=None,
                params=EthMq4Params(
                    rsi_buy_level=35.0,  # Very selective - buy when RSI is lower (was 38.0)
                    pullback_atr_mult=0.6,  # Tighter pullback - buy closer to EMA (was 0.7)
                ),
                quote_per_trade=Decimal("50"),  # Larger trades, fewer but better entries
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

        # Calculate how many candles we need for 3 years
        if symbol == "ETHUSDT":
            needed_candles = 24 * 365 * 3  # H1 -> hours per year * 3 years
        else:  # XRPUSDT H4
            needed_candles = 6 * 365 * 3  # 6 candles/day * 365 days * 3 years
        
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

        # Restrict to last ~3 years of data (approx)
        if symbol == "ETHUSDT":
            lookback_candles = 24 * 365 * 3  # H1 -> hours per year * 3 years
        else:  # XRPUSDT H4 (~6 candles/day)
            lookback_candles = 6 * 365 * 3  # 6 candles/day * 365 days * 3 years

        if len(klines) > lookback_candles:
            klines = klines[-lookback_candles:]
            print(f"Using last {lookback_candles} candles (~3 years)")

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
        print("Profit % over ~3 years:", profit_pct)
        print("Trades:", len(wallet.trades))

if __name__ == "__main__":
    run()
