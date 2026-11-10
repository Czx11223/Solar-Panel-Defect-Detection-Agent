# 模型权重部署目录

权重文件不纳入版本库（见根目录 `.gitignore`），须在部署时手工放置到本目录。

## 加载规则

引擎按文件扩展名自动选择，优先级 `*.onnx` > `*.pt`；`model_version` 取文件名（不含扩展名）。

| 文件 | 引擎 | 依赖 | 说明 |
|---|---|---|---|
| `best.onnx` | ONNX Runtime | `requirements.txt` | 推荐。由 `algorithm/export.py` 导出，是「单图 ≤ 200ms」指标的验证对象 |
| `best.pt` | ultralytics YOLO | `requirements-pt.txt`（额外安装） | 回退路径，延迟随 CPU 性能变化 |

两者皆无时 `/api/detect/image` 返回 50301（模型服务未就绪），注册/登录/历史等接口不受影响。

## 放置方式

```powershell
# ONNX（推荐）：在 algorithm/ 目录执行
python export.py --skip-eval --benchmark
Copy-Item ..\algorithm\models\best.onnx .\app\ml\weights\

# 或 PT 回退
Copy-Item ..\algorithm\runs\detect\train_final-2\weights\best.pt .\app\ml\weights\best.pt
```

## 版本登记

`model_version` 建议使用 `yolov8s-v1.0` 风格的可追溯命名（把权重文件改成同名即可），
换版须重新通过评估指标验收（mAP@0.5 ≥ 75%、缺陷召回率 ≥ 80%），并同步 `docs/model_eval_report.md`。

> 当前目录内的 `best.pt` 与算法侧最终训练产出并非同一文件（体积不一致），
> 上线前请核对后替换，避免评估结果与实际部署权重脱节。
