import os
import time
import typer
from decimal import Decimal
import logging
from typing import Dict, Optional

from .logging_setup import setup_logging
from .config import load_config
from .mexc.client import MexcSpotClient
from .services.execution import ExecutionService, ExecutionConfig
from .services.portfolio import Portfolio
from .services.profit_sweep import ProfitSweeper, ProfitSweepConfig
from .services.cost_basis import CostBasisTracker
from .strategies.h1_trend_pullback import H1TrendPullbackStrategy, H1TrendPullbackParams
from .strategies.mq4_eth_xrp import EthMq4Strategy, EthMq4Params, XrpMq4Strategy, XrpMq4Params

app = typer.Typer(add_completion=False)
log = logging.getLogger(__name__)

def load_portfolio(client: MexcSpotClient) -> Portfolio:
    acc = client.account()
    free = {}
    locked = {}
    for b in acc.get("balances", []):
        asset = b.get("asset")
        if not asset:
            continue
        free[asset] = Decimal(str(b.get("free", "0")))
        locked[asset] = Decimal(str(b.get("locked", "0")))
    return Portfolio(free=free, locked=locked)

@app.command()
def run(config: str = typer.Option(..., "--config", "-c"), dry_run: bool = typer.Option(False, "--dry-run")):
    cfg = load_config(config)
    setup_logging(cfg.runtime.log_level)

    api_key = os.getenv(cfg.env.api_key_env)
    api_secret = os.getenv(cfg.env.api_secret_env)
    base_url = os.getenv(cfg.env.base_url_env) or "https://api.mexc.com"
    recv_window = int(os.getenv(cfg.env.recv_window_env) or "5000")
    http_debug = os.getenv("HTTP_DEBUG", "0") == "1"

    dry = dry_run or cfg.safety.dry_run_default

    client = MexcSpotClient(api_key, api_secret, base_url=base_url, recv_window=recv_window, http_debug=http_debug)
    execsvc = ExecutionService(client, ExecutionConfig(**cfg.execution.model_dump()), dry_run=dry)

    params = H1TrendPullbackParams(**cfg.strategy.params)
    strat = H1TrendPullbackStrategy(client, params, quote_per_trade=Decimal(str(cfg.safety.max_usdt_per_order)))

    sweeper = ProfitSweeper(execsvc, ProfitSweepConfig(
        quote_asset=cfg.portfolio.quote_asset,
        min_profit_sweep_usdt=cfg.portfolio.min_profit_sweep_usdt,
        profit_sweep_to_base=cfg.portfolio.profit_sweep_to_base,
    ))

    last_trade_ts = {s: 0.0 for s in cfg.safety.allow_symbols}

    try:
        sweeper.set_baseline(load_portfolio(client))
    except Exception as e:
        log.warning("baseline set failed: %s", e)

    log.info("Bot started symbols=%s dry_run=%s", cfg.safety.allow_symbols, dry)

    while True:
        try:
            for symbol in cfg.safety.allow_symbols:
                if time.time() - last_trade_ts.get(symbol, 0.0) < cfg.safety.cooldown_seconds:
                    continue

                sig = strat.generate(symbol)
                if not sig:
                    continue

                size = Decimal(sig.size_quote)
                if size < cfg.safety.min_usdt_per_order:
                    continue
                size = min(size, Decimal(str(cfg.safety.max_usdt_per_order)))

                log.info("Signal: %s %s size=%s reason=%s", sig.side, sig.symbol, size, sig.reason)
                if sig.side == "BUY":
                    execsvc.market_buy_quote(symbol, size)
                    last_trade_ts[symbol] = time.time()
                    try:
                        sweeper.maybe_sweep(load_portfolio(client), symbol)
                    except Exception as e:
                        log.warning("profit sweep failed: %s", e)

        except KeyboardInterrupt:
            log.info("Stopping...")
            break
        except Exception as e:
            log.exception("Loop error: %s", e)

        time.sleep(cfg.runtime.poll_seconds)


@app.command()
def run_backtest_mode(
    config: str = typer.Option(..., "--config", "-c"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    cost_basis_file: str = typer.Option("cost_basis.json", "--cost-basis-file"),
):
    """
    Live trading mode that uses the SAME logic as backtest:
    - Per-symbol strategies (EthMq4Strategy for ETHUSDT H1, XrpMq4Strategy for XRPUSDT H4)
    - Executes both BUY and SELL signals
    - Cost basis tracking for min profit checks
    - Time-based cooldowns (mapped from bar-based rules)
    """
    cfg = load_config(config)
    setup_logging(cfg.runtime.log_level)

    api_key = os.getenv(cfg.env.api_key_env)
    api_secret = os.getenv(cfg.env.api_secret_env)
    base_url = os.getenv(cfg.env.base_url_env) or "https://api.mexc.com"
    recv_window = int(os.getenv(cfg.env.recv_window_env) or "5000")
    http_debug = os.getenv("HTTP_DEBUG", "0") == "1"

    dry = dry_run or cfg.safety.dry_run_default

    client = MexcSpotClient(api_key, api_secret, base_url=base_url, recv_window=recv_window, http_debug=http_debug)
    execsvc = ExecutionService(client, ExecutionConfig(**cfg.execution.model_dump()), dry_run=dry)
    cost_tracker = CostBasisTracker(state_file=cost_basis_file)

    # Per-symbol strategies (same as backtest)
    strategies: Dict[str, any] = {}
    intervals: Dict[str, str] = {}
    sell_pcts: Dict[str, Decimal] = {}
    min_holdings: Dict[str, Decimal] = {}
    min_profits: Dict[str, Decimal] = {}
    cooldown_hours: Dict[str, Dict[str, float]] = {}  # symbol -> {buy: hours, sell: hours, same_side: hours}

    for symbol in cfg.safety.allow_symbols:
        if symbol == "ETHUSDT":
            strategies[symbol] = EthMq4Strategy(
                client=client,
                params=EthMq4Params(
                    rsi_buy_level=38.0,
                    rsi_buy_ceiling=54.0,
                    rsi_sell_min=70.0,
                    sell_require_premium=False,
                    sell_require_downtrend=False,
                    pullback_atr_mult=0.6,
                ),
                quote_per_trade=Decimal(str(cfg.safety.max_usdt_per_order)),
            )
            intervals[symbol] = "60m"  # H1
            sell_pcts[symbol] = Decimal("0.15")  # 15%
            min_holdings[symbol] = Decimal("0.10")  # 0.10 ETH
            min_profits[symbol] = Decimal("0.05")  # 5%
            cooldown_hours[symbol] = {"opposite": 24.0, "buy": 12.0, "sell": 6.0}  # H1 bars -> hours
        elif symbol == "XRPUSDT":
            strategies[symbol] = XrpMq4Strategy(
                client=client,
                params=XrpMq4Params(
                    dev_atr_mult=2.5,
                    rsi_oversold=35.0,
                    min_atr=0.003,
                ),
                quote_per_trade=Decimal(str(cfg.safety.max_usdt_per_order)),
            )
            intervals[symbol] = "4h"  # H4
            sell_pcts[symbol] = Decimal("0.5")  # 50%
            min_holdings[symbol] = Decimal("0")  # No minimum
            min_profits[symbol] = Decimal("0")  # No minimum (XRP strategy handles it)
            cooldown_hours[symbol] = {"opposite": 24.0, "buy": 12.0, "sell": 6.0}  # Approximate
        else:
            log.warning("Unknown symbol %s, skipping", symbol)
            continue

    # Track last trade times per symbol and side
    last_buy_ts: Dict[str, float] = {}
    last_sell_ts: Dict[str, float] = {}

    log.info("Backtest-mode bot started symbols=%s dry_run=%s", list(strategies.keys()), dry)

    while True:
        try:
            for symbol in strategies.keys():
                strat = strategies[symbol]
                now = time.time()

                # Generate signal first
                sig = strat.generate(symbol)
                if not sig:
                    continue

                portfolio = load_portfolio(client)
                base = symbol.replace("USDT", "")
                cooldown = cooldown_hours.get(symbol, {})

                if sig.side == "BUY":
                    # Opposite-side cooldown (can't buy if sold recently)
                    if last_sell_ts.get(symbol, 0) > 0:
                        if (now - last_sell_ts[symbol]) < cooldown.get("opposite", 24) * 3600:
                            log.debug("Skipping BUY %s: opposite-side cooldown", symbol)
                            continue
                    # Same-side cooldown (can't buy if bought recently)
                    if last_buy_ts.get(symbol, 0) > 0:
                        if (now - last_buy_ts[symbol]) < cooldown.get("buy", 12) * 3600:
                            log.debug("Skipping BUY %s: same-side cooldown", symbol)
                            continue

                    size = Decimal(sig.size_quote or str(cfg.safety.max_usdt_per_order))
                    if size < cfg.safety.min_usdt_per_order:
                        continue
                    size = min(size, Decimal(str(cfg.safety.max_usdt_per_order)))

                    log.info("Signal: BUY %s size=%s reason=%s", symbol, size, sig.reason)
                    result = execsvc.market_buy_quote(symbol, size)
                    if result and not result.get("dry_run"):
                        # Get executed price and qty from result (or fetch ticker)
                        ticker = client.book_ticker(symbol)
                        price = Decimal(str(ticker.get("bidPrice", "0")))  # Use bid for buy estimate
                        if price > 0:
                            base_qty = size / price
                            cost_tracker.record_buy(symbol, price, size, base_qty)
                            cost_tracker.save()
                    last_buy_ts[symbol] = now

                elif sig.side == "SELL":
                    # Opposite-side cooldown (can't sell if bought recently)
                    if last_buy_ts.get(symbol, 0) > 0:
                        if (now - last_buy_ts[symbol]) < cooldown.get("opposite", 24) * 3600:
                            log.debug("Skipping SELL %s: opposite-side cooldown", symbol)
                            continue
                    # Same-side cooldown (can't sell if sold recently)
                    if last_sell_ts.get(symbol, 0) > 0:
                        if (now - last_sell_ts[symbol]) < cooldown.get("sell", 6) * 3600:
                            log.debug("Skipping SELL %s: same-side cooldown", symbol)
                            continue

                    holdings = portfolio.asset_free(base)
                    if holdings < min_holdings.get(symbol, Decimal("0")):
                        log.debug("Skipping SELL %s: holdings %s < min %s", symbol, holdings, min_holdings.get(symbol))
                        continue

                    # Check profitability
                    ticker = client.book_ticker(symbol)
                    current_price = Decimal(str(ticker.get("askPrice", "0")))  # Use ask for sell estimate
                    if current_price <= 0:
                        log.warning("Invalid price for %s", symbol)
                        continue

                    # Check profitability (cost basis should already be up to date from previous trades)
                    if not cost_tracker.is_profitable(symbol, current_price, min_profits.get(symbol, Decimal("0"))):
                        log.debug("Skipping SELL %s: not profitable (price=%s avg_cost=%s)", 
                                 symbol, current_price, cost_tracker.get_avg_cost(symbol))
                        continue

                    sell_pct = sell_pcts.get(symbol, Decimal("0.5"))
                    sell_qty = holdings * sell_pct
                    if sell_qty <= 0:
                        continue

                    log.info("Signal: SELL %s qty=%s (%.0f%%) price=%s reason=%s avg_cost=%s profit=%.1f%%",
                            symbol, sell_qty, float(sell_pct) * 100, current_price, sig.reason,
                            cost_tracker.get_avg_cost(symbol),
                            float((current_price - cost_tracker.get_avg_cost(symbol)) / cost_tracker.get_avg_cost(symbol) * 100) if cost_tracker.get_avg_cost(symbol) > 0 else 0)
                    result = execsvc.market_sell_base(symbol, sell_qty)
                    if result and not result.get("dry_run"):
                        # Use actual executed qty if available, otherwise use computed
                        executed_qty = Decimal(str(result.get("executedQty", sell_qty)))
                        cost_tracker.record_sell(symbol, sell_pct, executed_qty)
                        cost_tracker.save()
                    last_sell_ts[symbol] = now

        except KeyboardInterrupt:
            log.info("Stopping...")
            break
        except Exception as e:
            log.exception("Loop error: %s", e)

        time.sleep(cfg.runtime.poll_seconds)
