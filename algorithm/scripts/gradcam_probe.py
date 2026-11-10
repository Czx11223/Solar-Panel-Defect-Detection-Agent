"""Grad-CAM 弱监督定位探针：验证类别热力图能否聚焦真实缺陷位置。

对 YOLOv8 Detect 分类分支（cv3 倒数第二层 Conv 输出）做梯度加权，
生成目标类别的热力图并叠加到原图输出 PNG，供人工核对。
"""

import argparse
from pathlib import Path

import cv2
import numpy as np
import torch

from ultralytics import YOLO

BASE = Path(__file__).resolve().parent.parent


def letterbox(img: np.ndarray, sz: int = 640):
    h, w = img.shape[:2]
    r = sz / max(h, w)
    nw, nh = int(round(w * r)), int(round(h * r))
    im2 = cv2.resize(img, (nw, nh))
    canvas = np.full((sz, sz, 3), 114, np.uint8)
    ox, oy = (sz - nw) // 2, (sz - nh) // 2
    canvas[oy:oy + nh, ox:ox + nw] = im2
    x = torch.from_numpy(canvas.transpose(2, 0, 1)).float().div(255).unsqueeze(0)
    return x, canvas, ox, oy, r


def gradcam(model, x, target_cls: int, det_idxs=(0, 1, 2)):
    dm = model.model
    m = dm.model
    dm.eval()
    for p in dm.parameters():
        p.requires_grad_(True)
    detect = m[-1]

    acts: dict[int, torch.Tensor] = {}
    logits: dict[int, torch.Tensor] = {}

    def make_hook(i: int, tag: str):
        def hook(_mod, _inp, out):
            if tag == "act":
                out.retain_grad()
                acts[i] = out
            else:
                logits[i] = out
        return hook

    hooks = []
    for i in det_idxs:
        hooks.append(detect.cv3[i][-2].register_forward_hook(make_hook(i, "act")))
        hooks.append(detect.cv3[i][-1].register_forward_hook(make_hook(i, "logit")))

    with torch.enable_grad():
        _preds = dm._predict_once(x)
        cams = {}
        for i in det_idxs:
            if i not in acts or i not in logits:
                continue
            act = acts[i]                              # (bs, C, na, h, w)
            logit = logits[i]                          # (bs, nc, na, h, w)
            score = logit[0, target_cls].max()
            dm.zero_grad()
            score.backward(retain_graph=True)
            grad = act.grad
            if grad is None:
                continue
            wts = grad.mean(dim=(0, 2, 3), keepdim=True)          # (1, C, 1, 1)
            cam = torch.relu((wts * act).sum(dim=1))              # (1, h, w)
            cam = cam[0].detach().cpu().numpy()                   # (h, w)
            if cam.max() > 0:
                cam = (cam - cam.min()) / (cam.max() - cam.min())
            cams[i] = cam
    for h in hooks:
        h.remove()
    return cams


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True, help="模型权重路径")
    ap.add_argument("--img", required=True, help="测试图像路径")
    ap.add_argument("--cls", type=int, default=3, help="目标类别id")
    ap.add_argument("--out", required=True, help="输出PNG路径")
    ap.add_argument("--imgsz", type=int, default=640)
    args = ap.parse_args()

    img = cv2.imread(args.img)
    if img is None:
        raise SystemExit(f"读图失败: {args.img}")
    h, w = img.shape[:2]
    x, canvas, ox, oy, r = letterbox(img, args.imgsz)

    model = YOLO(args.weights)
    cams = gradcam(model, x, args.cls)
    if not cams:
        raise SystemExit("未生成任何热力图")

    # 用最大尺度（P3）热力图叠加
    best_i = max(cams, key=lambda k: cams[k].shape)
    cam = cams[best_i]
    cam_up = cv2.resize(cam, (args.imgsz, args.imgsz), interpolation=cv2.INTER_LINEAR)
    cam_up = cam_up[oy:oy + int(h * r), ox:ox + int(w * r)]
    cam_up = cv2.resize(cam_up, (w, h), interpolation=cv2.INTER_LINEAR)
    cam_uint = np.uint8(255 * cam_up)
    heat = cv2.applyColorMap(cam_uint, cv2.COLORMAP_JET)
    overlay = cv2.addWeighted(img, 0.6, heat, 0.45, 0)

    # 热力阈值连通域 -> 候选框
    thr = cv2.threshold(cam_uint, 120, 255, cv2.THRESH_BINARY)[1]
    cnts, _ = cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = sorted((cv2.boundingRect(c) for c in cnts),
                   key=lambda b: b[2] * b[3], reverse=True)[:4]
    for bx, by, bw, bh in boxes:
        if bw * bh < 0.002 * w * h:
            continue
        cv2.rectangle(overlay, (bx, by), (bx + bw, by + bh), (0, 255, 255), 3)

    cv2.imwrite(args.out, overlay)
    print(f"输出: {args.out}")
    print(f"热力框(像素): {[list(b) for b in boxes[:4]]}")
    print(f"归一化框: {[(round((b[0]+b[2]/2)/w,3), round((b[1]+b[3]/2)/h,3), round(b[2]/w,3), round(b[3]/h,3)) for b in boxes[:4]]}")


if __name__ == "__main__":
    main()
