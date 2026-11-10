"""后端API冒烟测试：覆盖spec.md第9章用例。

运行：cd backend && python -m pytest tests/ -v
覆盖：健康检查、鉴权、注册/登录、个人信息、检测全链路与校验分支、
历史列表/详情/导出、属主隔离、ONNX引擎路径。
"""

from __future__ import annotations

import uuid

from .conftest import make_test_image, make_user


def _detect(client, token, filename: str = "panel_test.jpg",
            img: bytes | None = None) -> dict:
    """以指定用户token执行检测，返回data（公共助手，保证记录归属正确）。"""
    files = {"file": (filename, img if img is not None else make_test_image(), "image/jpeg")}
    resp = client.post("/api/detect/image",
                       headers={"Authorization": f"Bearer {token}"}, files=files)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ---------- 1. 健康检查与未认证 ----------

def test_health(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["app"] and body["docs"] == "/docs"
    assert body["model_version"] == "best_smoke"


def test_unauthorized_returns_401(client):
    resp = client.get("/api/record/list")
    assert resp.status_code == 401 and resp.json()["code"] == 40101
    resp = client.get("/api/user/profile")
    assert resp.status_code == 401
    resp = client.post("/api/detect/image")
    assert resp.status_code == 401


# ---------- 2. 注册 ----------

def test_register_ok(client):
    name = f"reg_{uuid.uuid4().hex[:8]}"
    resp = client.post("/api/auth/register", json={
        "username": name, "password": "Abc123456",
        "email": f"{name}@test.com", "nickname": "张三",
    })
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == name


def test_register_duplicate_username(client):
    name, _ = make_user(client)
    resp = client.post("/api/auth/register", json={
        "username": name, "password": "Abc123456"})
    assert resp.status_code == 409
    assert resp.json()["code"] == 40901


def test_register_bad_email(client):
    resp = client.post("/api/auth/register", json={
        "username": f"reg_{uuid.uuid4().hex[:8]}",
        "password": "Abc123456", "email": "not-an-email"})
    assert resp.status_code == 400
    assert resp.json()["code"] == 40001


def test_register_weak_password(client):
    resp = client.post("/api/auth/register", json={
        "username": f"reg_{uuid.uuid4().hex[:8]}",
        "password": "onlyletters"})
    assert resp.status_code == 400


# ---------- 3. 登录 ----------

def test_login_ok_and_wrong_password(client):
    name, _ = make_user(client)
    bad = client.post("/api/auth/login", json={
        "username": name, "password": "Wrong123"})
    assert bad.status_code == 401 and bad.json()["code"] == 40102
    ok = client.post("/api/auth/login", json={
        "username": name, "password": "Abc123456"})
    assert ok.status_code == 200
    data = ok.json()["data"]
    assert data["token_type"] == "bearer" and data["access_token"]


# ---------- 4. 个人信息 ----------

def test_profile_flow(client):
    name, token = make_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/user/profile", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == name

    resp = client.put("/api/user/profile", headers=headers,
                      json={"nickname": "李四", "email": f"new_{name}@test.com"})
    assert resp.status_code == 200
    assert resp.json()["data"]["nickname"] == "李四"

    resp = client.put("/api/user/password", headers=headers,
                      json={"old_password": "Abc123456", "new_password": "Xyz789012"})
    assert resp.status_code == 200

    old = client.post("/api/auth/login", json={"username": name, "password": "Abc123456"})
    assert old.status_code == 401
    new = client.post("/api/auth/login", json={"username": name, "password": "Xyz789012"})
    assert new.status_code == 200


def test_profile_wrong_old_password(client):
    _, token = make_user(client)
    resp = client.put("/api/user/password",
                      headers={"Authorization": f"Bearer {token}"},
                      json={"old_password": "Wrong123", "new_password": "Xyz789012"})
    assert resp.status_code == 401 and resp.json()["code"] == 40102


# ---------- 5. 检测全链路 ----------

def test_detect_full_flow(client):
    _, token = make_user(client)
    data = _detect(client, token)
    assert isinstance(data["record_id"], int)
    assert data["model_version"] == "best_smoke"
    assert isinstance(data["targets"], list)
    assert isinstance(data["defect_summary"], dict)
    assert isinstance(data["advice"], list) and len(data["advice"]) >= 1
    assert data["rendered_image_base64"].startswith("data:image/jpeg;base64,")
    assert data["result_image_url"].startswith("/api/files/results/")
    assert data["image_size"] == {"width": 640, "height": 480}


# ---------- 6. 上传校验分支 ----------

def test_detect_oversize(client):
    _, token = make_user(client)
    big = b"x" * (10 * 1024 * 1024 + 1)
    resp = client.post("/api/detect/image",
                       headers={"Authorization": f"Bearer {token}"},
                       files={"file": ("big.jpg", big, "image/jpeg")})
    assert resp.status_code == 400 and resp.json()["code"] == 40002


def test_detect_fake_extension(client):
    _, token = make_user(client)
    resp = client.post("/api/detect/image",
                       headers={"Authorization": f"Bearer {token}"},
                       files={"file": ("fake.jpg", b"not an image", "image/jpeg")})
    assert resp.status_code == 400 and resp.json()["code"] == 40003


def test_detect_bad_extension(client):
    _, token = make_user(client)
    resp = client.post("/api/detect/image",
                       headers={"Authorization": f"Bearer {token}"},
                       files={"file": ("doc.txt", make_test_image(), "text/plain")})
    assert resp.status_code == 400 and resp.json()["code"] == 40003


def test_detect_corrupted_image(client):
    _, token = make_user(client)
    # 魔数正确但内容损坏：扩展名校验通过、解码失败 → 40001
    corrupted = b"\x89PNG\r\n\x1a\n" + b"broken-content-xxx"
    resp = client.post("/api/detect/image",
                       headers={"Authorization": f"Bearer {token}"},
                       files={"file": ("bad.png", corrupted, "image/png")})
    assert resp.status_code == 400 and resp.json()["code"] == 40001


# ---------- 7. 历史记录：列表/详情/导出 ----------

def test_record_list_detail_export(client):
    _, token = make_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    data = _detect(client, token)
    record_id = data["record_id"]

    lst = client.get("/api/record/list?page=1&page_size=5", headers=headers)
    assert lst.status_code == 200
    items = lst.json()["data"]["items"]
    assert items and items[0]["record_id"] == record_id

    det = client.get(f"/api/record/{record_id}", headers=headers)
    assert det.status_code == 200
    detail = det.json()["data"]
    assert detail["targets"] == data["targets"]
    assert detail["image_url"].startswith("/api/files/uploads/")

    img = client.get(data["result_image_url"], headers=headers)
    assert img.status_code == 200
    assert img.headers["content-type"].startswith("image")

    exp = client.get("/api/record/export", headers=headers)
    assert exp.status_code == 200
    text = exp.content.decode("utf-8-sig")
    assert "记录ID" in text and "推理耗时ms" in text
    assert "panel_test.jpg" in text


# ---------- 8. 属主隔离 ----------

def test_owner_isolation(client):
    _, token_a = make_user(client)
    _, token_b = make_user(client)
    data = _detect(client, token_a)

    resp = client.get(f"/api/record/{data['record_id']}",
                      headers={"Authorization": f"Bearer {token_b}"})
    assert resp.status_code == 403 and resp.json()["code"] == 40301

    resp = client.get(data["result_image_url"],
                      headers={"Authorization": f"Bearer {token_b}"})
    assert resp.status_code == 404


def test_record_not_found(client):
    _, token = make_user(client)
    resp = client.get("/api/record/999999",
                      headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404 and resp.json()["code"] == 40401


# ---------- 9. ONNX引擎路径 ----------

def test_onnx_engine(_env):
    """合成pt → 导出onnx → ONNXEngine推理，验证ONNX推理链路与坐标映射。"""
    from pathlib import Path

    from ultralytics import YOLO

    from app.services.inference import ONNXEngine

    yolo = YOLO(str(_env["pt_path"]))
    exported = yolo.export(format="onnx", imgsz=640, opset=12,
                           simplify=True, dynamic=False, batch=1)
    onnx_path = Path(exported) if exported else _env["weights_dir"] / "best_smoke.onnx"
    assert onnx_path.is_file(), onnx_path

    engine = ONNXEngine(onnx_path)
    assert engine.available and engine.model_version == "best_smoke"

    import cv2
    import numpy as np
    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    targets, elapsed = engine.infer(img)
    assert isinstance(targets, list)
    assert isinstance(elapsed, float) and elapsed >= 0
    for t in targets:
        assert set(t) == {"class_id", "class_name", "confidence", "bbox"}
        x1, y1, x2, y2 = t["bbox"]
        assert 0 <= x1 < x2 <= 640 and 0 <= y1 < y2 <= 480  # 坐标映射回原图范围
