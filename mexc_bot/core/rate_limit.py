import time
from dataclasses import dataclass

@dataclass
class SimpleRateLimiter:
    min_interval: float = 0.05
    _last: float = 0.0

    def wait(self) -> None:
        now = time.time()
        elapsed = now - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.time()
