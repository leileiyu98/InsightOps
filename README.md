# InsightOps

InsightOps 是一个面向企业经营分析场景的大模型应用项目。当前仓库已完成 M0 基础设施、截至
**M1.1D：Marketing Schema** 的数据库实现，以及 **M1.2A：Seed Dataset & Benchmark Foundation**。

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
- pytest、Ruff、mypy 和 GitHub Actions

当前不包含产品使用和客服 Schema，也不包含业务 API、登录权限、大模型 API、Text2SQL、RAG、
Agent、SQL 安全引擎、Memory、MCP、Redis、Celery 或前端。Gold SQL 和 expected results 仅是 benchmark
oracle，不是未来 Agent 的检索或 prompt 输入。

## 环境要求

- [uv](https://docs.astral.sh/uv/) 0.11 或更高版本
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
   uv run python -m insightops.seed unload
   ```

   M1.2A dataset/catalog `1.1.0` 绑定 schema revision `0004` 和 Business Definitions `1.0.1`。
   seed 命令只允许在 `local`、`test` 或 `ci` 环境运行，并要求数据库位于当前 `head`。seed 不会创建
   migration 或专用数据库表，`unload` 只删除 manifest 所有的固定行。

6. 启动 API：

   ```bash
   uv run uvicorn insightops.main:app --host 127.0.0.1 --port 8000 --reload
   ```

7. 在另一个终端检查服务：

   ```bash
   curl --fail --silent --show-error http://127.0.0.1:8000/health
   ```

   预期响应：

   ```json
   {"status":"ok"}
   ```

`/health` 只表示 API 进程存活，不检查数据库。数据库就绪由 Compose healthcheck 和 Alembic 命令分别验证。

## 开发检查

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict src tests scripts alembic
uv run pytest
```

验证迁移可回滚和重新执行：

```bash
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
```

## 持续集成与远程验证

GitHub Actions 在推送到 `main` 或创建、更新 Pull Request 时运行。CI 使用 MySQL 8.4
service，并依次验证锁定依赖安装、Ruff 格式和 lint、mypy、Alembic 升级与回滚、pytest，
最后启动 API 并请求 `GET /health` 进行 smoke test。

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
明确里程碑规划，不提前实现 Agent、Text2SQL 或 M1.1D 范围。
