import os
import time
import typer
from decimal import Decimal
import logging

from .logging_setup import setup_logging
from .config import load_config
from .mexc.client import MexcSpotClient
from .services.execution import ExecutionService, ExecutionConfig
from .services.portfolio import Portfolio
from .services.profit_sweep import ProfitSweeper, ProfitSweepConfig
from .strategies.h1_trend_pullback import H1TrendPullbackStrategy, H1TrendPullbackParams

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
