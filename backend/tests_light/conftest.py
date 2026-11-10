"""轻量测试环境：不依赖 torch / ultralytics / ONNX 权重。

与 tests/（完整算法链路测试，需算法环境）并列：
- tests/        需 torch + ultralytics，验证真实权重导出与推理；
- tests_light/  用内存 FakeEngine 覆盖 API 全链路，适合 CI 与干净环境快速回归。

运行（backend/ 目录）：python -m pytest tests_light/ -v
"""

from __future__ import annotations

import uuid

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient


class FakeEngine:
    """固定输出的推理引擎替身：结果可复现，不依赖深度学习框架。"""

    available = True
    model_version = "best_smoke"

    def infer(self, img_bgr: np.ndarray) -> tuple[list[dict], float]:
        h, w = img_bgr.shape[:2]
        return ([{
            "class_id": 1,
            "class_name": "积灰",
            "confidence": 0.9,
            "bbox": [10.0, 10.0, min(100.0, float(w)), min(100.0, float(h))],
        }], 1.25)


@pytest.fixture(scope="session", autouse=True)
def _env(tmp_path_factory):
    """把后端运行环境重定向到临时目录，并注入 FakeEngine。"""
    base = tmp_path_factory.mktemp("pvtest_light")
    db_file = base / "pv_test.db"
    up_dir, res_dir = base / "uploads", base / "results"
    for d in (up_dir, res_dir):
        d.mkdir()

    import app.api.detect as dmod
    import app.api.record as rmod
    import app.db.database as dm
    import app.db.init_db as im
    import app.main as mm

    saved = [
        (dm, "DB_PATH", dm.DB_PATH),
        (im, "DB_PATH", im.DB_PATH),
        (dmod, "UPLOAD_DIR", dmod.UPLOAD_DIR),
        (dmod, "RESULT_DIR", dmod.RESULT_DIR),
        (rmod, "UPLOAD_DIR", rmod.UPLOAD_DIR),
        (rmod, "RESULT_DIR", rmod.RESULT_DIR),
        (mm, "load_engine", mm.load_engine),
    ]
    dm.DB_PATH, im.DB_PATH = db_file, db_file
    dmod.UPLOAD_DIR, dmod.RESULT_DIR = up_dir, res_dir
    rmod.UPLOAD_DIR, rmod.RESULT_DIR = up_dir, res_dir
    mm.load_engine = lambda _model_dir: FakeEngine()

    yield {"db": db_file, "uploads": up_dir, "results": res_dir}

    for mod, name, val in saved:
        setattr(mod, name, val)


@pytest.fixture(scope="session")
def client(_env):
    """共享 TestClient：进入 with 块触发 startup（init_db + 注入引擎）。"""
    from app.main import app
    with TestClient(app) as c:
        yield c


def make_user(client, prefix: str = "u") -> tuple[str, str]:
    """注册并登录，返回 (username, token)。"""
    name = f"{prefix}_{uuid.uuid4().hex[:8]}"
    resp = client.post("/api/auth/register", json={
        "username": name, "password": "Abc123456",
        "email": f"{name}@test.com", "nickname": "测试用户",
    })
    assert resp.status_code == 200, resp.text
    login = client.post("/api/auth/login", json={"username": name, "password": "Abc123456"})
    assert login.status_code == 200, login.text
    return name, login.json()["data"]["access_token"]


def make_test_image(width: int = 640, height: int = 480) -> bytes:
    """固定种子生成可复现的测试图片（非纯色、可解码）。"""
    rng = np.random.default_rng(20260914)
    img = rng.integers(0, 255, (height, width, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()
