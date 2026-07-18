# M1.2B Deterministic SQL Evaluation Harness v1

## 1. Scope Definition

M1.2B 建立不依赖模型调用的 SQL 评测基线。输入是版本绑定的 candidate submission，输出是可复现的
case result 和 deterministic report。

In scope：suite manifest、candidate submission contract、SQL AST analysis、benchmark-only 只读执行、结果
规范化与比较、错误 taxonomy、确定性报告。Out of scope：Agent、Text2SQL 生成、模型/provider、Prompt、RAG、
生产 SQL 安全系统、Product Event schema、Support schema、权限与审计产品化。

## 2. Version Binding

- Dataset：`insightcloud-m1-2a-benchmark@1.1.0`，digest
  `bf3efd9079bd434fe8f400fac161735e012548565fce9277e3bcf30ace44c18c`；
- Schema：Alembic `0004`；
- Business Definitions：`insightcloud-business-definitions@1.0.1`，digest
  `eb759951171f377c5c33a199d06d98dd4ebf0529b66d4e950ea8f622a778500d`；
- Catalog：`insightcloud-m1-2a-gold-catalog@1.1.0`；
- Oracle assets digest：
  `356369ee2c6664e87c818082f3d73f8c41be3323a8b5224b107cd5b95fafc4d0`。

M1.2B 不修改 ORM、Alembic、seed、Gold SQL 或 Expected Results。任何上述资产变化都要求显式版本提升，
不能由 evaluator 回写。

## 3. Architecture

冻结流水线为：Candidate Submission → Suite Validation → Action Routing → SQL AST Analysis → Readonly
Execution → Result Normalization → Semantic Comparison → Error Classification → Deterministic Report。

Suite Validation 只验证合同、版本链和 case partition；Action Routing 先处理 execute/clarification/deferred；
AST Analysis 只负责结构判定；Execution 只在 benchmark 数据库的 readonly 身份运行已通过分析的查询；
Normalization 不重算业务指标；Comparison 以 expected result 为 oracle；Classification 只记录最早失败阶段；
Report 将确定性内容与运行环境元数据分开。

## 4. Contract Design

`EvaluationSuiteManifest` 冻结 suite/evaluator 版本、digest 算法、dataset/catalog/schema/Business Definitions/
oracle 绑定、48 case 的 expected action、clarification code、comparison policy 和 execution limits。

`CandidateSubmission` 只允许 suite binding 和 case responses。`execute_sql` 仅包含 `case_id` 与 `sql`；
`request_clarification` 仅包含 `case_id` 与 `clarification_code`。禁止 expected rows、Gold SQL、oracle path 和
execution-limit override。28 个 executable 和 6 个 clarification case 必须各有一个 response；14 个 deferred
case 禁止 response。

`CaseEvaluationResult` 冻结 expected/actual action、top-level status、failure/secondary codes、stage results 和
digests。完成报告分为 `deterministic_payload` 与 `run_envelope`；后者的 run ID、时间、耗时和 host 不参与摘要。
ABORTED report 只有稳定 abort code 与 `run_envelope`，没有 case score、deterministic payload 或 evaluation digest。

## 5. SQL Parser Decision

M1.2B 精确锁定 `sqlglot==30.12.0`，使用 MySQL dialect。必须支持单语句、SELECT/WITH、CTE、表提取、
wildcard 检测和 bind 校验；拒绝 DML、DDL、多语句、系统 schema、文件操作、锁定语句、危险函数和用户变量。
禁止用正则模拟 SQL parser。M1.2B-0 不引入该依赖，也不解析 SQL。

## 6. Database Execution Boundary

writer 身份仅用于 migration、seed load 和 dataset validation；readonly 身份仅用于 candidate SQL。
M1.2B-2 才增加 compose/CI bootstrap 与 readonly credential fixture，并强制只读事务、5 秒超时、1000 行
和 1 MiB 输出上限。服务端 5 秒限制先触发，客户端 read timeout 保留额外缓冲；任何 DBAPI timeout/disconnect
都会 rollback 并 invalidate connection，状态不确定的连接不得回池。该边界是 benchmark execution environment，
不声称是 production SQL security system。
M1.2B 不新增 migration。

## 7. Result Comparison Contract

列名、列顺序、类型、NULL、Decimal、datetime 和行值均严格比较。suite case 内的 reviewed
`expected_column_types` 是 evaluator-internal、suite-digest-bound metadata；Expected Result 只能按声明类型解码，
不得根据字符串外观猜测 Decimal 或 datetime。存在 `ordered_by` 的 case 使用 exact
sequence；否则使用 canonical multiset。禁止数值容差和类型强制转换。normalization 只规范数据库驱动的
表示差异，不改变业务值或重新实现业务逻辑。

## 8. Error Taxonomy

一级状态为 `PASS`、`FAIL_ACTION`、`FAIL_STRUCTURE`、`FAIL_EXECUTION`、`FAIL_RESULT`、
`NOT_EVALUATED`、`ABORTED`。case 只记录最早失败阶段；`ABORTED` 只用于 run-level suite、binding、submission
或环境失败，不作为普通 case score。二级码由 evaluation contract 的固定枚举承载，后续 taxonomy 模块只
提供分组与报告映射，不另建不一致的字符串集合。

## 9. Clarification Evaluation

以下 6 个 case 不执行 SQL，只比较 expected action 与 clarification code：

- GQ-SAA-009：`observable_churn_scope_required`；
- GQ-COM-007：`order_lifecycle_funnel_definition_required`；
- GQ-MKT-006、GQ-MKT-007：`attributed_revenue_type_required`；
- GQ-PRD-005：`registration_source_attribution_unavailable`；
- GQ-XDM-003：`touch_to_registration_funnel_definition_required`。

## 10. Digest Design

使用 `sha256-canonical-json-v1`。suite digest 排除自身字段；submission digest 覆盖完整 oracle-free submission；
evaluation digest 覆盖 suite/submission/evaluator 版本与排序后的 case outcomes。timestamp、run ID、duration、host
始终排除。

## 11. Directory Design

版本资产位于 `evaluations/m1_2b/`；可复用代码位于 `src/insightops/evaluation/`。最终模块边界为
`contracts.py`、`suite.py`、`sql_analysis.py`、`execution.py`、`normalization.py`、`comparison.py`、
`runner.py`、`reporting.py` 和 `__main__.py`。MVP 的 failure taxonomy 由 contracts 中的稳定 enum 承载，
不为映射字符串再创建空的 `taxonomy.py`。共享 `canonical.py` 和 benchmark catalog contract；candidate
analysis/execution 路径禁止读取 Gold SQL 或 Expected Results。benchmark registry 在 trusted preflight 阶段读取
Gold/Expected assets 只做 oracle integrity validation；comparison 阶段才读取 expected business result 参与比较。
两条内部路径都不向 candidate contract 或 report 暴露 oracle 内容。

## 12. Dependency Changes

唯一新增的运行依赖是精确锁定的 `sqlglot==30.12.0`，用于可靠 MySQL AST 判定，因此会更新 project
metadata、lock file 和 CI dependency cache。MySQL driver、canonical serialization、Pydantic、pytest 和报告
JSON 均复用现有依赖，不新增 normalization 或 reporting library。M1.2B-0 不改变依赖。

## 13. Test Plan

Unit 覆盖 contracts、suite、parser、normalization、comparison 和 taxonomy。Integration 覆盖 readonly identity、
Gold controls、恶意 SQL 拒绝、timeout、row/output limit 和 digest tamper。每个阶段必须保持既有回归测试通过，
不调用真实模型或生产数据库。

## 14. Implementation Delivery

M1.2B-0 先冻结 suite/submission/result/report 合同。其余 parser、readonly execution、normalization、comparison、
runner/report、CLI、bootstrap 与 CI 在 `codex/m1-2b-evaluation-harness` 单一 feature branch 交付端到端 MVP，
以一次 28/6/14 control、危险 SQL、资源限制、tamper、digest repeatability 和全量回归审查验收，不再按
M1.2B-1—M1.2B-5 单独合并或审查。

## 15. Risks and Frozen Decisions

主要风险是 oracle 泄漏、parser/MySQL 方言差异、readonly 身份误配置、把结果一致夸大为普遍语义正确，以及
对单一 dataset 过拟合。已冻结 candidate submission 格式、ordered/unordered policy、strict type/no tolerance、
digest scope、oracle visibility boundary、错误一级状态、clarification codes、`sqlglot==30.12.0`，以及本地
Compose/CI 使用同名 readonly 环境合同的 bootstrap 方案。
