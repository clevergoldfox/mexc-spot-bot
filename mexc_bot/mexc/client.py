import time
import logging
import requests

from ..core.rate_limit import SimpleRateLimiter
from ..core.exceptions import HttpError
from .endpoints import BASE_URL_DEFAULT
from .auth import build_signed_params

log = logging.getLogger(__name__)

class MexcSpotClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str = BASE_URL_DEFAULT, recv_window: int = 5000, http_debug: bool = False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.recv_window = int(recv_window)
        self.http_debug = http_debug
        self.session = requests.Session()
        self.rl = SimpleRateLimiter(0.05)

    def _url(self, path: str) -> str:
        return self.base_url + path

    def _request(self, method: str, path: str, params=None, signed: bool = False):
        self.rl.wait()
        params = params or {}
        headers = {"Content-Type": "application/json"}

        if signed:
            ts = int(time.time() * 1000)
            params, signed_headers = build_signed_params(self.api_key, self.api_secret, params, self.recv_window, ts)
            headers.update(signed_headers)

        if self.http_debug:
            log.info("%s %s params=%s signed=%s", method, path, params, signed)

        resp = self.session.request(
            method,
            self._url(path),
            params=params if method in ("GET", "DELETE") else None,
            data=None if method in ("GET", "DELETE") else params,
            headers=headers,
            timeout=60
        )

        if resp.status_code >= 400:
            raise HttpError(resp.status_code, resp.text, payload={"path": path, "params": params})

        try:
            return resp.json()
        except Exception:
            return resp.text

    # Public
    def ping(self):
        from .endpoints import PING
        return self._request("GET", PING)

    def server_time(self):
        from .endpoints import TIME
        return self._request("GET", TIME)

    def exchange_info(self, symbol: str | None = None):
        from .endpoints import EXCHANGE_INFO
        p = {}
        if symbol:
            p["symbol"] = symbol
        return self._request("GET", EXCHANGE_INFO, params=p)

    def klines(self, symbol: str, interval: str, limit: int = 500):
        from .endpoints import KLINES
        return self._request("GET", KLINES, params={"symbol": symbol, "interval": interval, "limit": limit})

    def book_ticker(self, symbol: str):
        from .endpoints import BOOK_TICKER
        return self._request("GET", BOOK_TICKER, params={"symbol": symbol})

    # Signed
    def account(self):
        from .endpoints import ACCOUNT
        return self._request("GET", ACCOUNT, signed=True)

    def place_order(self, **params):
        from .endpoints import ORDER
        return self._request("POST", ORDER, params=params, signed=True)

    def get_order(self, symbol: str, orderId: int):
        from .endpoints import ORDER
        return self._request("GET", ORDER, params={"symbol": symbol, "orderId": orderId}, signed=True)

    def cancel_order(self, symbol: str, orderId: int):
        from .endpoints import ORDER
        return self._request("DELETE", ORDER, params={"symbol": symbol, "orderId": orderId}, signed=True)

    def open_orders(self, symbol: str | None = None):
        from .endpoints import OPEN_ORDERS
        p = {}
        if symbol:
            p["symbol"] = symbol
        return self._request("GET", OPEN_ORDERS, params=p, signed=True)
