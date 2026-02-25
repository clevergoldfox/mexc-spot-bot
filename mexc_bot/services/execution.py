from dataclasses import dataclass
from decimal import Decimal
import json
import logging

from ..mexc.client import MexcSpotClient
from ..core.exceptions import HttpError

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
        try:
            return self.client.place_order(symbol=symbol, side="BUY", type="MARKET", quoteOrderQty=str(quote_qty))
        except HttpError as exc:
            if self._error_code(exc) == 30041:
                # Fallback to LIMIT for symbols that reject MARKET orders.
                ticker = self.client.book_ticker(symbol)
                ask = Decimal(str(ticker.get("askPrice", "0") or ticker.get("bidPrice", "0")))
                if ask <= 0:
                    raise
                min_notional = self._get_min_notional(symbol)
                if min_notional is not None and quote_qty < min_notional:
                    raise
                raw_qty = quote_qty / ask
                qty = self._adjust_quantity(symbol, raw_qty)
                if qty <= 0:
                    raise
                buffer = Decimal(self.cfg.limit_price_buffer_bps) / Decimal("10000")
                limit_price = ask * (Decimal("1") + buffer)
                return self.client.place_order(
                    symbol=symbol,
                    side="BUY",
                    type="LIMIT",
                    timeInForce=self.cfg.time_in_force,
                    quantity=str(qty),
                    price=str(limit_price),
                )
            raise

    def market_sell_base(self, symbol: str, base_qty: Decimal):
        if self.dry_run:
            log.info("[DRY] MARKET SELL %s quantity=%s", symbol, base_qty)
            return {"dry_run": True}
        qty = self._adjust_quantity(symbol, base_qty)
        if qty <= 0:
            raise ValueError(f"Adjusted sell quantity is zero for {symbol}. base_qty={base_qty}")
        return self.client.place_order(symbol=symbol, side="SELL", type="MARKET", quantity=str(qty))

    def _error_code(self, exc: Exception) -> int | None:
        try:
            msg = str(exc)
            if "HTTP" in msg and "{" in msg:
                payload = msg.split("HTTP", 1)[1]
                payload = payload[payload.find("{"):]
                data = json.loads(payload)
                return int(data.get("code"))
        except Exception:
            return None
        return None

    def _get_min_notional(self, symbol: str) -> Decimal | None:
        try:
            info = self.client.exchange_info(symbol=symbol)
            symbols = info.get("symbols", []) if isinstance(info, dict) else []
            if not symbols:
                return None
            data = symbols[0]
            filters = data.get("filters", []) if isinstance(data, dict) else []
            for f in filters:
                if f.get("filterType") in ("MIN_NOTIONAL", "MIN_NOTIONAL_VALUE", "NOTIONAL"):
                    value = f.get("minNotional") or f.get("notional") or f.get("minNotionalValue")
                    if value is not None:
                        return Decimal(str(value))
        except Exception:
            return None
        return None

    def _adjust_quantity(self, symbol: str, qty: Decimal) -> Decimal:
        try:
            info = self.client.exchange_info(symbol=symbol)
            symbols = info.get("symbols", []) if isinstance(info, dict) else []
            if not symbols:
                return Decimal("0")
            data = symbols[0]
            filters = data.get("filters", []) if isinstance(data, dict) else []
            step = None
            min_qty = None
            for f in filters:
                if f.get("filterType") == "MARKET_LOT_SIZE":
                    step = Decimal(str(f.get("stepSize", "0")))
                    min_qty = Decimal(str(f.get("minQty", "0")))
                    break
            if step is None:
                for f in filters:
                    if f.get("filterType") == "LOT_SIZE":
                        step = Decimal(str(f.get("stepSize", "0")))
                        min_qty = Decimal(str(f.get("minQty", "0")))
                        break
            if step is None or step <= 0:
                return qty
            steps = (qty / step).to_integral_value(rounding="ROUND_FLOOR")
            adj = steps * step
            if min_qty is not None and adj < min_qty:
                return Decimal("0")
            return adj
        except Exception:
            return qty
