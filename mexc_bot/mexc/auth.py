import hmac
import hashlib
import os
from urllib.parse import urlencode

def _sorted_items(params: dict) -> list[tuple]:
    return [(k, params[k]) for k in sorted(params.keys())]

def _to_query(items: list[tuple]) -> str:
    return urlencode(items, doseq=True)

def sign_params(secret: str, params: dict) -> str:
    items = _sorted_items(params)
    qs = _to_query(items)
    if os.getenv("MEXC_DEBUG_QUERY", "0") == "1":
        print(qs)
    sig = hmac.new(secret.encode("utf-8"), qs.encode("utf-8"), hashlib.sha256).hexdigest()
    if os.getenv("MEXC_DEBUG_QUERY", "0") == "1":
        print(f"{qs}&signature={sig.lower()}")
    return sig.lower()

def build_signed_params(api_key: str, secret: str, params: dict, recv_window: int, timestamp_ms: int):
    signed = dict(params)
    signed.pop("signature", None)
    signed["recvWindow"] = int(recv_window)
    signed["timestamp"] = int(timestamp_ms)
    signature = sign_params(secret, signed)
    items = _sorted_items(signed)
    items.append(("signature", signature))
    headers = {"X-MEXC-APIKEY": api_key, "Content-Type": "application/json"}
    return items, headers
