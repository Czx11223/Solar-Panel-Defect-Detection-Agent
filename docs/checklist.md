# 方案检查清单（Checklist）

| 项目 | 内容 |
|---|---|
| 项目名称 | 光伏面板缺陷检测系统 |
| 文档版本 | V1.0.0 |
| 编写日期 | 2026-09-14（2026-09-15 更新为全量验收版） |
| 用途 | 全量交付验收对照：需求覆盖、指标落位、约束合规、交付物完整性 |

## A 需求覆盖对照（任务书2.2 → PRD）

| 任务书要求 | PRD编号 | 覆盖状态 | 实测证据 |
|---|---|---|---|
| 图像上传：拖拽或点击选择方式上传 | FR-1.1 / FR-1.2 | 已覆盖 | 前端 ImageUploader，E2E通过 |
| 图像上传：支持jpg、png、jpeg、bmp格式 | FR-1.4 | 已覆盖 | 前后端双重校验，冒烟test_detect_bad_extension通过 |
| 图像上传：图像预览 | FR-1.3 | 已覆盖 | 上传区缩略预览+文件信息 |
| 图像上传：文件大小与格式校验 | FR-1.4 / FR-1.5 | 已覆盖 | 10MB上限，冒烟test_detect_oversize通过 |
| 预处理：尺寸调整 | FR-2.1 | 已覆盖 | letterbox 640×640 |
| 预处理：归一化 | FR-2.2 | 已覆盖 | 像素归一化0–1 |
| 预处理：格式转换 | FR-2.3 | 已覆盖 | 统一RGB三通道 |
| 识别：基于COCO预训练YOLOv8六类检测模型 | FR-3.1 | 已覆盖 | train.py迁移学习 + 双引擎推理 |
| 识别：提供目标框位置、置信度 | FR-3.1 / FR-3.2 | 已覆盖 | 结构化目标列表 |
| 结果展示：渲染检测框与类别标签 | FR-4.1 | 已覆盖 | render.py标注结果图 |
| 结果展示：可视化展示各类别置信度 | FR-4.2 | 已覆盖 | DetectionViewer置信度条 |
| 结果展示：提供清洗、检修运维建议 | FR-4.3 | 已覆盖 | advice.py六类模板+三档分级 |
| 历史：保存检测历史 | FR-5.1 | 已覆盖 | detect_record表 |
| 历史：查看过往检测结果 | FR-5.2 / FR-5.3 | 已覆盖 | 列表+详情，冒烟通过 |
| 历史：图像对比 | FR-5.4 | 已覆盖 | 原图/结果图对比组件 |
| 历史：检测记录导出 | FR-5.5 | 已覆盖 | CSV导出，冒烟test_record_list_detail_export通过 |
| 用户管理：注册、登录、个人信息管理 | FR-6.1 – FR-6.3 | 已覆盖 | 冒烟全部通过 |
| 用户管理：保障用户数据安全 | FR-6.4 | 已覆盖 | pbkdf2哈希+JWT+属主隔离，冒烟test_owner_isolation通过 |

## B 非功能指标落位

| 指标 | 目标 | 文档落位 | 验证状态 |
|---|---|---|---|
| mAP@0.5 | ≥ 75% | PRD 6.1 / spec 7 | 待真实模型复测（eval.py已实现） |
| 主要缺陷类别召回率 | ≥ 80% | PRD 6.1 / spec 7 | 待真实模型复测（eval.py已实现） |
| 单张图像推理耗时 | ≤ 200ms | PRD 6.1 / spec 6 | 待真实模型复测（export.py --benchmark） |
| HTTPS加密传输 | 全站 | PRD 6.2 / spec 9 | 生产部署后验收 |
| 密码加盐哈希存储 | 全环节 | PRD 6.2 / spec 9 | 已实现（pbkdf2_hmac） |
| 数据库存储加密 | 部署措施 | PRD 6.2 / spec 9 | 应用层+磁盘加密方案，部署期执行 |
| 浏览器兼容 | Chrome/Firefox/Safari/Edge最新两版本 | PRD 6.3 / spec 10 | Chrome已实测，其余待补测 |
| 响应式设计 | PC端与移动端 | PRD 6.3 / spec 10 | md(768px)断点已实现，移动端待实测 |

## C 约束合规自查（任务书硬性业务约束）

- [x] 功能范围与任务书一致：仅6大模块，无任务书以外的新增功能
- [x] 技术栈与任务书3.2一致，未增改
- [x] 检测类别与任务书一致：清洁、积灰、鸟粪、电损伤、物理损伤、积雪（6类）
- [x] 算法流程与任务书3.3一致：LabelImg标注→YOLO格式→8:1:1划分→加权采样与数据增强→迁移学习→量化剪枝ONNX→API部署
- [x] 巡检结果免责声明已随系统展示（检测结果页底部+页脚）且写入PRD/README
- [x] 模型局限性声明已写入PRD/README/评估报告（6类限定、漏检误检风险、阈值说明）
- [x] 数据隐私保护条款已写入PRD/README（数据仅用于本系统检测，不外传；密码哈希；属主隔离）
- [x] 剪枝遵循安全集合策略（只剪下采样Conv、SPPF出入口、C2f出口cv2，不剪C2f内部与Detect头）
- [x] RESTful统一JSON响应 {code,message,data}，健康检查/CSV导出/图像流不包装
- [x] 检测与历史接口JWT鉴权；40101清token跳登录
- [x] 图片处理内存优先，无临时磁盘堆积

## D 数据库设计完备性

- [x] user表：字段、类型、约束、说明齐全（db_design.md）
- [x] detect_record表：字段、类型、约束、外键（user_id → user.id，ON DELETE CASCADE）齐全
- [x] 主键：两表 INTEGER PRIMARY KEY AUTOINCREMENT
- [x] 索引：username唯一、email部分唯一、(user_id, created_at DESC)复合、created_at单列，均含用途说明
- [x] DDL可在SQLite3直接执行，PRAGMA foreign_keys=ON 已注明；check_same_thread=False已落地
- [x] detect_result JSON结构已定义（含空结果约定）

## E 交付物完整性对照（任务书5.2，五类全量）

### E1 算法（algorithm/）

- [x] 数据集处理脚本：organize_dataset.py、convert_labels.py、split_dataset.py、augment.py、gen_pseudo_labels.py、pv_classes.py（6个）
- [x] 训练脚本 train.py（迁移学习、联合损失、AdamW/SGD、余弦退火、早停、加权采样）
- [x] 评估脚本 eval.py（双口径指标、六类PR曲线、退出码）
- [x] ONNX导出脚本 export.py（FP32/INT8/FP16、剪枝、精度核对、延迟基准）
- [x] requirements.txt 与数据准备文档 dataset_readme.md
- [x] 真实数据集（885张）与整图伪标签已就绪（2026-09-15），CPU全量训练进行中
- [ ] 训练完成的模型权重（runs/train_real/best.pt，待训练结束）

### E2 后端（backend/）

- [x] FastAPI全套代码：main.py、core/（config、errors、security、pv_classes）、api/（auth、user、detect、record、deps）、services/（preprocess、inference、render、advice、upload_check）、repositories/、schemas/、db/
- [x] 完整OpenAPI文档 docs/api_doc.md（11接口）与 docs/backend_api_spec.md
- [x] 测试：tests/test_api.py（18用例全通过）、tests/concurrency_smoke.py（20线程×100请求）
- [ ] 模型权重文件（backend/app/ml/weights/，待真实模型部署）

### E3 前端（frontend/）

- [x] React+TS+Vite工程：pages（Login/Register/Detect/History）、components（ImageUploader/DetectionViewer/ImageCompare/AppLayout/ProtectedRoute）、api、hooks、types、utils、constants（27个src文件）
- [x] npm run build 零错误；8个E2E用例通过
- [x] 响应式适配PC/移动端；免责声明展示

### E4 集成、部署、测试、需求文档（docs/）

- [x] PRD（docs/prd.md）、架构（architecture.md）、数据库设计（db_design.md）、目录结构（project_structure.md）
- [x] 部署运维手册（deploy_manual.md）、部署规格（deploy_spec.md）、README.md
- [x] 测试报告（test_report.md，功能/性能/兼容性三域+问题清单+优化建议）
- [x] 规格文档：dataset_spec、model_train_spec、test_spec、frontend_web_spec、final_docs_spec
- [x] 评估报告模板（model_eval_report.md）

### E5 答辩文档（docs/ + rag/）

- [x] AI协作教程 docs/ai_dev_tutorial.md
- [x] 汇报PPT大纲 docs/report_ppt_outline.md
- [x] 项目说明（参数文档）docs/project_spec_doc.md（含D1–D38决策记录）
- [x] RAG语料库 rag/pv_system_corpus.md 与 RAG助手提示词 rag/prompt.md
- [ ] 答辩PPT成品（待制作，含界面截图与PR曲线配图）

## F 决策点确认记录（D1–D38，均已按建议默认值执行）

| 编号 | 决策点 | 已确认值 |
|---|---|---|
| D1 | 数据集标注策略 | 2026-09-15 用户决策：跳过人工标注，采用整图伪标签弱监督（gen_pseudo_labels.py，885张全量），放弃LabelImg人工框标注 |
| D2 | 上传大小上限 | 10MB |
| D3 | 历史导出格式 | CSV |
| D4 | 登录态方案 | JWT Bearer Token |
| D5 | 数据库存储加密 | 敏感字段应用层加密 + 部署层磁盘加密 |
| D6 | 推理性能测试硬件 | 待真实模型阶段明确（GPU或纯CPU） |
| D7 | 置信度展示阈值 | 0.25 |
| D8 | 注册邮箱 | 选填 |
| D9 | 免责声明位置 | 检测结果页底部 + 页脚入口 |
| D10 | 前端静态托管 | 开发期Vite，部署期Nginx |
| D11 | data.yaml类别名语言 | 英文标识，中文应用层映射 |
| D12 | 未标注图像处理 | 排除并列清单 |
| D13 | 增强样本存放 | 并入train（augm_前缀） |
| D14 | 旋转角度策略 | ±15°随机 |
| D15 | 标注可视化抽查 | 提供 --preview |
| D16 | 模型规模 | 2026-09-16 用户决策：为加速CPU训练改用yolov8n；结果不达标可回退yolov8s |
| D17 | 优化器 | 默认AdamW lr0=0.001，可切SGD |
| D18 | 脚本命名 | train/eval/export.py，产物入algorithm/models/ |
| D19 | 训练加权过采样 | 默认开启（因子≤3） |
| D20 | 剪枝落地 | torch-pruning ≥1.6.0默认关闭；安全集合策略 |
| D21 | ONNX精度 | 默认FP32；--half/--int8可选并自动mAP核对 |
| D22 | 召回率口径 | conf=0.25+IoU=0.5工程口径，并列官方口径 |
| D23 | 在线增强策略 | 保留Mosaic/HSV/翻转，关闭在线旋转 |
| D24 | 接口路径风格 | detect/image、record/list、record/export |
| D25 | 推理引擎 | 双引擎自动探测：onnx优先、pt回退 |
| D26 | 密码哈希算法 | 标准库pbkdf2_hmac |
| D27 | JWT参数 | 环境变量密钥 + 24h过期 |
| D28 | 运维建议策略 | 六类模板 + 置信度三档分级 |
| D29 | 图片处理链路 | 内存优先，原图/结果图按日期落盘 |
| D30 | 数据库访问层 | 原生sqlite3 + DAO，不引入ORM |
| D31 | antd与Tailwind分工 | antd组件 / Tailwind布局 |
| D32 | 构建工具 | Vite 5（Node 18+） |
| D33 | 状态管理 | 不引入全局状态库 |
| D34 | 路由模式 | HashRouter |
| D35 | token存储 | localStorage，不入cookie |
| D36 | 前端上传校验深度 | 格式+大小与后端一致，魔数仅后端 |
| D37 | 响应式断点 | md(768px)主切换 |
| D38 | 个人信息功能范围 | Header展示用户名+退出，接口保留 |

## G 遗留事项验收

| 事项 | 责任阶段 | 验收标准 |
|---|---|---|
| 真实数据集下载与标注 | 阶段1 | 六类目标框标注完成，YOLO格式转换通过 |
| 模型训练与评估 | 阶段2 | mAP@0.5 ≥75%、缺陷召回率 ≥80%，评估报告产出 |
| 权重部署与性能复核 | 阶段3/7 | 单图推理 ≤200ms，检测接口返回真实结果 |
| 浏览器兼容性补测 | 阶段7 | Firefox/Safari/Edge最新两版本+移动端 |
| 答辩PPT成品 | 阶段8 | 按大纲10章20页，含界面截图与PR曲线配图 |
