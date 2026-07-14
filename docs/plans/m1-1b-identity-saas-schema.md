# M1.1B 企业身份与 SaaS Schema 实施记录

## 目标与范围

本批次将 `docs/m1-physical-data-model.md` 中的企业身份与 SaaS 物理模型实现为 SQLAlchemy 2.x
typed declarative mappings 和 Alembic revision `0002`。

实施表仅包括：

- `organization`
- `organization_member`
- `consumer`
- `merchant`
- `saas_plan_version`
- `subscription`
- `subscription_state_event`
- `subscription_invoice`
- `invoice_payment_attempt`

不包含商城、营销、产品使用、客服、种子数据、Gold SQL、业务 API、repository/service、Text2SQL、
RAG、Agent、Memory 或 MCP。

实施时复核了物理模型基线：`saas_plan_version` 字段表中实际只有一行 `effective_to`，不存在可删除的
重复行，因此未误删这个必需字段；文档只更新了 M1.1B 的实施状态。

## 代码组织

- `insightops.db.models.identity` 保存 4 个企业与身份模型。
- `insightops.db.models.saas` 保存 5 个 SaaS 模型。
- `insightops.db.models.sql_types` 集中定义 unsigned bigint、`DECIMAL(19,4)`、`DATETIME(6)` 和
  ASCII binary 标识类型，防止 ORM 映射内部漂移。
- `insightops.db.models` 显式导入全部模型并重新导出 `Base`，作为 ORM 和 Alembic 的共同注册入口。
- 模型不包含应用服务、业务流程或无实际用途的 relationship。

## Schema 决策

- 内部主键和外键使用 `BIGINT UNSIGNED`；套餐版本号使用 `SMALLINT UNSIGNED`。
- 金额使用 `DECIMAL(19,4)` 和 Python `Decimal`，不使用浮点数。
- 业务时间使用 `DATETIME(6)`，不使用 MySQL `TIMESTAMP`。
- 外部 ID、来源 ID 和支付提供商交易 ID 使用 ASCII 字符集及 `ascii_bin` 排序规则，保证大小写敏感。
- 状态和事件类型使用 `VARCHAR` 加具名 Check Constraint，不使用 MySQL ENUM。
- `is_test` 使用 SQLAlchemy `Boolean`，并额外使用具名 `IN (0, 1)` Check，确定性约束 MySQL
  `TINYINT(1)` 的物理取值。
- 所有外键显式使用 `ON DELETE RESTRICT ON UPDATE RESTRICT`。
- 所有唯一约束、Check、外键和普通索引具有确定名称，且名称不超过 MySQL 64 字符。
- `merchant` 允许同一 `merchant_id` 保存多个不同起点的历史区间；区间不重叠不由本批次伪造为
  数据库单行约束。

## UTC 与 `updated_at`

每个新 MySQL 物理连接通过 SQLAlchemy connect 事件执行：

```sql
SET time_zone = '+00:00'
```

ORM 中的 `server_onupdate` 只通知 SQLAlchemy 该字段由服务器更新，不作为 DDL 已生成的证明。
Revision `0002` 对可变实体明确生成：

```sql
updated_at DATETIME(6)
    NOT NULL
    DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6)
```

集成测试通过 `information_schema.columns.EXTRA` 检查 `ON UPDATE CURRENT_TIMESTAMP(6)`，并实际更新
organization 行，确认数据库自动刷新 `updated_at`。

## Migration 依赖顺序

Upgrade 顺序：

1. organization
2. consumer
3. saas_plan_version
4. organization_member
5. merchant
6. subscription
7. subscription_state_event
8. subscription_invoice
9. invoice_payment_attempt

Downgrade 按逆外键依赖删除。`0001` 空基线保持不变；migration 不导入 ORM 模型，也不调用
`Base.metadata.create_all()`。

## 测试隔离

真实 MySQL 测试使用单个共享 Schema，并通过 `/tmp` 下的进程间文件锁让整个数据库测试目录串行运行。
这明确禁止 migration 往返和约束测试并行操作同一 Schema，也能在未来启用 pytest 并行时保持互斥。

Migration 测试在 `finally` 中恢复到 `0002` head。每个数据约束测试使用独立事务；数据库拒绝写入后
立即显式回滚，不继续使用失败状态中的 Session。

MySQL 8.4 Check Constraint 失败码 `3819` 被 PyMySQL 映射为 SQLAlchemy `OperationalError`，而唯一键
和外键失败映射为 `IntegrityError`。测试只接受 `IntegrityError`，或错误码严格等于 `3819` 的
`OperationalError`，不会捕获宽泛异常。

## 数据库与应用层边界

数据库负责主外键、唯一性、受控状态、币种、布尔值、单行时间顺序、金额非负与合计、MRR 行内变化、
支付状态与终态时间一致性。

以下规则保留给后续明确里程碑中的应用事务或数据质量检查：merchant 区间不重叠及稳定属性一致、
subscription 跨事件状态转换、当前字段与最后事件对账、invoice 与 payment 跨表金额对账、输入时间的
时区语义、事件表的权限级 append-only 控制，以及测试标记的全归属链一致性。
