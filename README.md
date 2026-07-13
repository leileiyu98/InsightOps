# InsightOps

InsightOps 是一个面向企业经营分析场景的大模型应用项目。当前仓库处于 **M0：项目骨架与本地开发环境**，只提供后续开发所需的可运行、可测试基础。

## 当前能力

- Python 3.12 与 uv 项目管理
- FastAPI 应用工厂和 `GET /health` 存活检查
- Pydantic 环境配置
- SQLAlchemy 2.x 引擎和 Session 工厂
- Alembic 空基线迁移
- MySQL 8.4 Docker Compose 开发环境
- pytest、Ruff、mypy 和 GitHub Actions

M0 不包含业务数据表、登录权限、大模型 API、Text2SQL、RAG、Agent、SQL 安全引擎、Memory、MCP、Redis、Celery 或前端。

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

5. 启动 API：

   ```bash
   uv run uvicorn insightops.main:app --host 127.0.0.1 --port 8000 --reload
   ```

6. 在另一个终端检查服务：

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
uv run mypy src tests alembic
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

当前边界和设计理由见 [`docs/architecture.md`](docs/architecture.md)，M0 实施范围与验收见 [`docs/plans/m0-project-foundation.md`](docs/plans/m0-project-foundation.md)。M0 验收完成后的下一项工作应继续按明确里程碑规划，不提前实现 Agent 或 Text2SQL。
