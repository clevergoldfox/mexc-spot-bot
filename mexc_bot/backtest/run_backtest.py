# mexc_bot/backtest/run_backtest.py

from decimal import Decimal
from mexc_bot.mexc.client import MexcSpotClient
from mexc_bot.backtest.data_provider import fetch_klines
from mexc_bot.backtest.simulator import SpotWallet
from mexc_bot.backtest.engine import BacktestEngine
from mexc_bot.strategies.h1_trend_pullback import (
    H1TrendPullbackStrategy,
    H1TrendPullbackParams,
)

def run():
    # Public client (no auth needed for klines)
    client = MexcSpotClient("", "")

    # Initial virtual wallet
    wallet = SpotWallet(initial_usdt=Decimal("1000"))

    # === Strategy parameters (H1 XRP/ETH tuned) ===
    params = H1TrendPullbackParams(
        candles_limit=300,
        ema_fast=50,
        ema_slow=200,
        rsi_period=14,
        rsi_buy_max=62.0,
        atr_period=14,
        min_atr=0.01,
        pullback_atr_mult=0.35,
    )

    # Strategy (client not required in backtest)
    strategy = H1TrendPullbackStrategy(
        client=None,
        params=params,
        quote_per_trade=Decimal("50"),
    )

    # Backtest engine
    engine = BacktestEngine(
        wallet=wallet,
        strategy=strategy,
        trade_usdt=Decimal("50"),
    )

    # Run backtest
    for symbol in ["XRPUSDT", "ETHUSDT"]:
        print(f"\n=== Backtesting {symbol} ===")
        klines = fetch_klines(
            client=client,
            symbol=symbol,
            interval="60m",   # MEXC H1
            limit=5000
        )
        print(f"Fetched candles: {len(klines)}")

        if len(klines) < 300:
            print("Not enough data, skipping.")
            continue
        engine.run(symbol, klines)

    # Results
    print("\n========== RESULT ==========")
    print("Final USDT:", wallet.usdt)
    print("Holdings:", wallet.assets)
    print("Trades:", len(wallet.trades))

if __name__ == "__main__":
    run()
