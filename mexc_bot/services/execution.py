from dataclasses import dataclass
from decimal import Decimal
import logging

from ..mexc.client import MexcSpotClient

log = logging.getLogger(__name__)

@dataclass
class ExecutionConfig:
    default_order_type: str = "MARKET"
    slippage_bps: int = 20
    limit_price_buffer_bps: int = 10
    time_in_force: str = "GTC"

class ExecutionService:
    def __init__(self, client: MexcSpotClient, cfg: ExecutionConfig, dry_run: bool):
        self.client = client
        self.cfg = cfg
        self.dry_run = dry_run

    def market_buy_quote(self, symbol: str, quote_qty: Decimal):
        if self.dry_run:
            log.info("[DRY] MARKET BUY %s quoteOrderQty=%s", symbol, quote_qty)
            return {"dry_run": True}
        return self.client.place_order(symbol=symbol, side="BUY", type="MARKET", quoteOrderQty=str(quote_qty))

    def market_sell_base(self, symbol: str, base_qty: Decimal):
        if self.dry_run:
            log.info("[DRY] MARKET SELL %s quantity=%s", symbol, base_qty)
            return {"dry_run": True}
        return self.client.place_order(symbol=symbol, side="SELL", type="MARKET", quantity=str(base_qty))
