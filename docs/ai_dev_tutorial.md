# AI协作开发教程（AI Dev Tutorial）

| 项目 | 内容 |
|---|---|
| 项目名称 | 光伏面板缺陷检测系统 |
| 文档版本 | V1.0.0 |
| 编写日期 | 2026-09-15 |
| 编制依据 | 《光伏面板缺陷检测系统项目任务书V1.0.0》任务10（AI协作教程） |
| 定位 | 以本项目实际开发过程为蓝本，讲解如何使用 AI 协作完成"数据-模型-应用"全链路开发 |

## 1 教程说明

本教程面向希望用 AI 协作完成全栈 AI 应用开发的学习者，以光伏面板缺陷检测系统的真实开发过程为主线，按任务书 10 个阶段逐一复盘：每个阶段做了什么、AI 产出什么、人工负责什么、如何验证、遇到哪些坑。

**AI 协作的基本约定**：

| 分工 | 负责内容 |
|---|---|
| AI 承担 | 代码编写、文档编写、方案设计、测试用例、排错分析 |
| 人工承担 | 数据集下载、图像标注、决策点拍板、关键验证、最终确认 |

**人机边界**：AI 产出的一切都要经过验证（pytest、构建、E2E、人工检查），不是"AI 说什么就是什么"。任务书要求的指标（mAP@0.5 ≥ 75%、缺陷召回率 ≥ 80%、单图推理 ≤ 200ms）是硬约束，AI 只能围绕它工作，不能改动。

## 2 AI协作工作流总览

本项目的开发遵循"**规格先行、任务分解、验证驱动**"循环：

```text
任务书 → 阶段规格（spec/任务分解/检查清单）→ 用户确认 → 分阶段开发 → 每阶段验证 → 文档归档
```

核心机制：

1. **spec 先行**：每个阶段先产出规格文档（章节大纲、决策点、验收标准），用户确认后才写代码。避免 AI 自由发挥引入任务书外功能。
2. **决策点机制**：任务书未定死参数（如上传上限、登录态方案）列为 D1、D2…，给建议默认值，用户确认或修改。本项目累计 38 个决策点（D1–D38）。
3. **验证驱动**：每阶段交付都有可执行验证——后端 pytest 冒烟、前端 `npm run build` 零报错、E2E 冒烟、接口 curl 实测。
4. **文档随阶段归档**：每个阶段的规格、报告、手册即时写入 docs/，答辩材料是最后阶段的自然产物。

## 3 阶段0 需求分析与系统设计

**任务书要求**：需求分析、架构设计、数据库设计、目录结构。

**AI 产出**：docs/prd.md（产品需求）、architecture.md（Mermaid 架构图）、db_design.md（表结构与 DDL）、project_structure.md（目录规划）、spec.md（技术方案与决策点）、tasks.md（任务分解）、checklist.md（检查清单）。

**提示词要点**（四要素缺一不可）：

```text
角色：产品经理/系统架构师
上下文：任务书原文 + 技术栈约束（Python 3.12、YOLOv8、FastAPI、React、sqlite3）
任务：产出 PRD：业务背景、目标、6大功能模块（FR-1~FR-6）、非功能指标
约束：只覆盖任务书范围，不新增功能；待确认参数列为决策点
```

**关键做法**：

- 需求逐条编号（FR-1.1、FR-1.2…），与任务书 2.2 一一对应，后续测试报告可直接引用。
- 六类检测定义与运维建议在需求阶段就固化（清洁/积灰/鸟粪/电损伤/物理损伤/积雪），后续所有文档复用同一张表。
- 决策点 D1–D10 在阶段0 一次性列出并确认：标注策略、上传上限 10MB、导出 CSV、JWT Bearer、存储加密、测试硬件、置信度阈值 0.25、邮箱选填、免责声明位置、部署形态。

**人工步骤**：审阅并确认 D1–D10（默认值直接采纳）。

## 4 阶段1 数据预处理与数据集构建

**任务书要求**：数据集构建、标注转换、划分、增强。

**人工步骤（AI 无法替代）**：

1. 下载 Kaggle "Solar Panel Images" 数据集（按六类文件夹组织，约数千张，注册后免费下载）。
2. LabelImg 人工标注目标框——该数据集**无边界框标注**，这是本项目最大的体力活，也是 AI 无法代劳的部分。

**AI 产出**（dataset_spec.md + 5 个脚本）：

| 脚本 | 功能 | 关键参数 |
|---|---|---|
| pv_classes.py | 六类映射表共享常量 | Clean/Dusty/Bird-drop/Electrical-damage/Physical-Damage/Snow-Covered |
| organize_dataset.py | 数据集目录组织 | — |
| convert_labels.py | LabelImg XML → YOLO txt | 含 --preview 抽样可视化抽查 |
| split_dataset.py | 8:1:1 分层抽样 | 生成 data.yaml 与 class_weights.json |
| augment.py | 数据增强 | 翻转/±15°旋转/亮度/Mosaic + 加权采样 |

**决策点**：D11 data.yaml 类别名用英文（中文由应用层映射，避免训练日志乱码）；D12 未标注图像排除而非当负样本；D13 增强样本并入 train；D14 旋转 ±15°（避免大角度外接框膨胀）；D15 提供标注可视化抽查。

**验证**：人工抽查 --preview 输出框叠加图，核对标注质量。

## 5 阶段2 深度学习模型开发与训练

**任务书要求**：模型训练、评估、导出。

**AI 产出**：train.py、eval.py、export.py、model_eval_report.md（评估报告模板）。

**训练参数**（task 指定 + D16–D22 确认）：

| 参数 | 值 | 说明 |
|---|---|---|
| 模型 | yolov8s（COCO 预训练迁移） | 精度/速度均衡，CPU 延迟超标可降级 yolov8n |
| 优化器 | AdamW，lr0=0.001 | 小数据集收敛快；CLI 可切 SGD |
| 学习率策略 | 余弦退火 | 配合早停（监控验证集 mAP） |
| 类别不均衡 | 加权过采样 | 重复因子 ≤3，可关闭 |
| 数据增强 | 在线 Mosaic/HSV/翻转 | 关闭在线旋转避免与离线增强重复 |
| 评估口径 | conf=0.25 + IoU=0.5 工程口径 | 与部署展示阈值一致，并列官方口径 |

**踩坑记录（重要）**：

1. **torch-pruning 1.6.0 移除了 check_dependency() API**：旧教程写法直接报错，新版本 `group.prune()` 自动同步耦合层，需按新 API 改写。
2. **C2f 模块无法直接剪枝**：YOLOv8 的 C2f 是动态 split + 残差相加结构，剪内部层会导致依赖对齐错乱、结构破坏。解决方案是"**安全集合**"策略——只剪下采样 Conv、SPPF 进出、C2f 出口 cv2，**绝不剪 C2f 内部与 Detect 头**。
3. **INT8 动态量化对 YOLOv8 CNN 收益有限**：实测体积压缩靠剪枝为主，量化为可选且需自动核对精度（--int8 后跑 mAP 对比，掉点即回退 FP32）。

**验证**：eval.py 输出 mAP@0.5 双口径与各类别 AP/召回率；export.py 输出 ONNX（FP32/opset12/simplify/batch=1）与基准延迟。

## 6 阶段3 模型部署与推理服务接口

**任务书要求**：模型部署、推理服务接口。

本项目中阶段3 的推理服务随阶段4 后端一并交付（backend/app/services/inference.py），关键设计：

- **双引擎自动探测**（D25）：扫描 weights 目录，有 `*.onnx` 优先加载 onnxruntime 引擎（200ms 指标主力），否则回退 ultralytics pt 引擎；两者皆无返回 50301"模型服务未就绪"。
- 权重文件名即 model_version，写入每条检测记录，便于版本追溯。
- 部署位固定为 backend/app/ml/weights/（best.onnx / best.pt），由算法阶段产物拷贝。

## 7 阶段4 后端API服务开发

**任务书要求**：RESTful API、JWT 鉴权、历史记录、图像访问。

**AI 产出**：FastAPI 分层代码（main / api / core / db / repositories / schemas / services）+ 18 个 pytest 冒烟用例 + api_doc.md。

**分层结构**：

```text
app/
├── main.py            # 入口：CORS、路由、统一响应包装、lifespan 建库+加载模型
├── api/               # 路由层：auth/user/detect/record/deps
├── core/              # config（环境变量）/errors（错误码）/pv_classes/security
├── db/                # SQLite 连接 + 建库（幂等）
├── repositories/      # DAO 层（原生 sqlite3，不引入 ORM，D30）
├── schemas/           # Pydantic 请求/响应模型
├── services/          # upload_check/preprocess/inference/render/advice
└── ml/weights/        # 模型权重部署位
```

**关键设计**：

- 统一响应 `{code: 0, message: "success", data}`；12 个错误码（40001/40002/40003/40101/40102/40301/40401/40901/40902/50301/50000），健康检查与文件流除外。
- 密码 PBKDF2 加盐哈希（SHA-256、600000 迭代、随机盐，D26）——passlib/bcrypt 有版本兼容坑，标准库零依赖最稳。
- JWT：SECRET_KEY 走环境变量（缺省开发密钥+告警），有效期 24h（D27）。
- 图片链路全程内存处理（BytesIO），仅原图/结果图按日期落盘 storage/（D29）。

**踩坑记录**：

1. **SQLite 跨线程报错**：async 路由下连接跨线程使用崩溃，需 `check_same_thread=False`。
2. **路由注册顺序**：`/api/record/export` 必须注册在 `/api/record/{record_id}` 之前，否则 export 被解析成记录 ID。
3. **上传校验双保险**：扩展名 + 文件魔数（内容签名）双重校验，防止伪造扩展名绕过前端。

**验证**：`python -m pytest tests/ -v`，18/18 通过（覆盖鉴权、注册、检测全链路、上传校验分支、属主隔离、ONNX 引擎路径）。

## 8 阶段5 前端Web界面开发

**任务书要求**：Web 界面、上传、结果展示、历史、响应式。

**AI 产出**：React 18 + TypeScript（strict）+ Vite 5 + TailwindCSS 3 + Ant Design 5 + react-router-dom 6 + axios，20 个源码文件，frontend_web_spec.md（含 D31–D38）。

**关键实现**：

| 能力 | 实现 |
|---|---|
| 鉴权注入 | axios 拦截器统一加 `Authorization: Bearer`，40101 自动清 token 跳登录 |
| 上传校验 | 前端格式+大小与后端完全一致（jpg/jpeg/png/bmp、≤10MB），超限即时拦截不发请求 |
| 结果可视化 | 后端返回标注图 base64 直接渲染，展示目标列表与置信度 |
| 鉴权图片 | /api/files/* 用 blob + objectURL 加载（`<img src>` 无法带鉴权头） |
| 历史导出 | 分页列表 + 详情 + CSV 下载（blob） |
| 响应式 | Tailwind md(768px) 断点切换，移动端表格横向滚动 |
| 路由 | HashRouter（部署子路径刷新不 404） |

**决策点**：D31 antd 管交互组件、Tailwind 管布局；D32 Vite 5（Node 18+）；D33 不引入全局状态库（localStorage + hooks）；D35 token 存 localStorage 不入 cookie（减小 CSRF 面）；D38 个人信息仅展示用户名+退出（后端接口保留）。

**验证**：`npm run build`（tsc --noEmit 严格类型零报错）+ 8 个 E2E 冒烟。

## 9 阶段6 系统集成与联调

**任务书要求**：完整 WebApp 系统、部署文档。

**AI 产出**：docs/deploy_manual.md（本地部署运维手册）、README.md、docs/deploy_spec.md。

**联调要点**：

- 开发期跨域走 Vite 代理：`/api` → `http://127.0.0.1:8000`（changeOrigin），浏览器同源无跨域。
- 后端 CORS 兜底 `allow_origins=["*"]`、`allow_credentials=False`；鉴权走 Authorization 头与 Cookie 无关，收紧白名单不影响登录。
- 权重缺失时检测接口 50301、其余接口正常，便于先联调业务再补模型。

**验证**：全链路八步验收（注册→登录→上传→检测→历史→详情→导出→CSV 编码检查）。

## 10 阶段7 系统测试与优化

**任务书要求**：测试报告、性能优化。

**AI 产出**：docs/test_report.md、docs/test_spec.md、backend/tests/concurrency_smoke.py。

**实测结果**：

| 测试项 | 结果 |
|---|---|
| 后端冒烟 | 18/18 通过（10.38s），12 个错误码覆盖 10 个 |
| 前端 E2E | 8 用例通过 |
| 并发简单测试 | 20 线程×100 请求：列表接口 100% 成功（平均 42ms/最大 71ms）；检测接口稳定返回 503（模型未就绪，异常处理正常） |
| 推理速度 | 待真实模型部署后复测（export.py --benchmark） |

**诚实原则**：权重未部署、真实 mAP/召回率/耗时未验证等事实如实写入报告，不粉饰。测试报告给出问题清单（P1 权重缺失）与优化建议（剪枝、HTTPS、补测 40902 等）。

## 11 阶段8 文档编写与项目答辩

**任务书要求**：AI 协作教程、PPT、项目说明、RAG 语料库（本批交付物）。

AI 协作的优势在本阶段最明显：4 类 5 份文档（ai_dev_tutorial / report_ppt_outline / project_spec_doc / RAG 语料库 / RAG 提示词）基于既有 18 份文档二次提炼生成。**关键约束是"严格参考任务书原文，不篡改业务指标"**——做法是先把指标基线表写进规格（mAP≥75%、召回≥80%、≤200ms…），全文生成后逐项核对。

RAG 应用：语料库 + 系统提示词可直接搭一个"光伏检测项目问答助手"，答辩与后续维护中随时问答检索。

## 12 踩坑复盘与协作方法总结

### 12.1 实测问题清单

| 问题 | 根因 | 解决方案 |
|---|---|---|
| torch-pruning 1.6.0 报错 | check_dependency() API 移除 | 改用 group.prune() 自动同步耦合层 |
| C2f 剪枝结构破坏 | 动态 split + 残差相加依赖错位 | 安全集合策略：只剪下采样 Conv/SPPF 进出/C2f 出口 cv2，不剪 C2f 内部与 Detect 头 |
| ONNX 预处理崩溃 | preprocess.py 调用 letterbox 时传了已移除的 stride 参数 | 删除多余参数，按新签名调用 |
| SQLite 跨线程异常 | async 路由连接跨线程 | check_same_thread=False |
| /record/export 返回 404 | 被 /record/{id} 抢占 | 具体路径注册在参数化路径之前 |
| PowerShell 禁止运行脚本 | 执行策略限制 | 用 npm.cmd / python.exe 直调，或 Set-ExecutionPolicy -Scope Process Bypass |
| Kaggle 数据无标注 | 数据集只有类别文件夹 | LabelImg 人工标注 + 转换脚本 |
| INT8 量化收益小 | YOLOv8 CNN 结构特性 | 体积压缩以剪枝为主，量化可选并自动精度核对 |

### 12.2 AI 协作方法要点

1. **提示词四要素**：角色、上下文（任务书/既有文档）、任务（具体交付物）、约束（指标、目录、格式）。缺约束是最常见失控原因。
2. **规格先行**：任何阶段先出规格 + 决策点，人确认后再写代码，防止 AI 过度发挥。
3. **验证驱动**：每阶段定义可执行验收（pytest/构建/E2E/curl），AI 交付后跑验证，不通过就修。
4. **文档即资产**：文档随阶段产出，答辩材料不是最后补的，而是全程积累的提炼。
5. **人工守住三件事**：数据质量（标注）、决策拍板（决策点）、最终验证（指标复核）。AI 负责把想法变成可运行的实现与文档。
