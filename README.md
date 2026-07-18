# InsightOps

InsightOps 是一个面向企业经营分析场景的大模型应用项目。当前仓库已完成 M0 基础设施、截至
**M1.1D：Marketing Schema** 的数据库实现，以及 **M1.2A：Seed Dataset & Benchmark Foundation**。
当前 feature milestone 还提供 **M1.2B：Deterministic SQL Evaluation Harness v1**，以及
**M1.3：Text2SQL Demo MVP** 的端到端查询路径和 **M1.4：React Demo UI**。

## 当前能力

- Python 3.12 与 uv 项目管理
- FastAPI 应用工厂和 `GET /health` 存活检查
- Pydantic 环境配置
- SQLAlchemy 2.x 引擎和 Session 工厂
- SQLAlchemy 2.x 企业身份、SaaS、商城和营销 ORM（当前共 20 张表）
- Alembic `0001`—`0004` migration，可从空库升级和回滚验证
- 版本化、确定性的身份、SaaS、商城与营销 seed dataset（334 行，固定 SHA-256 digest）
- 48 个 Gold Question 绑定，其中 28 个具备隔离的 Gold SQL 与冻结结果
- dataset、schema、business definition、Gold catalog 和 oracle assets 的可校验版本链
- 可重复的 seed `load`、`verify`、`unload` 生命周期和真实 MySQL benchmark 回归
- MySQL 8.4 Docker Compose 开发环境
- MySQL AST 校验、独立 readonly identity、严格结果比较和确定性 JSON evaluation report
- `POST /v1/query` 与 CLI Text2SQL 演示入口
- oracle-free context builder、结构化 provider 合同、离线 fake provider 和单一 OpenAI adapter
- benchmark 单 case 评测、自由问题安全执行与基于实际结果的简短业务摘要
- React、TypeScript 与 Vite 构建的单页 Analytics Copilot，支持开发代理和 FastAPI production 托管
- pytest、Ruff、mypy 和 GitHub Actions

当前不包含产品使用和客服 Schema，也不包含登录权限、RAG、Agent、生产级 SQL sandbox、Memory、MCP、
Redis、Celery、多轮会话或复杂 Dashboard。Gold SQL 和 expected results 仅是 benchmark oracle，不是 provider
的检索或 prompt 输入。

## 环境要求

- [uv](https://docs.astral.sh/uv/) 0.11 或更高版本
- Node.js 22.12 或更高版本（CI 固定使用 22.12；前端依赖由 `package-lock.json` 锁定）
- Docker Engine
- Docker Compose v2
- `curl`（用于手工健康检查）

项目通过 uv 安装 Python 3.12，不依赖系统默认 Python。文档使用标准 `docker compose` 命令；如果本机仅安装了独立 Compose 命令，可将其等价替换为 `docker-compose`。

## 本地启动

1. 安装 Python 和依赖：

   ```bash
   uv python install 3.12
   uv sync --locked
   ```

2. 创建本地配置：

   ```bash
   cp .env.example .env
   ```

   `.env.example` 中只有隔离本地环境使用的示例值。不要把 `.env`、真实密码或密钥提交到 Git。

3. 检查配置并启动 MySQL：

   ```bash
   docker compose config
   docker compose up -d --wait mysql
   docker compose --profile tools run --rm mysql-readonly-bootstrap
   docker compose ps
   ```

4. 从空数据库执行迁移：

   ```bash
   uv run alembic upgrade head
   uv run alembic current
   ```

5. 可选：加载并验证 M1.2A 固定数据集：

   ```bash
   uv run python -m insightops.seed digest
   uv run python -m insightops.seed load
   uv run python -m insightops.seed verify
   ```

   M1.2A dataset/catalog `1.1.0` 绑定 schema revision `0004` 和 Business Definitions `1.0.1`。
   seed 命令只允许在 `local`、`test` 或 `ci` 环境运行，并要求数据库位于当前 `head`。seed 不会创建
   migration 或专用数据库表。演示与 evaluation 期间应保持 dataset 已加载；不再使用时可运行
   `uv run python -m insightops.seed unload`，它只删除 manifest 所有的固定行。

6. 可选：运行确定性 SQL evaluation。先保持固定 dataset 已加载，再提供包含 28 个 `execute_sql` 和
   6 个 `request_clarification` response 的 submission JSON：

   ```bash
   uv run python -m insightops.seed load
   uv run python -m insightops.evaluation \
     --suite evaluations/m1_2b/suite.json \
     --submission /path/to/submission.json \
     --output /tmp/m1-2b-report.json
   ```

   candidate SQL 只使用 `READONLY_DATABASE_*` 身份。Writer 身份仅用于 migration、seed lifecycle 和
   evaluation 前后 dataset verify。完成报告包含状态、failure taxonomy 和 digest；preflight ABORTED report
   不含 case score 或 evaluation digest。两者都不包含 Gold SQL、expected rows 或 oracle path。`--output` 使用
   原子写入，并拒绝覆盖 suite、submission、seed、benchmark 或 Business Definitions 资产。

7. 启动 API：

   ```bash
   uv run uvicorn insightops.main:app --host 127.0.0.1 --port 8000 --reload
   ```

8. 在另一个终端检查服务：

   ```bash
   curl --fail --silent --show-error http://127.0.0.1:8000/health
   ```

   预期响应：

   ```json
   {"status":"ok"}
   ```

`/health` 只表示 API 进程存活，不检查数据库。数据库就绪由 Compose healthcheck 和 Alembic 命令分别验证。

## React Demo UI

开发模式使用两个进程。先按“本地启动”完成 MySQL、readonly identity、migration、seed 与 FastAPI 启动，
然后在另一个终端运行：

```bash
cd frontend
npm ci
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。Vite 将相对路径 `/v1` 和 `/health` 代理到本机 FastAPI；前端源码不保存
后端地址、provider 配置或凭证。

production build：

```bash
cd frontend
npm ci
npm run build
cd ..
uv run uvicorn insightops.main:app --host 127.0.0.1 --port 8000
```

构建产物位于被 Git 忽略的 `frontend/dist/`。FastAPI 启动后访问 `http://127.0.0.1:8000/` 即可使用同一页面，
`/assets/*` 由 FastAPI 托管；如果尚未 build，根页面返回稳定提示，但 `/health` 和 `/v1/query` 保持可用。

默认 `QUERY_PROVIDER=fake`，四个页面示例均可完全离线演示，不需要 OpenAI API key：

1. `GQ-SAA-002`：2025 年第二季度每个月的 SaaS Revenue 是多少？
2. `GQ-COM-001`：2025 年 6 月的 GMV、订单数和 AOV 是多少？
3. `GQ-MKT-006`：Marketing ROAS 应该使用哪一种收入定义？
4. 无 case ID：列出一个企业名称

真实 OpenAI provider 是可选的手工 smoke 路径，不纳入 CI；没有真实 key 时仍可完成全部 UI 演示。演示结束后
可运行 `uv run python -m insightops.seed unload` 卸载固定 seed 数据。

## 五分钟 Text2SQL 演示

以下步骤可从 clean checkout 直接执行。默认 `QUERY_PROVIDER=fake`，不需要 `OPENAI_API_KEY`，整个演示不访问
外部网络。

1. 创建本地配置并安装锁定依赖：

   ```bash
   cp .env.example .env
   uv sync --locked
   ```

2. 启动 MySQL：

   ```bash
   docker compose up -d --wait mysql
   ```

3. 创建并验证独立 readonly identity：

   ```bash
   docker compose --profile tools run --rm mysql-readonly-bootstrap
   ```

4. 升级到冻结 Schema head：

   ```bash
   uv run alembic upgrade head
   uv run alembic current
   ```

5. 加载并验证固定 dataset；后续演示期间不要执行 `seed unload`：

   ```bash
   uv run python -m insightops.seed load
   uv run python -m insightops.seed verify
   ```

6. 启动 FastAPI：

   ```bash
   uv run uvicorn insightops.main:app --host 127.0.0.1 --port 8000
   ```

7. 在另一个终端运行 fake provider API executable 与 clarification 示例：

   ```bash
   curl --fail --silent --show-error \
     -H 'Content-Type: application/json' \
     -d '{"question":"2025 年 6 月商城的 GMV、Order Count 和 AOV 分别是多少？","case_id":"GQ-COM-001"}' \
     http://127.0.0.1:8000/v1/query

   curl --fail --silent --show-error \
     -H 'Content-Type: application/json' \
     -d '{"question":"2025 年 6 月哪个活动的 ROAS 相比 4—5 月明显下降？","case_id":"GQ-MKT-006"}' \
     http://127.0.0.1:8000/v1/query
   ```

8. 在任一已加载 `.env` 的终端运行 CLI executable 与 clarification 示例：

   ```bash
   uv run python -m insightops.query \
     --question "2025 年第二季度每个月的 SaaS Revenue 是多少？" \
     --case-id GQ-SAA-002 \
     --provider fake

   uv run python -m insightops.query \
     --question "2025 年 6 月哪个活动的 ROAS 相比 4—5 月明显下降？" \
     --case-id GQ-MKT-006 \
     --provider fake
   ```

自由问题也经过相同物理表白名单、AST 与 readonly execution 边界，并明确不做 benchmark 评分：

```bash
curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  -d '{"question":"列出一个企业名称"}' \
  http://127.0.0.1:8000/v1/query
```

三个 benchmark demo questions：

1. `GQ-SAA-002`：2025 年第二季度每个月的 SaaS Revenue 是多少？
2. `GQ-COM-001`：2025 年 6 月的 GMV、订单数和 AOV 是多少？
3. `GQ-MKT-006`：Marketing ROAS 应该使用哪一种收入定义？

有 `case_id` 时，候选必须通过 M1.2B 的 action、AST、readonly execution 和 exact comparison；失败状态不会
被改写成成功。无 `case_id` 时仍执行相同 AST 安全分析与 readonly 边界，但返回
`evaluation_status=not_benchmark_scored`，不会伪造 Gold PASS。

真实 provider 仅用于手工 smoke。将本地 `.env` 设置为 `QUERY_PROVIDER=openai`、提供
`OPENAI_API_KEY`，并可用 `OPENAI_MODEL` 在允许值 `gpt-5.6-sol`（默认）或官方 alias `gpt-5.6` 中选择，再把
CLI 的 `--provider` 改为 `openai`。adapter 使用固定运行时依赖 `openai==2.46.0`、Responses API、Pydantic
Structured Outputs 与显式 low reasoning effort；密钥、原始 provider 异常和 usage 明细不会进入查询响应。
真实 provider 调用不是 CI 或本轮自动 smoke 的一部分，因此本文不声称它已在线验证。

## 开发检查

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict src tests scripts alembic
uv run pytest

cd frontend
npm ci
npm run lint
npm run typecheck
npm run test -- --run
npm run build
```

验证迁移可回滚和重新执行：

```bash
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
```

## 持续集成与远程验证

GitHub Actions 在推送到 `main` 或创建、更新 Pull Request 时运行。CI 使用 MySQL 8.4
service。Python job 依次验证锁定依赖安装、Ruff 格式和 lint、mypy、Alembic 升级与回滚、pytest，
最后启动 API 并请求 `GET /health` 进行 smoke test。独立 frontend job 使用正式 Node setup、`npm ci`、ESLint、
TypeScript、Vitest 和 Vite production build；两类自动测试都不连接真实 OpenAI API，前端 job 也不连接 MySQL。

推送后应在仓库的 **Actions** 页面确认 `CI` workflow 成功结束。远程检查与本地
“开发检查”使用相同的锁文件和命令；如果远程失败，应先查看失败步骤和日志，不应通过
降低 lint、类型检查、测试或 migration 要求绕过问题。

## 停止与清理

停止容器但保留 MySQL 数据：

```bash
docker compose down
```

删除容器和本项目 MySQL volume：

```bash
docker compose down -v
```

`-v` 会永久删除该开发环境中的数据库数据，只应在确认不需要保留数据时使用。

## 常见问题

- `3306` 被占用：修改 `.env` 中的 `DATABASE_PORT`，应用和 Compose 会使用同一宿主端口。
- `8000` 被占用：启动 Uvicorn 时通过 `--port` 选择其他端口。
- MySQL 尚未就绪：运行 `docker compose ps` 和 `docker compose logs mysql` 查看健康状态。
- 找不到 `docker compose`：安装 Compose v2，或在已安装独立版本的环境使用 `docker-compose`。
- uv 缓存目录不可写：为当前命令设置一个可写的 `UV_CACHE_DIR`，不要把缓存提交到仓库。

## 架构与后续开发

当前边界和设计理由见 [`docs/architecture.md`](docs/architecture.md)，商城 Schema 实施记录见
[`docs/plans/m1-1c-commerce-schema.md`](docs/plans/m1-1c-commerce-schema.md)，M1.2A 数据与评测基础见
[`docs/plans/m1-2a-seed-benchmark-foundation.md`](docs/plans/m1-2a-seed-benchmark-foundation.md)。后续工作继续按
明确里程碑规划；M1.3 的实现边界见
[`docs/plans/m1-3-text2sql-demo.md`](docs/plans/m1-3-text2sql-demo.md)，M1.4 的前端边界见
[`docs/plans/m1-4-react-demo-ui.md`](docs/plans/m1-4-react-demo-ui.md)，不提前实现 Agent、RAG、登录或多轮会话。
