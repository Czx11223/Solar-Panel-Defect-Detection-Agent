# 任务分解（Tasks）

| 项目 | 内容 |
|---|---|
| 项目名称 | 光伏面板缺陷检测系统 |
| 文档版本 | V1.0.0 |
| 编写日期 | 2026-09-14（2026-09-15 更新为全量交付状态） |
| 编制依据 | 《光伏面板缺陷检测系统项目任务书V1.0.0》第四章项目任务分解 |

## 任务书任务映射

| 任务书# | 任务内容 | 对应阶段 | 交付物 | 状态 |
|---|---|---|---|---|
| 1 | 需求分析与系统设计 | 阶段0 | 需求文档、架构设计图、数据库设计 | 完成 |
| 2 | 数据预处理与数据集构建 | 阶段1 | 标注转换代码、数据集、数据增强脚本 | 脚本完成，数据集人工步骤待执行 |
| 3 | 深度学习模型开发与训练 | 阶段2 | 训练代码、模型权重、评估报告 | 脚本完成，真实训练待执行 |
| 4 | 模型部署与推理服务接口 | 阶段3 | 模型部署代码、推理服务接口 | 代码完成，权重部署待执行 |
| 5 | APP需求分析与系统设计 | 阶段0 | 需求文档、UI/UX设计、架构设计、数据库设计 | 完成 |
| 6 | 后端API服务开发 | 阶段4 | FastAPI服务代码、API文档 | 完成 |
| 7 | 前端Web界面开发 | 阶段5 | React前端代码、组件库 | 完成 |
| 8 | 系统集成与联调 | 阶段6 | 完整WebApp系统、部署文档 | 本地完成，生产部署待执行 |
| 9 | 系统测试与优化 | 阶段7 | 测试报告、性能优化版本 | 功能/并发完成，性能复核待真实模型 |
| 10 | 文档编写与项目答辩 | 阶段8 | 项目文档、演示PPT、项目说明 | 文档完成，PPT成品待制作 |

## 阶段0 需求分析与系统设计（完成）

- [x] PRD需求文档（docs/prd.md）
- [x] 系统架构设计（docs/architecture.md，Mermaid）
- [x] 数据库设计（docs/db_design.md）
- [x] 项目目录结构（docs/project_structure.md）
- [x] 技术方案规格（docs/spec.md，决策点D1–D38）
- [x] 任务分解与检查清单（docs/tasks.md、docs/checklist.md）
- [x] 用户确认方案与决策点（D1–D10 按建议默认值执行；后续各阶段决策点随阶段确认，全部落地）

## 阶段1 数据预处理与数据集构建（脚本完成，数据集待人工就绪）

脚本设计规格见 [dataset_spec.md](dataset_spec.md)（决策点D11–D15），操作指引见 [dataset_readme.md](dataset_readme.md)。

- [x] 下载Kaggle "Solar Panel Images"数据集至 algorithm/data/raw/（885张，2026-09-15 完成）
- [x] 整图伪标签生成脚本 scripts/gen_pseudo_labels.py（2026-09-15 用户决策：跳过人工标注，采用弱监督方案；每类生成一个全图检测框，885张全量标注）
- [x] 目录组织脚本 organize_dataset.py 与共享类别映射 pv_classes.py
- [x] 标注转换脚本 convert_labels.py（LabelImg XML → YOLO格式，保留备用；含 --preview 标注抽查）
- [x] 数据集划分脚本 split_dataset.py：8:1:1分层抽样，生成 data.yaml（train 709 / val 88 / test 88）
- [x] 加权采样清单 class_weights.json（应对类别分布不均）
- [x] 数据增强脚本 augment.py：随机翻转、±15°旋转、亮度扰动、Mosaic拼接 + 类别加权采样（2026-09-15 实际生成200张，train共909张）
- [x] 数据准备流程文档 docs/dataset_readme.md（端到端冒烟通过）

## 阶段2 深度学习模型开发与训练（脚本完成，真实训练待执行）

脚本设计规格见 [model_train_spec.md](model_train_spec.md)（决策点D16–D23）。

- [x] 训练脚本 train.py：COCO预训练迁移学习（yolov8s）、联合损失、AdamW/SGD + 余弦退火、fitness早停、类别加权采样、断点续训（超参数中文注释，合成微数据集冒烟通过）
- [ ] 训练执行与调参，产出模型权重（algorithm/runs/）——待阶段1数据集就绪
- [x] 评估脚本 eval.py：双口径mAP@0.5（≥75%）与缺陷类别召回率（≥80%，conf=0.25工作点）、六类PR曲线、各类别AP、阈值判定与退出码（冒烟通过）
- [x] 评估报告模板 docs/model_eval_report.md（指标表格、PR曲线说明、性能目标阈值、模型局限性）
- [x] 模型导出脚本 export.py：ONNX导出（FP32默认）、INT8动态量化、结构化剪枝（安全集合策略，冒烟实测17层通过）、FP16可选、ONNX精度核对、延迟基准
- [ ] 未达标时迭代（数据增强策略、采样权重、模型规模）——待真实数据训练后执行

## 阶段3 模型部署与推理服务接口（代码完成，权重待部署）

- [x] 模型优化导出脚本 export.py（量化、剪枝、ONNX导出、精度核对、延迟基准）
- [x] 推理服务封装：backend/app/services/（preprocess.py、inference.py、render.py、upload_check.py，ONNX优先/pt回退双引擎）
- [ ] 推理耗时验证：单图 ≤200ms（export.py --benchmark，待真实模型训练后执行）
- [ ] 权重部署至 backend/app/ml/weights/，登记 model_version（待真实模型训练后执行）

## 阶段4 后端API服务开发（完成）

- [x] FastAPI骨架：main.py、config.py、异常与统一响应结构（lifespan建库+加载模型、响应统一{code,message,data}）
- [x] SQLite初始化：database.py、init_db.py（user、detect_record建表，外键开启）
- [x] 认证模块：注册/登录接口、pbkdf2密码哈希、JWT鉴权
- [x] 用户信息接口：查看/修改个人信息、修改密码
- [x] 检测接口：上传校验（格式/大小10MB）→ 预处理 → 推理 → 记录保存 → 结果返回
- [x] 历史记录接口：列表分页、详情、图像访问（属主校验）、CSV导出
- [x] 运维建议服务：六类模板 + 置信度三档分级
- [x] 后端测试：18个冒烟用例全部通过（注册→登录→鉴权→检测→列表→导出全链路）；并发冒烟20线程×100请求通过
- [x] API接口文档 docs/api_doc.md（完整OpenAPI接口文档，配合FastAPI /docs交互文档）

## 阶段5 前端Web界面开发（完成）

- [ ] UI/UX设计文档 docs/ui_ux.md——暂缓，页面按 [frontend_web_spec.md](frontend_web_spec.md) 直接实现，后续可补
- [x] React + Vite + TailwindCSS + Ant Design 工程骨架、路由、响应式布局（TypeScript严格模式，npm run build 零错误）
- [x] 登录/注册页（表单校验与后端一致、JWT token localStorage存储）
- [x] 检测页：ImageUploader（拖拽/点选/预览/校验）+ DetectionViewer（检测框/置信度/运维建议）
- [x] 历史记录页：列表、详情、原图与结果图对比、CSV导出（blob鉴权方案）
- [x] 个人信息：Header展示用户名+退出登录（D38，接口保留）
- [x] 免责声明展示（页脚+检测页使用说明，AI辅助判断仅供参考）
- [x] 前端8个E2E用例通过

## 阶段6 系统集成与联调（本地完成，规格见 docs/deploy_spec.md）

- [x] 前后端接口联调（错误场景：50301模型未就绪、40101登录过期、上传校验失败等，全链路本地跑通）
- [x] 项目目录梳理（algorithm/backend/frontend/docs 四部分职责确认）
- [x] 本地部署文档 docs/deploy_manual.md（依赖安装、启动命令、环境变量、全链路验收、排错）
- [x] 项目 README.md（项目简介、技术栈、快速启动、局限性声明：巡检结果使用声明/模型局限/隐私保护）
- [ ] 生产部署：uvicorn + 静态资源托管 + HTTPS（按约束仅输出本地部署文档，不实施）

## 阶段7 系统测试与优化（部分完成，规格见 docs/test_spec.md）

- [x] 功能测试：5大模块用例（用户管理/上传校验/检测推理/结果展示/历史导出，正常+异常场景；后端18冒烟实测通过，前端8 E2E通过）
- [x] 并发简单测试：backend/tests/concurrency_smoke.py（20线程×100请求实测，鉴权接口100%成功）
- [x] 测试报告 docs/test_report.md（功能/性能/兼容性三域、问题清单、优化建议、对照任务书验收清单）
- [ ] 性能复核：mAP@0.5、缺陷召回率、单图推理耗时（待真实模型权重部署后复测，问题P1）
- [ ] 兼容性测试：Chrome/Firefox/Safari/Edge最新两版本、PC与移动端响应式（清单已输出，除Chrome外待执行）
- [ ] 安全检查：HTTPS（生产部署后）、token过期边界、错误码40902/50000补测

## 阶段8 文档编写与项目答辩（部分完成，规格见 docs/final_docs_spec.md）

- [x] AI协作教程 docs/ai_dev_tutorial.md（阶段0–8复盘AI协作全流程+踩坑清单）
- [x] 项目汇报PPT大纲 docs/report_ppt_outline.md（10大章节、逐页要点级，预计20页）
- [x] 项目说明（参数文档）docs/project_spec_doc.md（模块/指标/技术参数/D1–D38决策记录）
- [x] RAG语料库 rag/pv_system_corpus.md 与 RAG助手提示词 rag/prompt.md
- [ ] 答辩PPT成品（按大纲制作，含界面截图与PR曲线等配图）

## 依赖关系

阶段0（确认）→ 阶段1 → 阶段2 → 阶段3 → 阶段4；阶段4 与 阶段5 可在接口契约（spec.md 第5章）冻结后并行；阶段4+5 → 阶段6 → 阶段7 → 阶段8。

## 当前遗留执行清单（按优先级）

1. **P0 真实数据与模型**：下载Kaggle数据集 → LabelImg标注 → 训练 → 评估达标 → 导出ONNX → 部署权重
2. **P1 性能复核**：mAP@0.5 / 召回率 / 推理耗时实测（当前检测接口因缺权重返回50301）
3. **P1 兼容性补测**：Firefox/Safari/Edge + 移动端响应式
4. **P2 答辩PPT成品**：按大纲制作
5. **P2 安全检查**：HTTPS、token过期边界、错误码40902/50000补测
