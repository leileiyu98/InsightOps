# M1.2A Seed Dataset & Benchmark Foundation

## 1. 交付目标与边界

M1.2A 为未来 Text2SQL 与 Evaluation Framework 提供小而可审查的企业分析基准。交付物包括固定
dataset contract、benchmark case contract、确定性 loader、业务校验、Gold SQL 和 expected results。
本阶段不修改 ORM、业务 Schema 或 Alembic，不创建 seed table，不实现 Agent、RAG、MCP 或 Evaluation。

## 2. 数据集合同

数据集 `insightcloud-m1-2a-benchmark@1.1.0` 绑定：

- Alembic revision `0004`；
- `insightcloud-business-definitions@1.0.1`，内容摘要算法 `sha256-nfc-lf-v1`；
- Gold catalog `insightcloud-m1-2a-gold-catalog@1.1.0`；
- `America/Los_Angeles` 业务时区；
- 固定数据可见截止时间 `2026-01-15T08:00:00Z`；Activation 独立观察截止时间
  `2025-07-01T07:00:00Z`；
- Marketing 历史覆盖起点 `2025-04-01T07:00:00Z`；
- 20 张现有表、334 行固定记录；
- dataset digest `bf3efd9079bd434fe8f400fac161735e012548565fce9277e3bcf30ace44c18c`；
- Business Definitions digest
  `eb759951171f377c5c33a199d06d98dd4ebf0529b66d4e950ea8f622a778500d`；
- oracle-assets digest `356369ee2c6664e87c818082f3d73f8c41be3323a8b5224b107cd5b95fafc4d0`。

digest 对规范化 manifest 元数据和 source rows 计算；JSON 文件顺序、键顺序和数值表示均经过合同约束。
所有业务主键、时间和金额均显式版本控制，不使用 Faker、随机 UUID、当前时间或运行时随机数。
dataset digest 只标识兼容性元数据与 source rows，不包含 catalog/oracle 反向引用，避免摘要循环；业务定义
先对文档做 UTF-8 BOM 去除、NFC、LF 和单一末尾换行规范化，再计算内容摘要。catalog
再绑定 dataset digest、每条 SQL digest 与每份 expected-result digest，整体 oracle-assets digest 回写到 manifest
和 expected results，从而形成可双向校验的完整版本链。

## 3. 文件与运行边界

- `data/seed/m1_2a/`：manifest 以及 Identity、SaaS、Commerce、Marketing source rows；
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
取消订单 scope。Marketing 数据覆盖渠道、活动、append-only spend revision、touch 和物化 attribution；
CAC、SaaS Attributed ROAS 与 Commerce Attributed ROAS 分开计算，Gold SQL 只读取
`attributed_conversion`，不重算 `last_non_direct_168h`。

P07 已覆盖 GMV、Refund Amount 与 Marketing Cost 的季度变化。渠道当前 `status` 不参与历史归因；候选
touch 只按测试标记、非 direct 类型、历史有效区间、processed/recorded cutoff、主体与 campaign 一致性判断。
渠道后来 inactive 不追溯改变已物化结果，位于 `effective_to` 之后的 touch 才被排除。

关键边界包括测试身份与事实链排除、未支付和取消订单、失败退款、计划取消尚未生效、同一组织多订阅、
一对多订单明细/退款分配，以及 cutoff 之后的事实。业务校验在写库前验证引用完整性、金额格式、时间边界、
订阅状态历史、支付/退款归属和显式 `is_test` 覆盖。历史不足 conversion 必须由 validator 证明 168 小时
窗口起点早于 coverage boundary，并物化为 `unknown_unattributed/window_history_incomplete`。

## 5. Gold Question 绑定

M1 catalog 的 48 个问题全部有确定状态：

- 28 个 `executable`：原 16 个，加 GQ-MKT-001—005、008、GQ-PRD-001、006—008、
  GQ-XDM-002、007；
- 6 个 `clarification_required`，其中 GQ-PRD-005 保持澄清，不以首次付费归因推断注册来源；
- 14 个 `deferred`：依赖后续域表。

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
`load → verify → unload`、幂等 load、334 行计数和 28 条 Gold SQL 的冻结结果。回归结果同时验证：

- 测试数据排除；
- snapshot cutoff；
- 年付 MRR 折算和 MRR bridge 恒等式；
- GMV/Order Count 多明细去重；
- 退款分配与订单/平台收入分域聚合；
- 付款后退款/平台费用成功、订单随后取消时，退款与平台收入仍按各自成功时间计入；
- dataset、catalog、SQL 和 expected results 的版本与 digest 链；
- spend revision 先按 `recorded_at <= snapshot_cutoff` 过滤，再选择最大 `version_number`；
- Attribution 候选资格、direct/unknown 结果、晚到 touch 和历史覆盖边界；
- Activation 的 `activation_observation_as_of_utc` 与 dataset snapshot cutoff 相互独立；
- SaaS Revenue、MRR、GMV、Merchant Net Sales、Commerce Revenue 不混用。

v1.0.0 可由 merge commit `70680bc087a739583bcd5242907f9f0c6d9b2e0b` 重现。日常 CI 不读取 Git
历史，只校验紧凑的 `baseline_1.0.0_index.json`、reviewed delta report 与当前资产。旧 16 case 的
business-result digest 用来区分真实结果变化与纯 metadata/digest 变化；未登记原因的变化会使测试失败。

正式 oracle 的 authoring 必须使用独立、初始为空且名称以 `_authoring` 结尾的 schema。脚本在该 schema
执行 `base → manifest revision`、正式 seed load/validator、20 表精确行数与额外行检查后，才执行 28 条
Gold SQL；成功或失败均回滚至 base 并确认 schema 无表。默认模式只写 candidate 目录，不能覆盖
`cases.json`、manifest 或 expected；只有 clean worktree 下的显式 `--apply-reviewed`，且 candidate 的输入
digest 仍与仓库一致时，才能应用人工审查后的资产。dirty-worktree override 只能生成 candidate。

`baseline_1.0.0_index.json` 默认仅 compare，显式参数才能覆盖。正式 delta 是 reviewed asset，逐 case 冻结
old/new expected digest 与 old/new business-result digest 的精确 pair；普通 generator 只写 candidate。
任何新 pair 不继承既有 change reason/scenario，而标记 `review_required`；只有人工批准并显式 apply 后才能
替换正式 delta。CI 直接验证 baseline、reviewed delta 与当前 expected 的精确 pair，不依赖 Git 历史。

dataset 内容、业务定义或 Gold SQL 发生有意变更时，必须显式提升版本并审查 digest 与 expected results，
不得在测试运行时自动重写 snapshot。
