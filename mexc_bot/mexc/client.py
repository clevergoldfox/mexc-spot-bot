import time
import logging
import json
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
        self._time_offset_ms = 0
        self._last_time_sync = 0.0

    def _now_ms(self) -> int:
        return int(time.time() * 1000) + self._time_offset_ms

    def _sync_time(self) -> None:
        # Keep offset fresh but avoid spamming the time endpoint.
        now = time.time()
        if now - self._last_time_sync < 30:
            return
        try:
            server = self.server_time()
            if isinstance(server, dict) and "serverTime" in server:
                self._time_offset_ms = int(server["serverTime"]) - int(time.time() * 1000)
                self._last_time_sync = now
        except Exception:
            pass

    def _get_server_time(self) -> int | None:
        try:
            resp = requests.get(self._url("/api/v3/time"), timeout=5)
            data = resp.json()
            return int(data.get("serverTime"))
        except Exception:
            return None

    def _url(self, path: str) -> str:
        return self.base_url + path

    def _request(self, method: str, path: str, params=None, signed: bool = False):
        self.rl.wait()
        params = params or {}
        headers = {}

        if signed:
            # Always use MEXC server time for signed requests.
            ts = self._get_server_time()
            if ts is None:
                self._sync_time()
                ts = self._now_ms()
            params, signed_headers = build_signed_params(self.api_key, self.api_secret, params, self.recv_window, ts)
            headers.update(signed_headers)

        if self.http_debug:
            log.info("%s %s params=%s signed=%s", method, path, params, signed)

        last_error = None
        for attempt in range(3):
            try:
                resp = self.session.request(
                    method,
                    self._url(path),
                    params=params,
                    data=None,
                    headers=headers,
                    timeout=60
                )

                if resp.status_code >= 400:
                    # If server says timestamp is outside recvWindow, resync time once and retry.
                    if signed and resp.status_code == 400:
                        try:
                            payload = json.loads(resp.text)
                        except Exception:
                            payload = {}
                        if payload.get("code") == 700003 or "recvWindow" in str(payload.get("msg", "")):
                            self._last_time_sync = 0.0
                            self._sync_time()
                            ts = self._now_ms()
                            params, signed_headers = build_signed_params(
                                self.api_key, self.api_secret, params, self.recv_window, ts
                            )
                            headers.update(signed_headers)
                            continue
                    if resp.status_code in (502, 503, 504):
                        time.sleep(1 + attempt * 2)
                        continue
                    raise HttpError(resp.status_code, resp.text, payload={"path": path, "params": params})

                try:
                    return resp.json()
                except Exception:
                    return resp.text
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = exc
                # small backoff then retry
                time.sleep(1 + attempt)
        raise last_error

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
