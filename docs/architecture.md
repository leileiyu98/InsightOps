# InsightOps 架构说明

## 架构边界

InsightOps 初期采用模块化单体。M0 只建立已经有实际用途的边界：

- `api`：FastAPI 路由、HTTP 参数和响应模型；
- `core`：环境配置及其确定性校验；
- `db`：SQLAlchemy 元数据、引擎和 Session 工厂；
- `alembic`：所有数据库结构变更的唯一入口；
- `tests`：单元测试和 HTTP 边界集成测试。

M0 没有业务流程或领域规则，因此不创建空的应用服务层和领域层。后续里程碑出现相应逻辑时再增加这些模块。

## 依赖方向

FastAPI 应用工厂依赖 API 路由和经过校验的 `Settings`。数据库基础设施也只依赖 `Settings`，API 不直接访问数据库。Alembic 复用相同配置和 SQLAlchemy metadata，避免出现第二套连接配置。

配置和数据库资源不保存在隐藏的全局可变缓存中。ASGI 入口只创建框架要求的应用实例；测试通过应用工厂显式传入隔离配置。

## 健康检查

`GET /health` 是 liveness 检查，只证明 API 进程能够响应。它不连接 MySQL，因此数据库短暂不可用不会把仍在运行的进程报告为死亡。

M0 的数据库 readiness 由两个确定性步骤验证：

1. MySQL 容器的 `mysqladmin ping` healthcheck；
2. Alembic 能在空数据库执行到当前 head。

如果后续部署需要统一的 readiness API，应在对应里程碑单独设计，不能改变 `/health` 的现有语义而不记录兼容性决定。

## 数据库边界

SQLAlchemy 采用 2.x API，并在真正使用连接前保持惰性。M0 migration 只建立 Alembic 版本基线，不创建业务表。

M1.1B 和 M1.1C 在模块化单体的数据库边界内增加企业身份、SaaS 与商城 ORM 映射。模型按
`insightops.db.models.identity`、`insightops.db.models.saas` 和 `insightops.db.models.commerce` 组织，
`insightops.db.models` 是唯一显式注册入口；Alembic 从该入口取得 `Base.metadata`，不依赖 FastAPI
启动时的偶然导入。`0002` 独立创建 9 张身份与 SaaS 表，`0003` 独立创建 6 张商城表，ORM 不使用
`create_all()` 代替 migration。

商城 GMV 的权威金额只保存在订单商品明细，订单本身只保存首次支付时间和当前资格状态。退款和平台
服务费是按各自成功时间归期的独立事实；退款分配只承担商品退款金额到订单明细的分配，不复制 GMV。
跨行分配合计、退款与订单明细归属、商家有效区间和测试数据全链路排除仍属于后续应用事务或数据质量责任。

每个新 MySQL 物理连接通过 SQLAlchemy connect 事件执行 `SET time_zone = '+00:00'`。ORM 的
`server_onupdate` 只标记 `updated_at` 是服务器生成字段；真正的
`DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)` 由 migration 显式生成，并由真实
MySQL Schema 和行为测试验证。

Compose 创建的账号只用于隔离的本地开发和迁移，不代表未来执行分析 SQL 的只读账号。后续模型或 Agent 不得直接使用数据库基础设施绕过应用服务、权限和 SQL 安全校验。

## 当前仍未实现

M1.1C 之外的营销、产品使用和客服表，以及种子数据、业务 API、认证授权、大模型提供商、
Text2SQL、RAG、Agent 工作流、SQL 安全、Memory、MCP、异步任务、缓存、前端和复杂可观测性均不属于
当前架构实现。
