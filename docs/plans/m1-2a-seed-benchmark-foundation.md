# M1.2A Seed Dataset & Benchmark Foundation

## 1. 交付目标与边界

M1.2A 为未来 Text2SQL 与 Evaluation Framework 提供小而可审查的企业分析基准。交付物包括固定
dataset contract、benchmark case contract、确定性 loader、业务校验、Gold SQL 和 expected results。
本阶段不修改 ORM、业务 Schema 或 Alembic，不创建 seed table，不实现 Agent、RAG、MCP 或 M1.1D。

## 2. 数据集合同

数据集 `insightcloud-m1-2a-benchmark@1.0.0` 绑定：

- Alembic revision `0003`；
- `insightcloud-business-definitions@1.0.0`；
- Gold catalog `insightcloud-m1-2a-gold-catalog@1.0.0`；
- `America/Los_Angeles` 业务时区；
- 固定事实截止时间 `2026-01-15T08:00:00Z`；
- 15 张现有表、152 行固定记录；
- dataset digest `93ade01290d3b0500ff7863888c64fdcdac72a291ae9bb27f7bef672f0fed46c`；
- oracle-assets digest `f37815846a2acebcc6da295a5996396b2114609be296303cd0c7736ba72179e4`。

digest 对规范化 manifest 元数据和 source rows 计算；JSON 文件顺序、键顺序和数值表示均经过合同约束。
所有业务主键、时间和金额均显式版本控制，不使用 Faker、随机 UUID、当前时间或运行时随机数。
dataset digest 只标识兼容性元数据与 source rows，不包含 catalog/oracle 反向引用，避免摘要循环；catalog
再绑定 dataset digest、每条 SQL digest 与每份 expected-result digest，整体 oracle-assets digest 回写到 manifest
和 expected results，从而形成可双向校验的完整版本链。

## 3. 文件与运行边界

- `data/seed/m1_2a/`：manifest 以及 identity、SaaS、Commerce source rows；
- `src/insightops/seed/`：合同、digest、业务校验和数据库生命周期；
- `benchmarks/m1_2a/cases.json`：48 个问题的公开元数据和 benchmark-only oracle 引用；
- `benchmarks/m1_2a/sql/`、`expected/`：仅供回归 oracle 使用；
- `src/insightops/benchmark/`：catalog 读取和只读 Gold SQL 执行边界。

`PublicBenchmarkCase` 明确移除 Gold SQL/expected result 的路径和 digest。未来 schema retrieval 或 prompt
构建只能消费公开合同，不得遍历或读取 `sql/` 与 `expected/`。

## 4. 数据覆盖与可验证指标

SaaS 数据覆盖月付/年付 MRR 规范化、New/Expansion/Contraction/Churned MRR、套餐快照、Logo 与 Revenue
Churn、成功/失败/重试支付，以及 SaaS Revenue 与 MRR 的时间差。Commerce 数据覆盖多明细订单、GMV、
distinct Order Count、AOV、跨期部分退款、Refund Rate、Merchant Net Sales 和 Platform Transaction
Revenue。订单在付款并产生成功退款和平台费用后才被取消的场景，确保 Refund Amount 只按
`refund.succeeded_at`、Platform Transaction Revenue 只按 `fee.succeeded_at` 归属，不能复用 GMV 的
取消订单 scope。

P07 当前仅为 partial coverage：GMV 与 Refund Amount 的增长关系已有数据和可执行 oracle；Marketing Cost
依赖营销域 Schema，明确等待 M1.1D。M1.2A 不声称完整覆盖 P07。

关键边界包括测试身份与事实链排除、未支付和取消订单、失败退款、计划取消尚未生效、同一组织多订阅、
一对多订单明细/退款分配，以及 cutoff 之后的事实。业务校验在写库前验证引用完整性、金额格式、时间边界、
订阅状态历史、支付/退款归属和显式 `is_test` 覆盖。

## 5. Gold Question 绑定

M1 catalog 的 48 个问题全部有确定状态：

- 16 个 `executable`：SaaS 8、Commerce 7、跨域 1；
- 2 个 `clarification_required`：因果归因和漏斗口径尚需澄清；
- 30 个 `deferred`：依赖 M1.1D 或后续域表。

每个可执行 case 固定问题、难度、业务域、指标、必需表、现象、参数、Gold SQL、列顺序和 typed result
rows。`required_tables` 必须与 SQL 实际访问的物理表集合一致。Gold SQL 先按各指标的权威事实与时间字段
分别聚合，再连接结果，避免 subscription event、order item、refund allocation 等一对多关系放大金额或计数。

## 6. Loader 与安全约束

loader 仅允许 `local`、`test`、`ci`，并在写入前检查 Alembic revision、digest 和完整业务校验。`load`
按 manifest 表顺序插入且可幂等验证，`verify` 对所有拥有行做精确比较，`unload` 逆序删除且不触碰非 seed
行。任何主键冲突但内容不一致都会失败，不允许覆盖现有数据。

Gold oracle 只接受单条 `SELECT` 或 `WITH` 查询，拒绝分号和非只读开头。它不是通用 SQL 安全引擎，也
不会被 Agent 复用。数据仅为合成业务记录，不含真实用户、凭证、生产标识或外部 API 数据。

## 7. 测试与验收

单元测试覆盖 contract、digest 稳定性、路径隔离、数据校验和 SQL 只读边界。MySQL 集成测试覆盖两轮
`load → verify → unload`、幂等 load、152 行计数和 16 条 Gold SQL 的冻结结果。回归结果同时验证：

- 测试数据排除；
- snapshot cutoff；
- 年付 MRR 折算和 MRR bridge 恒等式；
- GMV/Order Count 多明细去重；
- 退款分配与订单/平台收入分域聚合；
- 付款后退款/平台费用成功、订单随后取消时，退款与平台收入仍按各自成功时间计入；
- dataset、catalog、SQL 和 expected results 的版本与 digest 链；
- SaaS Revenue、MRR、GMV、Merchant Net Sales、Commerce Revenue 不混用。

dataset 内容、业务定义或 Gold SQL 发生有意变更时，必须显式提升版本并审查 digest 与 expected results，
不得在测试运行时自动重写 snapshot。
