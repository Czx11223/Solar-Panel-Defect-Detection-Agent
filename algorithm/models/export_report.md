# 模型导出报告（Export Report）

- 导出时间：2026-11-10 09:30:32
- 基线权重：app\ml\weights\best.pt
- 基线mAP@0.5：0.637742
- 导出参数：imgsz=640, opset=12, batch=1, simplify=True
- 运行环境：CPU: Intel64 Family 6 Model 154 Stepping 3, GenuineIntel；GPU: 无（CPU）；基准运行时: onnxruntime CPU / torch CPU
- 剪枝：未启用（默认关闭）

## 产物对比

| 产物 | 精度 | 体积(MB) | mAP@0.5 | 相对基线降幅 | 延迟mean/p95(ms) | ≤200ms | 结论 |
|---|---|---|---|---|---|---|---|
| best.onnx | FP32 | 11.7 | 0.614989 | +0.0228 | 未测 | — | 精度降幅超限，不建议部署 |

**部署建议**：暂无同时满足精度与延迟要求的产物；可尝试--int8量化、降低imgsz或降级模型规模（yolov8s→n）后重新导出。

注：延迟未测（未指定--benchmark）。

## 目标阈值核对

| 指标 | 目标 | 结果 |
|---|---|---|
| 单图推理延迟 | ≤200ms | 未测 |
| ONNX精度降幅 | ≤2% | 见上表 |
