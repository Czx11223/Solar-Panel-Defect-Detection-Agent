# 技术方案规格说明书（Spec）

| 项目 | 内容 |
|---|---|
| 项目名称 | 光伏面板缺陷检测系统 |
| 文档版本 | V1.0.0 |
| 编写日期 | 2026-09-14（2026-09-15 升级为全量交付方案版） |
| 文档状态 | 已确认（2026-09-15，D1–D38 按建议默认值执行；遗留执行项见第14章） |
| 编制依据 | 《光伏面板缺陷检测系统项目任务书V1.0.0》 |

本说明书汇总系统全量技术方案（算法、后端、前端、集成部署、答辩文档五类交付物）。功能需求见 [prd.md](prd.md)，架构见 [architecture.md](architecture.md)，数据库见 [db_design.md](db_design.md)，目录结构见 [project_structure.md](project_structure.md)，任务计划见 [tasks.md](tasks.md)，验收清单见 [checklist.md](checklist.md)。

## 1 范围与依据

对应任务书第四章全部10项任务，交付五类内容：

| 交付类别 | 对应任务书任务 | 交付物 |
|---|---|---|
| 1 算法 | 任务2/3/4 | 数据集处理脚本、训练/评估/ONNX导出脚本（algorithm/） |
| 2 后端 | 任务6 | FastAPI 全套代码 + OpenAPI 文档（backend/、docs/api_doc.md） |
| 3 前端 | 任务5/7 | React 完整页面代码（frontend/） |
| 4 集成与文档 | 任务8/9 | 部署运维手册、测试报告、PRD、数据库设计（docs/） |
| 5 答辩文档 | 任务10 | AI协作教程、PPT大纲、项目说明、RAG语料库与提示词（docs/、rag/） |

## 2 技术栈

与任务书3.2核心技术表完全一致，不新增、不替换：

| 技术模块 | 技术选型 | 用途 |
|---|---|---|
| 开发语言 | Python 3.12+ | 后端与算法开发 |
| 深度学习框架 | PyTorch / Ultralytics | 模型训练与推理 |
| 网络模型 | YOLOv8（COCO预训练） | 六类面板状态目标检测 |
| 图像处理 | OpenCV / PIL | 图像预处理、增强与结果图渲染 |
| 后端服务 | FastAPI | RESTful API |
| 前端框架 | React | Web界面 |
| UI组件库 | TailwindCSS / Ant Design | 界面组件与样式 |
| 数据库 | sqlite3 | 用户与检测记录持久化 |

工程配套（不改变任务书技术栈）：前端构建工具 Vite 5（D32）、TypeScript 严格模式、Python 依赖管理 pip + requirements.txt、接口调试用 FastAPI 自带交互文档（/docs）。

## 3 总体架构

前后端分离B/S架构，四层划分：前端Web客户端（React + antd + Tailwind）、后端API服务层（FastAPI）、AI推理层（YOLOv8 双引擎）、数据存储层（SQLite + storage 图像目录）。分层职责与架构图见 [architecture.md](architecture.md)。

## 4 检测类别与业务约束

### 4.1 六类检测类别

| 类别ID | 类别名称 | 英文标识 | 状态说明 | 运维建议 |
|---|---|---|---|---|
| 0 | 清洁 | Clean | 面板表面无遮挡、无明显缺陷 | 状态正常，维持现有巡检周期 |
| 1 | 积灰 | Dusty | 表面灰尘沉积造成遮挡 | 安排清洗作业，恢复发电效率 |
| 2 | 鸟粪 | Bird-drop | 鸟粪沉积，局部遮挡 | 尽快局部清洁，防止长期遮挡引发热斑 |
| 3 | 电损伤 | Electrical-damage | 电弧、热斑导致的烧蚀痕迹 | 安排停机检查与专业检修 |
| 4 | 物理损伤 | Physical-Damage | 破裂、崩边等机械损伤 | 评估损伤程度，安排检修或更换 |
| 5 | 积雪 | Snow-Covered | 积雪覆盖面板 | 视积雪与发电情况安排除雪或等待自然融化 |

### 4.2 业务约束（任务书硬性要求，系统内必须体现）

- **巡检结果免责声明**：检测结果及运维建议仅作为运维辅助参考，不构成处置决策依据；最终处置决策须由具备资质的专业人员依据现场情况作出（随系统展示：检测结果页底部 + 页脚）。
- **模型局限性声明**：模型仅识别上述6类状态；受拍摄角度、光照、遮挡等因素影响可能存在漏检/误检；置信度低于阈值的缺陷不会展示；检测结果以实际部署权重为准（README 与测试报告均声明）。
- **数据隐私保护条款**：用户数据仅用于本系统检测服务，不外传、不用于其他用途；密码加盐哈希存储；记录与图像按用户属主隔离，接口校验资源所有权。

## 5 API设计

RESTful风格，统一前缀 /api，请求与响应体为JSON（文件上传为multipart/form-data）。完整接口文档见 [api_doc.md](api_doc.md)（配合 FastAPI /docs 交互文档）与 [backend_api_spec.md](backend_api_spec.md)。

| # | 方法 | 路径 | 功能 | 需登录 |
|---|---|---|---|---|
| 1 | POST | /api/auth/register | 注册 | 否 |
| 2 | POST | /api/auth/login | 登录，返回访问凭证 | 否 |
| 3 | GET | /api/user/profile | 查看个人信息 | 是 |
| 4 | PUT | /api/user/profile | 修改个人信息（昵称/邮箱） | 是 |
| 5 | PUT | /api/user/password | 修改密码（验证原密码） | 是 |
| 6 | POST | /api/detect/image | 上传图像并执行检测 | 是 |
| 7 | GET | /api/record/list | 历史记录列表（分页，时间倒序） | 是 |
| 8 | GET | /api/record/{record_id} | 检测记录详情 | 是 |
| 9 | GET | /api/record/export | 导出检测记录（CSV） | 是 |
| 10 | GET | /api/files/uploads/{filename} | 上传原图访问 | 是 |
| 11 | GET | /api/files/results/{filename} | 标注结果图访问 | 是 |

统一响应结构 `{code, message, data}`（成功 code=0；健康检查 /、CSV 导出、图像文件流不包装）。鉴权：JWT Bearer Token（Authorization 头），前端 axios 拦截器自动注入，40101 错误码触发前端清 token 并跳转登录页。

## 6 AI推理层方案

1. **预处理**：OpenCV 解码 → BGR转RGB → letterbox 等比缩放至640×640（stride=32对齐）→ 像素归一化至0–1（内存优先，不落盘临时文件）
2. **推理**：双引擎自动探测（D25）——优先加载 ONNX（onnxruntime，性能达标）；无 ONNX 时回退 .pt（ultralytics）；权重缺失返回 50301
3. **后处理**：置信度阈值0.25（D7）、NMS IoU 0.45 → 坐标映射回原图 → 绘制检测框/类别/置信度生成标注结果图（base64 返回前端，另存 storage/results/）

性能验收：单图推理 ≤200ms（部署环境实测，不含传输与渲染）；推理耗时与 model_version 随记录保存。

## 7 模型训练方案

**数据准备**（algorithm/scripts/）：

- 数据源：Kaggle "Solar Panel Images" 数据集（六类可见光RGB图像，无边界框标注，需 LabelImg 人工标注，操作指引见 [dataset_readme.md](dataset_readme.md)）
- 标注转换 convert_labels.py（LabelImg XML → YOLO txt，含 --preview 抽查，D15）
- 数据集划分 split_dataset.py：8:1:1 分层抽样（保持类别比例），生成 data.yaml 与 class_weights.json
- 数据增强 augment.py：随机翻转、±15°旋转（D14）、亮度扰动、Mosaic拼接 + 类别加权采样（因子≤3，D19）

**模型训练**（algorithm/train.py）：

- COCO 预训练迁移学习，模型规模 yolov8s（CPU 不达标降级 yolov8n，D16）
- 损失：YOLOv8 默认联合损失（边框回归 + 分类 + DFL）
- 优化器：AdamW lr0=0.001（可切 SGD，D17）+ 余弦退火学习率
- 早停：验证集 fitness 监控；断点续训；在线增强保留 Mosaic/HSV/翻转、关闭在线旋转（D23）

**评估**（algorithm/eval.py，验收口径）：

| 指标 | 验收线 | 评估方式 |
|---|---|---|
| mAP@0.5 | ≥ 75% | 测试集总体 |
| 主要缺陷类别召回率 | ≥ 80% | 积灰、鸟粪、电损伤、物理损伤、积雪各类（conf=0.25 + IoU=0.5 工程口径，D22） |
| 单图推理耗时 | ≤ 200ms | 部署环境实测（D6：GPU 型号或纯 CPU 待真实模型阶段明确） |

产出六类 PR 曲线与各类别 AP，自动填充 [model_eval_report.md](model_eval_report.md)。

**模型导出**（algorithm/export.py）：

- ONNX 导出（FP32 默认，--half/--int8 可选并自动 mAP 核对，D21）
- 结构化剪枝：torch-pruning ≥1.6.0，安全集合策略（只剪下采样Conv、SPPF出入口、C2f出口cv2，不剪C2f内部与Detect头，D20）
- 导出产物入 algorithm/models/（D18），含延迟基准 --benchmark

## 8 数据库方案

SQLite3，user 表与 detect_record 表（user_id 外键，ON DELETE CASCADE，detect_result 为 JSON 存储检测结果）。连接使用 check_same_thread=False 适配 async 路由；访问层原生 sqlite3 + DAO，不引入 ORM（D30）。字段、索引、DDL 见 [db_design.md](db_design.md)。

## 9 安全设计

| 环节 | 措施 |
|---|---|
| 密码存储 | 标准库 pbkdf2_hmac 加盐哈希（D26），不落明文 |
| 登录态 | JWT：环境变量密钥（PV_SECRET_KEY）+ 24h 过期（D27） |
| 权限隔离 | 记录与图像按用户隔离，接口校验属主 |
| 数据用途 | 用户数据仅用于本系统检测服务，不外传 |
| 数据库存储加密 | 敏感字段应用层加密 + 部署层磁盘加密（D5） |
| 图片处理 | 内存优先，原图/结果图按日期落盘（D29），访问需鉴权 |

## 10 前端方案

- 工程：React 18 + TypeScript 严格模式 + Vite 5 + TailwindCSS（布局）+ Ant Design 5（组件）（D31/D32）
- 路由：HashRouter（D34）；状态：不引入全局状态库（D33）；token 存 localStorage（D35）
- 页面：登录/注册页、检测页（ImageUploader 拖拽/点选/预览/校验 + DetectionViewer 检测框/置信度/运维建议）、历史记录页（列表/详情/原图与结果图对比/CSV导出）、个人中心（Header 用户名+退出，D38）
- 响应式：md(768px) 主断点（D37），兼容 PC 与移动端；兼容 Chrome/Firefox/Safari/Edge
- 上传校验：格式+大小前端拦截与后端一致，魔数校验仅后端（D36）；图像访问走 blob + objectURL 携带鉴权头
- 错误处理：网络异常、上传超限、推理失败均有提示；40101 自动清 token 跳登录

## 11 部署方案

- 后端：uvicorn 运行 FastAPI（端口8000），启动时自动建库并加载模型权重（权重目录 backend/app/ml/weights/，ONNX 优先、pt 回退）
- 前端：开发期 Vite 开发服务器（端口5173，proxy 代理 /api），部署期 Nginx 托管静态产物（D10）
- 数据库：SQLite 单文件 + storage 图像目录，随应用同机部署
- 环境变量：PV_SECRET_KEY（JWT密钥）、VITE_API_BASE（前端API地址）
- 详细步骤见 [deploy_manual.md](deploy_manual.md)

## 12 测试方案

- 后端：18 个冒烟用例（注册/登录/鉴权/上传校验/检测/记录/导出/属主隔离/ONNX引擎），pytest 实测 18/18 通过；并发冒烟（20线程×100请求）
- 前端：8 个 E2E 用例（登录注册/上传校验/检测/历史/导出/响应式）；npm run build 零错误
- 结果汇总见 [test_report.md](test_report.md)

## 13 决策记录（D1–D38）

各阶段决策点均已确认，完整记录见 [project_spec_doc.md](project_spec_doc.md)：

- D1–D10（阶段0 系统设计）：数据集标注策略=全量标注/均衡抽样；上传上限10MB；导出CSV；JWT；存储加密=应用层+磁盘；性能硬件待明确；置信度阈值0.25；邮箱选填；免责声明=结果页+页脚；托管=开发Vite/部署Nginx
- D11–D15（阶段1 数据）：类别名英文标识中文映射；未标注图像排除并列清单；增强样本并入train（augm_前缀）；±15°旋转；--preview抽查
- D16–D23（阶段2 模型）：yolov8s（降级yolov8n）；AdamW默认可切SGD；脚本命名train/eval/export.py；加权采样因子≤3；剪枝安全集合策略默认关闭；ONNX FP32默认--half/--int8可选；召回率conf=0.25+IoU=0.5工程口径；关闭在线旋转
- D24–D30（阶段3/4 部署与后端）：接口路径对齐；双引擎onnx优先pt回退；pbkdf2_hmac；JWT密钥+24h；六类运维建议模板+置信度三档分级；图片内存优先按日期落盘；原生sqlite3+DAO
- D31–D38（阶段5 前端）：antd组件/Tailwind布局；Vite 5；无全局状态库；HashRouter；token存localStorage；前端校验与后端一致魔数仅后端；md(768px)断点；个人信息=Header用户名+退出

## 14 遗留执行项与风险

| 事项 | 状态 | 说明 |
|---|---|---|
| 真实数据集训练 | 待执行 | 需人工下载Kaggle数据集 + LabelImg标注（阶段1/2） |
| 模型权重部署 | 待执行 | 训练后导出ONNX并部署至 backend/app/ml/weights/，登记 model_version |
| 性能指标实测 | 待执行 | mAP/召回率/推理耗时需真实模型复测（当前权重缺失返回50301，P1） |
| 答辩PPT成品 | 待执行 | 按 [report_ppt_outline.md](report_ppt_outline.md) 制作，含界面截图与PR曲线配图 |
| 生产部署 | 待执行 | Nginx托管 + HTTPS + 兼容性全量实测（当前按约束仅输出本地部署文档） |
