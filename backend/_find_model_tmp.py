import glob
import os
import re

b = r"D:\peixunwenjian\2026.9.14-9.28\backend"
for p in sorted(glob.glob(os.path.join(b, "**", "*.py"), recursive=True)):
    s = open(p, encoding="utf-8", errors="replace").read()
    for m in re.finditer(r"[A-Za-z0-9_./\\-]+\.(?:pt|onnx)", s):
        print(os.path.relpath(p, b), "->", m.group(0))
