# M1.3 Text2SQL Demo MVP

## 目标与范围

M1.3 提供一条可演示、可测试的最短业务查询路径：question → bounded context → structured provider →
M1.2B evaluation/readonly execution → result table → deterministic summary。范围仅覆盖现有 20 张表和 M1.2A
dataset；不增加 Schema、Gold case、RAG、Agent、前端或持久化能力。

## 组件

- `query.contracts`：互斥 SQL/澄清 provider 合同，以及 oracle-free API response。
- `query.context`：从 `PublicBenchmarkCase`、dataset 时间合同、精简业务规则和 SQLAlchemy metadata 构建上下文。
- `query.providers`：`QueryProvider` 协议、deterministic fake 和单一 OpenAI Responses adapter。
- `evaluation.runner.run_case`：复用 M1.2B 阶段的单 case 运行入口，额外返回 candidate 实际结果。
- `query.service`：benchmark scoring、自由查询安全边界、稳定错误和摘要降级。
- `api.query` / `query.__main__`：共享应用服务的 HTTP 与 CLI 入口。

## 安全与隔离

provider 上下文不读取 benchmark-only catalog 字段、Gold SQL、Expected rows、baseline/delta 或 asset path。
所有 SQL 都先进入 sqlglot AST analyzer，再由独立 `READONLY_DATABASE_*` 身份在 read-only transaction 中执行，
并继承 M1.2B 的 timeout、row 和 output limits。benchmark evaluator 失败不会触发第二条绕过评测的执行路径。

自由查询没有可比较的 oracle，只允许无 bind parameter 的单条 SELECT/CTE，复用 allowlisted table、危险函数、
文件操作、锁、wildcard 和系统 Schema 检查。成功结果明确标记 `not_benchmark_scored`。

## Provider 决策

官方 `openai` Python SDK 是本阶段唯一新增主要依赖。它提供 Responses API、超时/重试和 Pydantic Structured
Outputs，避免维护手写 HTTP 与重复 JSON Schema。运行时依赖精确锁定为 `openai==2.46.0`，默认模型由
`OPENAI_MODEL` 配置为 `gpt-5.6-sol`（也允许官方 alias `gpt-5.6`）。adapter
显式使用 low reasoning effort，不发送未确认适用于该模型调用模式的 `temperature`，并确定性处理 refusal、
incomplete/failed、缺失 parsed payload 和缺失 usage。自动测试始终使用 fake 或 mocked SDK，不依赖密钥或网络。
维护成本是 SDK 升级时必须重新核对 Responses/Structured Outputs 合同并更新 mocked contract tests；更简单的
手写 HTTP 替代会重复维护认证、错误映射、schema 解析和类型，因此本阶段不采用。

## 测试与验收

Unit 覆盖结构化合同、context oracle 隔离、fake/provider error、summary 数值保真。真实 MySQL integration
覆盖 executable PASS、clarification PASS、FAIL_STRUCTURE、FAIL_RESULT、unscored execution、稳定 provider
错误、API 脱敏、dataset 前后不变和 summary 降级。最终执行 Ruff format/lint、strict mypy、full pytest、
Alembic `0004`、API/CLI smoke、`git diff --check`，并确认 dataset/catalog/oracle/suite 未修改。

## 已知限制

- fake provider 只内置三个 benchmark 演示 case 和一个固定自由查询；它不是通用自然语言模型。
- 自由问题不支持模型声明运行时 bind 参数，也不具备 Gold result scoring。
- 业务摘要是确定性首行摘要，不做复杂洞察或建议。
- 当前 readonly executor 是求职项目 demo 边界，不声明为生产级多租户 SQL sandbox。
