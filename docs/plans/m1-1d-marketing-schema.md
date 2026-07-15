# M1.1D Marketing Schema 实施记录

## 目标与范围

本批次把冻结的 Marketing Domain Schema 实现为 SQLAlchemy 2.x typed declarative mappings 和 Alembic
revision `0004`。仅新增以下五张表：

- `marketing_channel`
- `marketing_campaign`
- `campaign_daily_spend`
- `marketing_touch`
- `attributed_conversion`

`0001`—`0003` 以及已有 SaaS/Commerce ORM 保持不变。本批次不更新 M1.2A dataset/catalog、Gold SQL，
也不实现 Agent、Evaluation、归因计算服务或业务 API。

## 冻结的数据边界

- `marketing_channel.channel_code` 是 immutable 业务代码；`channel_name` 是可变显示名。
- campaign 明确冻结 `saas/commerce` business scope，避免组织与消费者主体混用。
- daily spend 是 append-only final revision。更正创建更高 `version_number` 并引用被替代 revision；表中
  不设置 provisional 状态或 `updated_at`。
- touch 是 append-only 事件，区分 occurred、received、processed 和 recorded 可见时间，并且只能解析到
  organization 或 consumer 中的一个主体。
- attribution 结果是 append-only 派生事实。Gold SQL 的后续升级只能读取 `attributed_conversion`，不得
  在查询中重新实现 `last_non_direct_168h_v1`。
- 统一使用 **Attributed ROAS** 命名，避免与财务 ROI 混淆。

## Attribution 完整性

- conversion type 固定为 `saas_first_payment`、`saas_revenue`、`commerce_first_payment`、
  `commerce_revenue`、`attributed_gmv`。
- 三个显式 authoritative FK 指向 payment attempt、commerce order 和 platform fee charge。数据库 CHECK
  同时保证 fact XOR、conversion type/fact 对应关系，不使用 polymorphic ID。
- subject XOR 要求 SaaS conversion 仅有 organization，Commerce conversion 仅有 consumer；同一 CHECK
  进一步约束 conversion type、fact 和 subject 的完整组合。
- `non_direct` 必须保存 `selected_marketing_touch_id` 和 channel；`direct`/`unknown_unattributed` 的
  selected touch 必须为空。result、reason code 与 `history_complete` 的允许组合由 CHECK 固定。
- 模型固定为 `last_non_direct_168h_v1`，窗口固定为 168 小时。每个结果记录
  `source_data_cutoff_at`；late-arriving touch 只能在更晚 cutoff 追加新结果，不回写旧结果。

## Snapshot 规则

daily spend as-of 查询必须按以下顺序执行：

1. 只保留 `recorded_at <= snapshot_cutoff` 的可见 revision；
2. 在可见集合中按 `(marketing_campaign_id, business_date)` 选择最大 `version_number`；
3. 只聚合被选中的 final revision。

禁止先对全表执行 `MAX(version_number)` 再检查可见时间。对应 MySQL 集成测试使用窗口函数固定这一查询
语义。

## Migration 与回滚

- upgrade 顺序：channel → campaign → spend → touch → attributed conversion。
- downgrade 顺序：attributed conversion → touch → spend → campaign → channel。
- revision `0004` 显式声明 DDL，不导入 ORM，也不使用 `Base.metadata.create_all()`。
- migration 生命周期覆盖 `0003 → 0004 → 0003 → 0004` 和
  `base → 0004 → base → 0004`，并在结束时恢复到 head。

## 数据库与应用层边界

数据库保证 PK/FK、显式 fact/subject XOR、行内 result/reason、版本唯一性、单行时间顺序、币种、金额、
布尔值和 FK RESTRICT。

跨行或跨表语义由后续写入服务和数据质量任务保证，包括：spend revision 必须与 predecessor 属于同一
campaign/date 且 version 连续；selected touch 必须与 attribution 的主体、channel、campaign、窗口和 cutoff
一致；direct channel 类型；campaign 的 merchant/organization 归属；以及测试标记全链路排除。本阶段不以
trigger 或冗余字段伪造这些保证。

## 验证策略

- metadata/structure 单元测试验证精确 20 表、类型、ASCII binary collation、具名约束、索引、append-only
  表不含 `updated_at`，以及 ORM/migration 结构一致性。
- MySQL 集成测试验证 channel、campaign、spend revision、touch 可见性、authoritative fact XOR、subject
  XOR、selected touch、result/reason、168 小时窗口和 source-data cutoff。
- migration 测试验证 0003/0004 增量往返与 base/0004 全量往返，并确认 0003 降级状态不存在营销表。
- M1.2A dataset 1.0.0 继续绑定 revision `0003`，不把其既有 benchmark 测试计入 0004 营销验收。

## 验收结果

- Ruff format check：通过，47 个 Python 文件均已格式化。
- Ruff lint：通过。
- strict mypy：通过，47 个源文件无问题。
- Marketing + migration 定向测试：31 个全部通过。
- 全量 pytest：183 个全部通过；仅保留一个来自 Starlette TestClient/httpx 兼容层的既有弃用警告。
- Alembic 增量生命周期 `0003 → 0004 → 0003 → 0004`：通过。
- Alembic 全量生命周期 `base → 0004 → base → 0004`：通过。
- 最终数据库 revision：`0004 (head)`。
- M1.2A 的数据库测试通过模块级 revision fixture 在 `0003` 执行，结束后自动恢复 `0004`；dataset、
  catalog、Gold SQL 和冻结结果均未修改。
