"""轻量矩形框标注工具（tkinter，PascalVOC XML 输出，兼容 LabelImg 格式）。

用法：
    python annotation_tool.py <图像目录> <类别文件> [--save-dir <XML输出目录>]

操作：
    鼠标左键拖拽画框；右键/选中后 Del 删除选中框；
    类别切换：点右侧按钮或按 1/2（依类别文件顺序）；
    保存：Ctrl+S 或「保存并下一张」按钮（PascalVOC XML 写到图像同目录）；
    跳过（图上无缺陷）：「跳过并下一张」按钮，记入 skipped.txt；
    ←/→ 上一张/下一张。
"""

import argparse
import os
import sys
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


class Box:
    __slots__ = ("x0", "y0", "x1", "y1", "cls")

    def __init__(self, x0, y0, x1, y1, cls):
        self.x0, self.y0, self.x1, self.y1, self.cls = x0, y0, x1, y1, cls


class Annotator:
    def __init__(self, img_dir: Path, classes: list[str], save_dir: Path):
        self.img_dir = img_dir
        self.classes = classes
        self.save_dir = save_dir
        self.files = sorted(
            p for p in img_dir.iterdir()
            if p.suffix.lower() in IMG_EXTS and not p.name.startswith("~"))
        self.idx = 0
        self.boxes: list[Box] = []
        self.cur_cls = 0
        self.img = None
        self.photo = None
        self.scale = 1.0
        self.offset = (0, 0)
        self.drag_start = None
        self.sel = -1
        self.dirty = False
        self.skipped = (img_dir / "skipped.txt") if False else (save_dir / "skipped.txt")

        self.root = tk.Tk()
        self.root.title("矩形框标注工具 - 光伏缺陷")
        self._build_ui()
        self._load()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Control-s>", lambda e: self._save())
        self.root.bind("<Left>", lambda e: self._nav(-1))
        self.root.bind("<Right>", lambda e: self._nav(1))
        for i, c in enumerate(classes[:9]):
            self.root.bind(str(i + 1), lambda e, k=i: self._set_cls(k))
        self.root.bind("<Delete>", lambda e: self._del_sel())
        self.root.bind("<Escape>", lambda e: self._del_sel())

    # ---------- UI ----------
    def _build_ui(self):
        top = tk.Frame(self.root)
        top.pack(fill=tk.X)
        self.lb_info = tk.Label(top, text="", font=("Consolas", 11))
        self.lb_info.pack(side=tk.LEFT, padx=6)
        btn_prev = tk.Button(top, text="◀ 上一张", command=lambda: self._nav(-1))
        btn_prev.pack(side=tk.LEFT, padx=2)
        btn_next = tk.Button(top, text="下一张 ▶", command=lambda: self._nav(1))
        btn_next.pack(side=tk.LEFT, padx=2)
        btn_skip = tk.Button(top, text="跳过(无缺陷)", command=self._skip, bg="#ffd")
        btn_skip.pack(side=tk.LEFT, padx=2)
        btn_save = tk.Button(top, text="保存并下一张", command=self._save_next, bg="#dfd")
        btn_save.pack(side=tk.LEFT, padx=2)

        main = tk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(main, bg="#222", cursor="crosshair")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        side = tk.Frame(main, width=190)
        side.pack(side=tk.RIGHT, fill=tk.Y)
        tk.Label(side, text="缺陷类别", font=("", 11, "bold")).pack(pady=6)
        self.cls_btns = []
        colors = ["#f66", "#c6f"]
        for i, c in enumerate(self.classes):
            b = tk.Button(side, text=f"{i + 1}. {c}", font=("", 10),
                          command=lambda k=i: self._set_cls(k))
            b.pack(fill=tk.X, padx=8, pady=2)
            self.cls_btns.append(b)
        tk.Label(side, text="操作提示", font=("", 10, "bold")).pack(pady=(14, 2))
        tips = ("左键拖拽 = 画框\n"
                "1/2 = 切类别\n"
                "Delete = 删选中框\n"
                "Ctrl+S = 保存\n"
                "←/→ = 切换图片\n"
                "跳过 = 图上无缺陷")
        tk.Label(side, text=tips, font=("", 9), justify=tk.LEFT, fg="#555").pack(padx=8)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<ButtonPress-3>", self._on_right)

    # ---------- 图像加载 ----------
    def _load(self):
        if self.dirty:
            self._save()
        if not self.files:
            self.lb_info.config(text="目录无图像")
            return
        p = self.files[self.idx]
        self.img = Image.open(p).convert("RGB")
        self._fit_canvas()
        xml = self.save_dir / (p.stem + ".xml")
        self.boxes = self._parse_existing(xml) if xml.exists() else []
        self.sel = -1
        self.dirty = False
        self._refresh()

    def _fit_canvas(self):
        cw = max(self.canvas.winfo_width(), 400)
        ch = max(self.canvas.winfo_height(), 400)
        iw, ih = self.img.size
        self.scale = min(cw / iw, ch / ih, 1.5)
        self.offset = ((cw - iw * self.scale) / 2, (ch - ih * self.scale) / 2)
        self.photo = ImageTk.PhotoImage(
            self.img.resize((int(iw * self.scale), int(ih * self.scale)),
                            Image.LANCZOS))

    def _parse_existing(self, xml: Path) -> list[Box]:
        import xml.etree.ElementTree as ET
        boxes = []
        try:
            root = ET.parse(xml).getroot()
        except Exception:
            return boxes
        for obj in root.iter("object"):
            name = (obj.findtext("name") or "").strip()
            if name not in self.classes:
                continue
            b = obj.find("bndbox")
            if b is None:
                continue
            boxes.append(Box(
                float(b.findtext("xmin")), float(b.findtext("ymin")),
                float(b.findtext("xmax")), float(b.findtext("ymax")),
                self.classes.index(name)))
        return boxes

    # ---------- 画布交互 ----------
    def _to_img(self, cx, cy):
        ox, oy = self.offset
        return ((cx - ox) / self.scale, (cy - oy) / self.scale)

    def _on_press(self, e):
        self.drag_start = (e.x, e.y)

    def _on_drag(self, e):
        if not self.drag_start:
            return
        self.canvas.coords("drag", self.drag_start[0], self.drag_start[1], e.x, e.y)

    def _on_release(self, e):
        if not self.drag_start:
            return
        x0, y0 = self._to_img(*self.drag_start)
        x1, y1 = self._to_img(e.x, e.y)
        self.drag_start = None
        self.canvas.delete("drag")
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        iw, ih = self.img.size
        if x1 - x0 < 3 or y1 - y0 < 3 or x0 < 0 or y0 < 0 or x1 > iw or y1 > ih:
            return
        self.boxes.append(Box(x0, y0, x1, y1, self.cur_cls))
        self.sel = len(self.boxes) - 1
        self.dirty = True
        self._refresh()

    def _on_right(self, e):
        x, y = self._to_img(e.x, e.y)
        best, bd = -1, 1e9
        for i, b in enumerate(self.boxes):
            if b.x0 <= x <= b.x1 and b.y0 <= y <= b.y1:
                d = min(x - b.x0, b.x1 - x, y - b.y0, b.y1 - y)
                if d < bd:
                    bd, best = d, i
        if best >= 0:
            self.sel = best
            self.dirty = True
            self._refresh()

    def _del_sel(self):
        if 0 <= self.sel < len(self.boxes):
            self.boxes.pop(self.sel)
            self.sel = -1
            self.dirty = True
            self._refresh()

    # ---------- 渲染 ----------
    def _refresh(self):
        self.canvas.delete("all")
        ox, oy = self.offset
        self.canvas.create_image(ox, oy, anchor=tk.NW, image=self.photo)
        colors = ["#ff4444", "#dd66ff"]
        for i, b in enumerate(self.boxes):
            x0 = ox + b.x0 * self.scale
            y0 = oy + b.y0 * self.scale
            x1 = ox + b.x1 * self.scale
            y1 = oy + b.y1 * self.scale
            tag = "sel" if i == self.sel else ""
            self.canvas.create_rectangle(x0, y0, x1, y1, outline=colors[b.cls % 2],
                                         width=2 if not tag else 3,
                                         tags=tag)
            self.canvas.create_text(x0 + 2, max(y0 - 6, 2), anchor=tk.SW,
                                    text=f"{i + 1}:{self.classes[b.cls]}",
                                    fill=colors[b.cls % 2], font=("", 9, "bold"),
                                    tags=tag)
        name = self.files[self.idx].name if self.files else "-"
        self.lb_info.config(
            text=f"[{self.idx + 1}/{len(self.files)}] {name}  框数:{len(self.boxes)}  类别:{self.classes[self.cur_cls]}")

    # ---------- 保存/导航 ----------
    def _write_xml(self, p: Path):
        import xml.etree.ElementTree as ET
        from xml.dom import minidom
        root = ET.Element("annotation")
        ET.SubElement(root, "folder").text = str(self.img_dir)
        ET.SubElement(root, "filename").text = p.name
        size = ET.SubElement(root, "size")
        ET.SubElement(size, "width").text = str(self.img.size[0])
        ET.SubElement(size, "height").text = str(self.img.size[1])
        ET.SubElement(size, "depth").text = "3"
        for b in self.boxes:
            obj = ET.SubElement(root, "object")
            ET.SubElement(obj, "name").text = self.classes[b.cls]
            ET.SubElement(obj, "truncated").text = "0"
            ET.SubElement(obj, "difficult").text = "0"
            bb = ET.SubElement(obj, "bndbox")
            ET.SubElement(bb, "xmin").text = str(int(round(b.x0)))
            ET.SubElement(bb, "ymin").text = str(int(round(b.y0)))
            ET.SubElement(bb, "xmax").text = str(int(round(b.x1)))
            ET.SubElement(bb, "ymax").text = str(int(round(b.y1)))
        raw = ET.tostring(root, encoding="utf-8")
        self.save_dir.mkdir(parents=True, exist_ok=True)
        (self.save_dir / (p.stem + ".xml")).write_bytes(
            minidom.parseString(raw).toprettyxml(indent="  ").encode("utf-8"))
        self.dirty = False

    def _save(self):
        if not self.files:
            return
        self._write_xml(self.files[self.idx])
        self.lb_info.config(text=self.lb_info.cget("text") + "  [已保存]")

    def _save_next(self):
        self._save()
        if self.idx < len(self.files) - 1:
            self._nav(1)

    def _skip(self):
        if not self.files:
            return
        p = self.files[self.idx]
        self.skipped.parent.mkdir(parents=True, exist_ok=True)
        with self.skipped.open("a", encoding="utf-8") as f:
            f.write(p.name + "\n")
        self.boxes = []
        self.dirty = False
        self._nav(1)

    def _nav(self, d):
        if not self.files:
            return
        if self.dirty:
            self._save()
        self.idx = (self.idx + d) % len(self.files)
        self._load()

    def _set_cls(self, k):
        self.cur_cls = k % len(self.classes)
        self._refresh()

    def _on_close(self):
        if self.dirty:
            self._save()
        self.root.destroy()

    def run(self):
        self.root.geometry("1100x760")
        self.root.after(200, self._load)
        self.root.mainloop()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("img_dir", help="图像目录")
    ap.add_argument("classes", help="类别文件（每行一个）")
    ap.add_argument("--save-dir", default=None, help="XML输出目录（默认=图像目录）")
    args = ap.parse_args()
    img_dir = Path(args.img_dir)
    classes = [ln.strip() for ln in
               Path(args.classes).read_text(encoding="utf-8").splitlines() if ln.strip()]
    save_dir = Path(args.save_dir) if args.save_dir else img_dir
    if not classes:
        raise SystemExit("类别文件为空")
    Annotator(img_dir, classes, save_dir).run()


if __name__ == "__main__":
    main()
