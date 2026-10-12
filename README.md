# MallMate 开发骨架

依据“电商客服售后 Agent 项目选题”创建的开发项目。当前已经建立版本化业务规则、广覆盖 Markdown 知识库、模拟交易数据和离线评估基线；外部模型默认关闭。

## 当前能做什么

- 前端聊天、演示账号切换、政策 FAQ、订单和物流查询。
- 售后申请预览、用户确认、幂等创建和创建后状态回查。
- LangGraph 工作流、FastAPI API、SQLAlchemy 数据模型。
- 10 类售后意图与 4 档紧急度的离线规则基线。
- 15 篇知识文档、BM25 检索基线、开发集/留出集评估入口。
- PostgreSQL、Redis、ChromaDB、MinIO 与 Prometheus 的 Compose 配置。

## 本机开发（所有项目数据位于 F 盘）

在 PowerShell 中进入本目录，首次安装执行：

```powershell
& .\scripts\setup.ps1
```

在两个 PowerShell 窗口分别运行：

```powershell
& .\scripts\start-backend.ps1
```

```powershell
& .\scripts\start-frontend.ps1
```

访问 <http://localhost:3000>；API 文档在 <http://localhost:18080/docs>。不使用 Docker 时，SQLite 备用数据文件位于 `backend/mallmate_dev_v2.db`，首次启动自动创建演示数据。旧版 `mallmate.db` 会保留，不会被新结构覆盖。

本机 Python 默认命令是 3.9，开发时请使用上面的 F 盘 Python 3.11 路径或项目虚拟环境。`py` 启动器当前指向失效的 Python 3.12 路径。
如果本机 Python 3.11 安装路径改变，可用 `& .\scripts\setup.ps1 -PythonExe '你的 Python 3.11 路径'` 指定。
如需修改本机数据库或 CORS 配置，将 `backend/.env.example` 复制为 `backend/.env` 后编辑。

## Docker Compose

本机 Docker Desktop 的 WSL 数据目录已配置为 `E:\Develop\DockerData\DockerDesktopWSL`，容器数据卷使用本项目 F 盘 `data/` 目录。启动 Docker Desktop 后，在本项目目录运行：

```powershell
docker compose up --build
```

PostgreSQL、Redis、ChromaDB、MinIO 与 Prometheus 的持久数据使用项目下 `data/` 目录。Docker 镜像和构建缓存的位置由 Docker Desktop 的 WSL 数据目录设置控制；如在其他机器运行，请先检查该目录是否位于非 C 盘。
本次搭建时 Docker Desktop 服务处于停止状态，当前终端无法启动该系统服务，因此容器尚未实启验证。本机前后端开发可使用上面的 SQLite 路径直接运行。

## 演示场景

- Alice：订单 `1001` 已签收、订单 `1002` 运输中；Bob：订单 `2001` 已签收。
- Alice 查询 Bob 的订单 `2001` 应返回不存在。
- Alice 对订单 `1001` 可以预览并确认创建模拟售后申请；订单 `1002` 会被演示规则拦截。
- FAQ 可问“退货上门取件要多久”。知识来源为 `knowledge/policies/` 中的演示文本。

## 文档

- [开发记录](docs/开发记录.md)：环境检查、实施步骤和验证结果。
- [后续开发清单](docs/后续开发清单.md)：当前骨架之后需要补齐的能力及建议顺序。
- [后端工程架构](docs/后端工程架构.md)：当前分层、职责边界和扩展方式。
- [后端改进方案](docs/后端改进方案.md)：配置、数据库、模型、RAG 和 Agent 的目标方案。
- [30 天开发计划](docs/30天开发计划.md)：每天的任务、产出、知识点和验收标准。
- [业务规则与评估数据说明](docs/业务规则与评估数据说明.md)：规则来源、模拟数据、评估口径和能力边界。
- [离线评估说明](evals/README.md)：数据划分、运行命令和指标。

## 离线评估

无需启动 Agent 或配置 API Key：

```powershell
& .\.venv\Scripts\python.exe .\evals\runner.py --split dev
```

留出集只在冻结版本后运行：

```powershell
& .\.venv\Scripts\python.exe .\evals\runner.py --split holdout
```

## 简单验证

后端启动后，在项目根目录执行：

```powershell
& .\.venv\Scripts\python.exe .\backend\scripts\smoke.py
```

该脚本检查政策来源、订单归属、售后资格、确认写入与幂等保护。脚本会创建一条演示售后申请；重复执行会复用同一个幂等键。

