"""pytest配置：隔离运行环境（临时数据库/存储/模型目录）与共享TestClient。

关键设计：
- 测试不触碰真实 backend/data 数据库与 storage 图像目录：
  session级autouse fixture把 database.DB_PATH、init_db.DB_PATH、
  detect/record的UPLOAD_DIR/RESULT_DIR、main.MODEL_DIR 指向临时目录，
  结束后恢复原值；
- 合成部署权重（不下载任何网络资源）：ultralytics构建nc=6随机权重DetectionModel
  保存为pt，供PTEngine全链路冒烟；ONNX引擎用例由该pt临时导出onnx验证。
"""

from __future__ import annotations

import uuid

import pytest
import torch
from fastapi.testclient import TestClient
from ultralytics.nn.tasks import DetectionModel


@pytest.fixture(scope="session", autouse=True)
def _env(tmp_path_factory):
    """把后端运行环境重定向到临时目录，并生成合成权重。"""
    base = tmp_path_factory.mktemp("pvtest")
    db_file = base / "pv_test.db"
    up_dir, res_dir, wdir = base / "uploads", base / "results", base / "weights"
    for d in (up_dir, res_dir, wdir):
        d.mkdir()

    # 合成随机权重pt（nc=6，与六类缺陷一致）
    model = DetectionModel("yolov8n.yaml", nc=6, verbose=False).cpu()
    pt_path = wdir / "best_smoke.pt"
    torch.save({"model": model, "train_args": {}, "date": "smoke",
                "version": "smoke", "description": "smoke test weights"}, pt_path)

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
        (mm, "MODEL_DIR", mm.MODEL_DIR),
    ]
    dm.DB_PATH = db_file
    im.DB_PATH = db_file
    dmod.UPLOAD_DIR, dmod.RESULT_DIR = up_dir, res_dir
    rmod.UPLOAD_DIR, rmod.RESULT_DIR = up_dir, res_dir
    mm.MODEL_DIR = wdir

    yield {"weights_dir": wdir, "pt_path": pt_path}

    for mod, name, val in saved:
        setattr(mod, name, val)


@pytest.fixture(scope="session")
def client(_env):
    """共享TestClient：进入with块触发startup（init_db + 加载合成权重）。"""
    from app.main import app
    with TestClient(app) as c:
        yield c


def make_user(client, prefix: str = "u") -> tuple[str, str]:
    """注册并登录，返回(username, token)。"""
    name = f"{prefix}_{uuid.uuid4().hex[:8]}"
    resp = client.post("/api/auth/register", json={
        "username": name, "password": "Abc123456",
        "email": f"{name}@test.com", "nickname": "测试用户",
    })
    assert resp.status_code == 200, resp.text
    login = client.post("/api/auth/login", json={
        "username": name, "password": "Abc123456"})
    assert login.status_code == 200, login.text
    return name, login.json()["data"]["access_token"]


def make_test_image(width: int = 640, height: int = 480) -> bytes:
    """生成合成测试图片（随机噪声，保证非纯色、可解码）。"""
    import cv2
    import numpy as np
    img = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


AUTH = {"Authorization": "Bearer {token}"}
