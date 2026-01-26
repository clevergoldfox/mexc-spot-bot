import hmac
import hashlib
from urllib.parse import urlencode

def _to_query(params: dict) -> str:
    items = [(k, params[k]) for k in sorted(params.keys())]
    return urlencode(items, doseq=True)

def sign_params(secret: str, params: dict) -> str:
    qs = _to_query(params)
    sig = hmac.new(secret.encode("utf-8"), qs.encode("utf-8"), hashlib.sha256).hexdigest()
    return sig.lower()

def build_signed_params(api_key: str, secret: str, params: dict, recv_window: int, timestamp_ms: int):
    signed = dict(params)
    signed["recvWindow"] = int(recv_window)
    signed["timestamp"] = int(timestamp_ms)
    signed["signature"] = sign_params(secret, signed)
    headers = {"X-MEXC-APIKEY": api_key, "Content-Type": "application/json"}
    return signed, headers
