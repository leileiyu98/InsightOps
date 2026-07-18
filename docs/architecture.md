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

M1.1B、M1.1C 和 M1.1D 在模块化单体的数据库边界内增加企业身份、SaaS、商城与营销 ORM 映射。模型按
`insightops.db.models.identity`、`insightops.db.models.saas`、`insightops.db.models.commerce` 和
`insightops.db.models.marketing` 组织，
`insightops.db.models` 是唯一显式注册入口；Alembic 从该入口取得 `Base.metadata`，不依赖 FastAPI
启动时的偶然导入。`0002` 独立创建 9 张身份与 SaaS 表，`0003` 独立创建 6 张商城表，`0004` 独立
创建 5 张营销表；ORM 不使用 `create_all()` 代替 migration。

商城 GMV 的权威金额只保存在订单商品明细，订单本身只保存首次支付时间和当前资格状态。退款和平台
服务费是按各自成功时间归期的独立事实；退款分配只承担商品退款金额到订单明细的分配，不复制 GMV。
跨行分配合计、退款与订单明细归属、商家有效区间和测试数据全链路排除仍属于后续应用事务或数据质量责任。

营销域只保存治理后的 channel/campaign、append-only 花费 revision、可见时间明确的 touch，以及已经由
`last_non_direct_168h_v1` 算法物化的最终 attribution result。`attributed_conversion` 用三个显式权威事实
外键和 CHECK 约束冻结 fact XOR、SaaS/Commerce subject XOR、结果链接与 reason code 一致性；分析查询不
重新实现归因算法。花费快照必须先按 `recorded_at <= snapshot_cutoff` 过滤可见 revision，再在每个
`(campaign, business_date)` 内选择最大 `version_number`。

每个新 MySQL 物理连接通过 SQLAlchemy connect 事件执行 `SET time_zone = '+00:00'`。ORM 的
`server_onupdate` 只标记 `updated_at` 是服务器生成字段；真正的
`DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)` 由 migration 显式生成，并由真实
MySQL Schema 和行为测试验证。

Compose 的 writer 账号只用于隔离的本地 migration、seed lifecycle 和 dataset verify。M1.2B 另由幂等
bootstrap 创建只有当前 benchmark database `SELECT` 权限的 readonly identity；candidate SQL 只能经该身份
进入 `START TRANSACTION READ ONLY`，并受 5 秒、1000 行和 1 MiB 输出上限约束。该边界用于确定性 benchmark，
不声称是生产 SQL sandbox。后续模型或 Agent 不得直接使用数据库基础设施绕过应用服务、权限和 SQL 安全校验。

## Evaluation 边界

`insightops.evaluation` 是 M1.2B 的独立模块：suite/submission contract → MySQL AST analysis → readonly
execution → typed normalization → exact ordered/unordered comparison → deterministic report。`sqlglot==30.12.0`
只负责结构解析；analyzer 和 candidate executor 不读取 Gold SQL 或 Expected Results。Trusted preflight 通过
benchmark registry 读取 Gold/Expected assets 只做完整性验证，comparison 阶段才读取 expected business result。
JSON report 只输出状态、failure code 和 digest，不输出 SQL、expected rows 或文件路径。

writer 在整次评测前后调用现有 `DatasetLoader.verify()`；candidate engine 使用完全独立的环境变量与数据库
用户。run envelope 的 run ID、时间、耗时和 host 不进入 deterministic digest，因此相同 suite/submission/
dataset 可产生一致摘要。

## Text2SQL Demo 边界

`insightops.query` 是 M1.3 的应用服务边界：自然语言问题先进入 oracle-free context builder，再由一个
`QueryProvider` 返回 Pydantic 校验后的 SQL 或澄清合同。fake provider 为测试和离线演示提供固定候选；OpenAI
adapter 是唯一真实 provider，使用 Responses API Structured Outputs，读取环境密钥并把 SDK 异常映射为稳定
应用错误；固定的 app lifespan/CLI finally 负责关闭 provider client 和 composition root 创建的数据库 engine。
provider 无权提供数据库凭证、执行上限、预期结果或 evaluator 配置。

带 `case_id` 的请求由 `EvaluationRunner.run_case()` 进入与 M1.2B 整套评测相同的 action、AST、readonly
execution、normalization 和 comparison 阶段。这个窄入口额外返回 candidate 的实际 normalized rows，供 API
展示，但不返回 expected rows。无 `case_id` 的自由问题复用同一 analyzer 和 readonly executor，并在前后验证
固定 dataset；它不会读取 comparison oracle，成功状态始终是 `not_benchmark_scored`。

`POST /v1/query` 只负责 HTTP 合同和错误映射，核心流程位于 `QueryService`。CLI 复用相同 composition root 和
service。业务摘要由实际 normalized result 确定性渲染，保留原始字符串数值；摘要失败时只省略摘要，不丢失
已通过评测的 SQL 结果。

## 当前仍未实现

M1.1D 之外的产品使用和客服表，以及认证授权、RAG、Agent 工作流、生产级 SQL sandbox、Memory、MCP、
异步任务、缓存、前端和复杂可观测性均不属于当前架构实现。M1.3 也不提供会话、多轮重试、向量检索或
多 provider 路由。
