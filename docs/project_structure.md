# 项目目录结构

| 项目 | 内容 |
|---|---|
| 项目名称 | 光伏面板缺陷检测系统 |
| 文档版本 | V1.0.0 |
| 编写日期 | 2026-09-14 |

项目根目录下按职责划分为四大部分：algorithm（算法）、backend（后端API）、frontend（前端web）、docs（文档）。当前阶段仅创建docs目录，其余目录在方案确认后随开发建立。

```text
pv-defect-detection/                  # 项目根目录
│
├── algorithm/                        # 算法目录：数据集构建、训练、评估、模型导出
│   ├── data/
│   │   └── raw/                      # Kaggle "Solar Panel Images" 原始数据集（按6类文件夹组织）
│   ├── datasets/                     # YOLO格式数据集
│   │   ├── images/
│   │   │   ├── train/                # 训练集图像（8）
│   │   │   ├── val/                  # 验证集图像（1）
│   │   │   └── test/                 # 测试集图像（1）
│   │   ├── labels/
│   │   │   ├── train/                # 训练集YOLO标注
│   │   │   ├── val/                  # 验证集YOLO标注
│   │   │   └── test/                 # 测试集YOLO标注
│   │   ├── data.yaml                 # 类别定义与数据集路径配置
│   │   └── class_weights.json        # 类别加权采样清单（阶段1产出，train.py消费）
│   ├── scripts/                      # 数据处理脚本（阶段1交付）
│   │   ├── pv_classes.py             # 六类映射表共享常量
│   │   ├── organize_dataset.py       # 数据集目录组织
│   │   ├── convert_labels.py         # 标注格式转换（LabelImg → YOLO）
│   │   ├── split_dataset.py          # 数据集划分（8:1:1）与加权采样清单
│   │   └── augment.py                # 数据增强（随机翻转/旋转/亮度扰动/Mosaic）
│   ├── train.py                      # YOLOv8迁移学习训练：早停/余弦退火/AdamW/加权采样/续训（阶段2交付）
│   ├── eval.py                       # 评估：双口径mAP@0.5、各类别AP与召回率、PR曲线、阈值判定（阶段2交付）
│   ├── export.py                     # ONNX导出、INT8量化、结构化剪枝、精度核对、延迟基准（阶段2交付，阶段3前置）
│   ├── models/                       # 导出产物：best.onnx、best_int8.onnx、export_report.md、manifest.json（部署时拷至backend/app/ml/weights/）
│   ├── runs/                         # 运行时产物（不入版本库）：detect/train*训练输出、eval/<时间戳>评估输出
│   └── requirements.txt              # 算法环境依赖（ultralytics、onnx、onnxruntime等）
│
├── backend/                          # 后端API目录（FastAPI，阶段4已交付）
│   ├── app/
│   │   ├── main.py                   # 应用入口：CORS、路由注册、全局异常、统一响应包装、lifespan（建库+加载模型）
│   │   ├── api/                      # 路由层
│   │   │   ├── auth.py               # 注册、登录（JWT签发）
│   │   │   ├── user.py               # 个人信息查看/修改、修改密码
│   │   │   ├── detect.py             # 图像上传校验与检测接口（POST /api/detect/image）
│   │   │   ├── record.py             # 历史记录列表/详情/导出、图像访问（属主校验）
│   │   │   └── deps.py               # 共享依赖（JWT鉴权 get_current_user）
│   │   ├── core/
│   │   │   ├── config.py             # 配置（上传上限、阈值、路径、JWT密钥，环境变量覆盖）
│   │   │   ├── errors.py             # 业务错误码与统一业务异常（BizError）
│   │   │   ├── pv_classes.py         # 六类映射表（class_id/中文名/框色，与algorithm侧一致）
│   │   │   └── security.py           # pbkdf2密码加盐哈希、JWT签发与校验
│   │   ├── db/
│   │   │   ├── database.py           # SQLite连接依赖（每请求独立连接，PRAGMA foreign_keys=ON）
│   │   │   └── init_db.py            # 建库建表初始化（user、detect_record，幂等）
│   │   ├── repositories/             # 数据访问层DAO（D30：原生sqlite3，不引入ORM）
│   │   │   ├── user_repo.py          # user表DAO
│   │   │   └── record_repo.py        # detect_record表DAO（属主隔离在查询层生效）
│   │   ├── schemas/                  # Pydantic请求/响应模型（auth、user、detect、record）
│   │   ├── services/
│   │   │   ├── upload_check.py       # 上传校验（扩展名+魔数双重，内存读取）
│   │   │   ├── preprocess.py         # 图像预处理（letterbox 640/归一化/格式转换）
│   │   │   ├── inference.py          # 推理引擎：ONNX优先（onnxruntime）/ pt回退（ultralytics）
│   │   │   ├── render.py             # 标注结果图渲染（OpenCV绘制检测框与标签）
│   │   │   └── advice.py             # 运维建议匹配（六类模板+置信度三档分级）
│   │   └── ml/
│   │       └── weights/              # 部署的模型权重（best.onnx优先/best.pt回退，由algorithm产出拷贝）
│   ├── storage/
│   │   ├── uploads/                  # 上传原图（YYYYMMDD/子目录）
│   │   └── results/                  # 标注结果图（YYYYMMDD/子目录）
│   ├── tests/                        # pytest冒烟测试（18用例，合成权重全链路）
│   └── requirements.txt              # 后端依赖（fastapi、uvicorn、onnxruntime、opencv-python等）
│
├── frontend/                         # 前端web目录（React，阶段5已交付）
│   ├── public/                       # 静态资源
│   ├── src/
│   │   ├── api/                      # axios实例与接口封装（client拦截器/auth/detect/record）
│   │   ├── types/                    # 与后端schema对齐的TS类型（auth/detect/record/common）
│   │   ├── components/
│   │   │   ├── ImageUploader/        # 上传组件（拖拽/点选/预览/格式大小校验）
│   │   │   ├── DetectionViewer/      # 检测结果渲染（标注图/检测框/置信度/运维建议）
│   │   │   ├── ImageCompare/         # 原图/结果图对比（blob鉴权加载）
│   │   │   ├── ProtectedRoute.tsx    # 鉴权路由守卫
│   │   │   └── AppLayout.tsx         # 顶栏（品牌/导航/用户名/退出）+ 内容区 + 页脚
│   │   ├── pages/
│   │   │   ├── Login/                # 登录页
│   │   │   ├── Register/             # 注册页
│   │   │   ├── Detect/               # 检测页（上传 + 结果展示）
│   │   │   └── History/              # 历史记录（列表/详情/对比/导出）
│   │   ├── hooks/                    # useAuth、useAuthImage、useObjectUrl
│   │   ├── constants/                # 校验规则常量（与后端一致）
│   │   ├── utils/                    # storage（token存取）、download（blob导出）
│   │   ├── App.tsx                   # 路由表
│   │   └── main.tsx                  # 入口（antd中文locale + ConfigProvider）
│   ├── index.html
│   ├── package.json                  # 依赖与脚本（dev/build/lint）
│   ├── vite.config.ts                # Vite构建配置（/api代理、分包、es2020目标）
│   ├── tsconfig.json                 # TypeScript严格模式
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   └── eslint.config.js              # 禁any、react-hooks规则
│
├── docs/                             # 文档目录
│   ├── prd.md                        # PRD需求文档
│   ├── architecture.md               # 系统架构设计（Mermaid）
│   ├── db_design.md                  # 数据库设计
│   ├── project_structure.md          # 项目目录结构（本文档）
│   ├── spec.md                       # 技术方案规格说明书
│   ├── tasks.md                      # 任务分解
│   ├── checklist.md                  # 方案检查清单
│   ├── dataset_readme.md             # 数据准备流程：下载→标注→转换→划分→增强（阶段1）
│   ├── dataset_spec.md               # 数据集处理脚本规格说明书（阶段1，D11–D15）
│   ├── model_train_spec.md           # 模型训练与导出脚本规格说明书（阶段2，D16–D23）
│   ├── model_eval_report.md          # 模型评估报告模板（阶段2，eval.py自动填充）
│   ├── backend_api_spec.md           # 后端API服务规格说明书（阶段4，D24–D30）
│   ├── frontend_web_spec.md          # 前端Web界面规格说明书（阶段5，D31–D38）
│   ├── api_doc.md                    # API接口文档（阶段4，完整OpenAPI接口文档）
│   └── （后续产出）ui_ux.md          # UI/UX设计文档
│       test_report.md                # 测试报告
│       deploy.md                     # 部署运维手册
│       tutorial.md                   # AI协作教程
│
└── README.md                         # 项目说明（快速开始、目录导航）
```

## 目录职责说明

| 目录 | 角色 | 核心内容 |
|---|---|---|
| algorithm/ | 算法工程 | 原始数据集管理、YOLO格式数据集构建、数据增强、模型训练与评估、量化剪枝与ONNX导出；产出的最优权重部署至 backend/app/ml/weights |
| backend/ | 后端API服务 | FastAPI应用：认证与用户管理、上传校验、预处理与推理编排、结果持久化、历史记录与导出；SQLite数据库与图像文件存储随此目录部署 |
| frontend/ | 前端Web应用 | React + TailwindCSS + Ant Design：上传、结果可视化、历史记录、个人信息等页面；构建产物部署时由后端或反向代理托管 |
| docs/ | 项目文档 | PRD、架构、数据库设计、目录结构、技术规格、任务分解、检查清单，以及后续各阶段文档 |

算法目录与后端目录的关系：algorithm/ 独立运行于训练环境，负责产出模型；backend/ 在服务端加载训练成果提供在线推理，两者通过 model_version 字段与 weights 文件衔接（见 db_design.md）。
