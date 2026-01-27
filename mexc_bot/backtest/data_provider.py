import time
from typing import List
from ..mexc.client import MexcSpotClient


def fetch_klines(
    client: MexcSpotClient,
    symbol: str,
    interval: str = "1H",
    limit: int = 1000,
    max_candles: int = 5000,
) -> List[list]:
    """
    Fetch historical klines from MEXC with pagination
    """

    all_klines = []
    end_time = None

    while len(all_klines) < max_candles:
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }

        if end_time:
            params["endTime"] = end_time

        klines = client._request(
            "GET",
            "/api/v3/klines",
            params=params,
        )

        if not klines:
            break

        all_klines = klines + all_klines
        end_time = klines[0][0] - 1  # previous candle

        time.sleep(0.2)  # avoid rate limit

    return all_klines[-max_candles:]
