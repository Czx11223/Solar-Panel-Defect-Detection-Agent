"""轻量 API 回归测试：干净环境可跑，无需 torch / ultralytics / 权重文件。

运行：cd backend && python -m pytest tests_light/ -v
"""

from __future__ import annotations

import uuid

import numpy as np

from .conftest import make_test_image, make_user


def _detect(client, token, filename: str = "panel_test.jpg", img: bytes | None = None) -> dict:
    files = {"file": (filename, img if img is not None else make_test_image(), "image/jpeg")}
    resp = client.post("/api/detect/image",
                       headers={"Authorization": f"Bearer {token}"}, files=files)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ---------- 健康检查与鉴权 ----------

def test_health(client):
    # 单端口部署形态（webapp_dist 存在）时 / 返回前端 HTML，健康检查在 /health
    root = client.get("/")
    if root.headers.get("content-type", "").startswith("text/html"):
        resp = client.get("/health")
    else:
        resp = root
    body = resp.json()
    assert body["app"] and body["docs"] == "/docs"
    assert body["model_version"] == "best_smoke"


def test_unauthorized_returns_401(client):
    resp = client.get("/api/record/list")
    assert resp.status_code == 401 and resp.json()["code"] == 40101
    assert client.get("/api/user/profile").status_code == 401
    assert client.post("/api/detect/image").status_code == 401


# ---------- 注册 / 登录 ----------

def test_register_and_login(client):
    name = f"reg_{uuid.uuid4().hex[:8]}"
    resp = client.post("/api/auth/register", json={
        "username": name, "password": "Abc123456", "email": f"{name}@test.com"})
    assert resp.status_code == 200 and resp.json()["data"]["username"] == name

    dup = client.post("/api/auth/register", json={"username": name, "password": "Abc123456"})
    assert dup.status_code == 409 and dup.json()["code"] == 40901

    bad = client.post("/api/auth/login", json={"username": name, "password": "Wrong123"})
    assert bad.status_code == 401 and bad.json()["code"] == 40102
    ok = client.post("/api/auth/login", json={"username": name, "password": "Abc123456"})
    assert ok.status_code == 200 and ok.json()["data"]["access_token"]


# ---------- 检测全链路 ----------

def test_detect_full_flow(client):
    _, token = make_user(client)
    data = _detect(client, token)
    assert isinstance(data["record_id"], int)
    assert data["model_version"] == "best_smoke"
    assert data["targets"][0]["class_name"] == "积灰"
    assert data["defect_summary"] == {"积灰": 1}
    assert data["advice"] and data["advice"][0]["level"] == "high"
    assert data["rendered_image_base64"].startswith("data:image/jpeg;base64,")
    assert data["result_image_url"].startswith("/api/files/results/")
    assert data["image_size"] == {"width": 640, "height": 480}


def test_upload_validation(client):
    _, token = make_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    big = client.post("/api/detect/image", headers=headers,
                      files={"file": ("big.jpg", b"x" * (10 * 1024 * 1024 + 1), "image/jpeg")})
    assert big.status_code == 400 and big.json()["code"] == 40002

    fake = client.post("/api/detect/image", headers=headers,
                       files={"file": ("fake.jpg", b"not an image", "image/jpeg")})
    assert fake.status_code == 400 and fake.json()["code"] == 40003

    bad_ext = client.post("/api/detect/image", headers=headers,
                          files={"file": ("doc.txt", make_test_image(), "text/plain")})
    assert bad_ext.status_code == 400 and bad_ext.json()["code"] == 40003

    broken = client.post("/api/detect/image", headers=headers,
                         files={"file": ("bad.png", b"\x89PNG\r\n\x1a\nbroken", "image/png")})
    assert broken.status_code == 400 and broken.json()["code"] == 40001


# ---------- 历史记录与属主隔离 ----------

def test_record_list_detail_export(client):
    _, token = make_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    data = _detect(client, token)

    lst = client.get("/api/record/list?page=1&page_size=5", headers=headers)
    assert lst.status_code == 200
    assert lst.json()["data"]["items"][0]["record_id"] == data["record_id"]

    det = client.get(f"/api/record/{data['record_id']}", headers=headers)
    assert det.status_code == 200
    assert det.json()["data"]["targets"] == data["targets"]

    img = client.get(data["result_image_url"], headers=headers)
    assert img.status_code == 200 and img.headers["content-type"].startswith("image")

    exp = client.get("/api/record/export", headers=headers)
    assert exp.status_code == 200 and "记录ID" in exp.content.decode("utf-8-sig")


def test_owner_isolation(client):
    _, token_a = make_user(client)
    _, token_b = make_user(client)
    data = _detect(client, token_a)

    resp = client.get(f"/api/record/{data['record_id']}",
                      headers={"Authorization": f"Bearer {token_b}"})
    assert resp.status_code == 403 and resp.json()["code"] == 40301
    assert client.get(data["result_image_url"],
                      headers={"Authorization": f"Bearer {token_b}"}).status_code == 404


# ---------- ONNX 后处理（纯函数，无需权重/运行时）----------

def test_onnx_postprocess_coordinate_mapping():
    """阈值过滤 + NMS + letterbox 坐标映射回原图。"""
    from app.services.inference import ONNXEngine

    # 640x480 原图 → 640x640 letterbox：ratio=1，左右0、上下各填充80
    meta = {"ratio": 1.0, "pad": (0.0, 80.0), "orig": (480, 640)}
    high = [100.0, 130.0, 40.0, 40.0, 0.1, 0.9, 0.1, 0.1, 0.1, 0.1]
    low = [300.0, 330.0, 40.0, 40.0, 0.1, 0.1, 0.1, 0.1, 0.1, 0.05]
    out = np.asarray([high, low], dtype=np.float32).T[None]  # (1, 4+nc, 2)

    targets = ONNXEngine._postprocess(out, meta)
    assert len(targets) == 1  # 低置信目标被 0.25 阈值过滤
    t = targets[0]
    assert set(t) == {"class_id", "class_name", "confidence", "bbox"}
    assert t["class_id"] == 1 and t["class_name"] == "积灰"
    assert t["confidence"] == 0.9
    assert t["bbox"] == [80.0, 30.0, 120.0, 70.0]


# ---------- 单次编码 / 上传防护 / WAL ----------

def test_result_image_reuses_single_jpeg_encoding(client):
    """内联 base64 与落盘结果图必须是同一份编码字节。"""
    import base64
    _, token = make_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    data = _detect(client, token)
    inline = base64.b64decode(data["rendered_image_base64"].split(",", 1)[1])
    stored = client.get(data["result_image_url"], headers=headers).content
    assert inline == stored


def test_empty_upload_rejected(client):
    _, token = make_user(client)
    resp = client.post("/api/detect/image",
                       headers={"Authorization": f"Bearer {token}"},
                       files={"file": ("empty.jpg", b"", "image/jpeg")})
    assert resp.status_code == 400


def test_pixel_limit_guard():
    from app.core.errors import BizError, CODE_PARAM
    from app.services.upload_check import validate_dimensions
    validate_dimensions(640, 480)
    try:
        validate_dimensions(50_000, 50_000)
    except BizError as e:
        assert e.code == CODE_PARAM
    else:
        raise AssertionError("超大像素未被拦截")


def test_sqlite_wal_enabled(_env):
    import sqlite3
    conn = sqlite3.connect(_env["db"])
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode == "wal"


# ---------- 算法侧 / 部署侧后处理口径一致 ----------

def test_postprocess_matches_algorithm_export():
    """同一 ONNX 输出，两侧必须给出相同的类别、置信度与坐标。"""
    import importlib.util
    import sys
    import types
    from pathlib import Path

    from app.core.pv_classes import ID_TO_ZH
    from app.services.postprocess import decode_detections

    for name in ("torch", "yaml"):
        sys.modules.setdefault(name, types.ModuleType(name))
    ul = types.ModuleType("ultralytics")
    ul.YOLO = object
    sys.modules.setdefault("ultralytics", ul)
    export_path = Path(__file__).resolve().parents[2] / "algorithm" / "export.py"
    spec = importlib.util.spec_from_file_location("_pv_export", export_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    meta = {"ratio": 1.0, "pad": (0.0, 80.0), "orig": (480, 640)}
    rows = [
        [100, 130, 40, 40, 0.1, 0.90, 0.10, 0.1, 0.1, 0.1],
        [102, 132, 40, 40, 0.1, 0.80, 0.10, 0.1, 0.1, 0.1],  # 同类高 IoU，应被抑制
        [100, 130, 40, 40, 0.1, 0.10, 0.85, 0.1, 0.1, 0.1],  # 同位置不同类，应保留
    ]
    out = np.asarray(rows, dtype=np.float32).T[None]

    backend_out = decode_detections(out, meta, 0.25, 0.45, ID_TO_ZH)
    algo_out = mod.postprocess_onnx(out, 0.25, 0.45, meta)

    def normalize(items):
        if items and isinstance(items[0], dict):
            return sorted((t["class_id"], t["confidence"], tuple(t["bbox"])) for t in items)
        return sorted((c, round(conf, 4),
                       (round(max(0.0, x1), 1), round(max(0.0, y1), 1),
                        round(min(640.0, x2), 1), round(min(480.0, y2), 1)))
                      for x1, y1, x2, y2, c, conf in items)

    assert len(backend_out) == 2  # 逐类 NMS：同类重叠抑制，跨类同位置保留
    assert normalize(backend_out) == normalize(algo_out)


# ---------- 限流 / 令牌撤销 / 输入防护 ----------

def test_login_rate_limit(client):
    name, _ = make_user(client)  # 首次登录占 1 次配额
    for _ in range(7):
        assert client.post("/api/auth/login",
                           json={"username": name, "password": "Wrong123"}).status_code == 401
    limited = client.post("/api/auth/login",
                          json={"username": name, "password": "Wrong123"})
    assert limited.status_code == 429 and limited.json()["code"] == 42901


def test_password_change_revokes_old_token(client):
    name, token = make_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    ok = client.put("/api/user/password", headers=headers,
                    json={"old_password": "Abc123456", "new_password": "Xyz789012"})
    assert ok.status_code == 200
    assert client.get("/api/user/profile", headers=headers).status_code == 401
    assert client.post("/api/auth/login",
                       json={"username": name, "password": "Xyz789012"}).status_code == 200


def test_csv_formula_guard_and_cors():
    from app.api.record import _csv_safe
    from app.core.config import settings
    assert _csv_safe("=1+1") == "'=1+1"
    assert _csv_safe("+SUM(A1)") == "'+SUM(A1)"
    assert _csv_safe("panel.jpg") == "panel.jpg"
    assert "*" not in settings.cors_origins


def test_image_filename_wildcard_not_matched(client):
    _, token = make_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    _detect(client, token)
    # %25 解码后为 '%'；若 LIKE 未转义会命中他人/非目标结果图
    assert client.get("/api/files/results/%25.jpg", headers=headers).status_code == 404
