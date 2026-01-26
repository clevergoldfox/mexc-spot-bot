from dataclasses import dataclass
from decimal import Decimal
import logging

from .execution import ExecutionService
from .portfolio import Portfolio

log = logging.getLogger(__name__)

@dataclass
class ProfitSweepConfig:
    quote_asset: str = "USDT"
    min_profit_sweep_usdt: Decimal = Decimal("2.0")
    profit_sweep_to_base: dict[str, str] | None = None

class ProfitSweeper:
    def __init__(self, execsvc: ExecutionService, cfg: ProfitSweepConfig):
        self.execsvc = execsvc
        self.cfg = cfg
        self._baseline: Decimal | None = None

    def set_baseline(self, p: Portfolio):
        self._baseline = p.asset_free(self.cfg.quote_asset)

    def maybe_sweep(self, p: Portfolio, symbol: str):
        if self._baseline is None:
            self.set_baseline(p)
            return
        cur = p.asset_free(self.cfg.quote_asset)
        profit = cur - self._baseline
        if profit < self.cfg.min_profit_sweep_usdt:
            return
        base = (self.cfg.profit_sweep_to_base or {}).get(symbol)
        if not base:
            return
        log.info("Profit sweep: %s %s -> %s via %s", profit, self.cfg.quote_asset, base, symbol)
        self.execsvc.market_buy_quote(symbol, profit)
        self._baseline = max(Decimal("0"), cur - profit)
