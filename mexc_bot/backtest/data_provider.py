import time
from typing import List

import requests
from ..mexc.client import MexcSpotClient


def fetch_klines(
    client: MexcSpotClient,
    symbol: str,
    interval: str = "1H",
    limit: int = 1000,
    max_candles: int = 5000,
) -> List[list]:
    """
    Fetch historical klines from MEXC with pagination.
    Retries on ReadTimeout (up to 3 attempts with backoff).
    """

    all_klines = []
    end_time = None
    max_retries = 3

    while len(all_klines) < max_candles:
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if end_time:
            params["endTime"] = end_time

        for attempt in range(max_retries):
            try:
                klines = client._request(
                    "GET",
                    "/api/v3/klines",
                    params=params,
                )
                break
            except requests.exceptions.ReadTimeout:
                if attempt < max_retries - 1:
                    time.sleep(2 ** (attempt + 1))  # 2, 4, 8 sec backoff
                else:
                    raise

        if not klines:
            break

        all_klines = klines + all_klines
        end_time = klines[0][0] - 1  # previous candle

        time.sleep(0.2)  # avoid rate limit

    return all_klines[-max_candles:]
