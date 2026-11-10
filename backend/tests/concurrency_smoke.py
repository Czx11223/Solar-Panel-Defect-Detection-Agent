"""并发简单测试脚本（无第三方依赖，仅标准库）。

场景：注册唯一用户 → 登录获取token → 多线程并发请求
  A. GET  /api/record/list      （鉴权接口，预期稳定通过）
  B. POST /api/detect/image     （检测接口；权重缺失时预期50301，如实统计）

输出：每类请求的成功率、平均/最大响应时间、错误码分布。

运行：cd backend && python tests/concurrency_smoke.py [并发线程数] [每线程请求数]
"""

from __future__ import annotations

import base64
import io
import json
import os
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

BASE_URL = os.getenv("PV_TEST_BASE_URL", "http://127.0.0.1:8000")

# 1x1 纯白JPEG（合法图像，魔数与内容均有效，用于检测接口请求体）
TINY_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVN//2Q=="
)


class Stats:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.times: list[float] = []
        self.codes: dict[int, int] = {}

    def record(self, elapsed_ms: float, status: int) -> None:
        with self.lock:
            self.times.append(elapsed_ms)
            self.codes[status] = self.codes.get(status, 0) + 1

    def summary(self, name: str) -> str:
        n = len(self.times)
        if n == 0:
            return f"{name}: 0 请求"
        ok = sum(v for k, v in self.codes.items() if k < 400)
        avg = statistics.mean(self.times)
        mx = max(self.times)
        return (f"{name}: {n}请求 成功{ok} 失败{n - ok} "
                f"成功率{ok / n * 100:.1f}% 平均{avg:.0f}ms 最大{mx:.0f}ms "
                f"状态码分布{sorted(self.codes.items())}")


def _request(method: str, path: str, headers: dict | None = None,
             body: bytes | None = None, content_type: str | None = None):
    req = urllib.request.Request(BASE_URL + path, method=method, data=body, headers=headers or {})
    if content_type:
        req.add_header("Content-Type", content_type)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
            return (time.perf_counter() - t0) * 1000, resp.status
    except urllib.error.HTTPError as e:
        e.read()
        return (time.perf_counter() - t0) * 1000, e.code
    except Exception as e:
        return (time.perf_counter() - t0) * 1000, -1  # 网络层失败


def _post_json(path: str, payload: dict):
    req = urllib.request.Request(
        BASE_URL + path, method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))["data"]


def worker(thread_id: int, token: str, per_thread: int, list_stats: Stats,
           detect_stats: Stats, detect_body: bytes) -> None:
    boundary = f"----pvtest{thread_id}{uuid.uuid4().hex[:8]}"
    multipart = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="tiny.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode() + detect_body + f"\r\n--{boundary}--\r\n".encode()
    auth = {"Authorization": f"Bearer {token}"}

    for _ in range(per_thread):
        ms, status = _request("GET", "/api/record/list?page=1&page_size=5", headers=auth)
        list_stats.record(ms, status)

        ms, status = _request(
            "POST", "/api/detect/image", headers=auth, body=multipart,
            content_type=f"multipart/form-data; boundary={boundary}")
        detect_stats.record(ms, status)


def main() -> int:
    threads_n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    per_thread = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    name = f"conc_{uuid.uuid4().hex[:8]}"
    _post_json("/api/auth/register", {"username": name, "password": "Abc123456"})
    token = _post_json("/api/auth/login", {"username": name, "password": "Abc123456"})["access_token"]
    print(f"用户 {name} 注册并登录成功，开始并发测试（{threads_n}线程 × {per_thread}请求）")

    list_stats, detect_stats = Stats(), Stats()
    threads = [threading.Thread(target=worker, args=(
        i, token, per_thread, list_stats, detect_stats, TINY_JPEG)) for i in range(threads_n)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total = (time.perf_counter() - t0) * 1000

    print(list_stats.summary("GET /api/record/list"))
    print(detect_stats.summary("POST /api/detect/image"))
    print(f"总耗时 {total:.0f}ms（并发 {threads_n}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
