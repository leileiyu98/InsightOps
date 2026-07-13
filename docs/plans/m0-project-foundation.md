# M0 项目骨架与本地开发环境

## 目标

建立一个最小、清晰、可运行和可测试的 FastAPI 项目骨架，为后续里程碑提供稳定基础，同时不提前实现任何企业数据分析功能。

## 实施内容

- 使用 Python 3.12、uv、`src` 布局和 `uv_build`；
- 提供 FastAPI 应用工厂和 `GET /health`；
- 使用 Pydantic Settings 从环境变量和 `.env` 读取配置；
- 提供 SQLAlchemy 2.x Base、Engine 和 Session 工厂；
- 配置 Alembic 并提供可升级、可回滚的空基线 migration；
- 使用 Docker Compose 启动单个 MySQL 8.4 服务；
- 配置 pytest、Ruff、mypy 和 GitHub Actions；
- 提供可由新环境复现的 README 和架构说明。

## 关键决策

- `/health` 是不依赖数据库的 liveness 接口；
- 数据库 URL 使用 SQLAlchemy `URL.create()` 组装，凭证不写入源码或 Alembic 配置；
- SQLAlchemy 引擎创建不触发连接；
- 只添加空 migration 基线，不创建业务表；
- 使用纯 Python 的 PyMySQL，避免本地 C 编译工具链；
- 当前没有业务逻辑，不创建空领域层、应用服务层或 Repository；
- M0 开发账号不是未来分析查询的只读账号。

## 验收标准

1. `uv sync --locked` 可安装依赖；
2. Docker Compose 可启动健康的 MySQL 8.4；
3. Alembic 可从空数据库 upgrade、downgrade 并重新 upgrade；
4. Uvicorn 可启动应用，`GET /health` 返回 HTTP 200 和 `{"status":"ok"}`；
5. pytest、Ruff format、Ruff lint 和 mypy 全部通过；
6. README 的步骤可在新环境中复现；
7. Git diff 中没有 M0 范围外文件、真实凭证或本地生成数据。

## 范围限制

M0 不实现业务表、种子业务数据、登录权限、大模型 API、Text2SQL、RAG、Agent、SQL 安全引擎、Memory、MCP、Redis、Celery、前端或复杂监控。
