"""进程内滑动窗口限流（线程安全，零依赖）。

适用范围：单进程 uvicorn 部署。多 worker / 多机部署时各进程计数独立，
应替换为 Redis 等共享存储（接口 check(key) -> bool 保持不变）。
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: float):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """记录一次尝试；未超限返回 True，超限返回 False。"""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.max_attempts:
                return False
            q.append(now)
            return True
