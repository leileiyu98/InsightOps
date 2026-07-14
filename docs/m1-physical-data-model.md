# M1.1A 物理数据模型设计

## 1. 文档状态、目的与边界

本文将 [`m1-logical-data-model.md`](m1-logical-data-model.md) 的 24 个核心表候选转换为
MySQL 8.4 可实施的物理模型，作为后续 Alembic migration、确定性种子数据和 Gold SQL 的
唯一 Schema 设计输入。

- 业务定义：`insightcloud-business-definitions 1.0.0`
- 数据库：MySQL 8.4，InnoDB
- 默认字符集/排序规则：`utf8mb4` / `utf8mb4_0900_ai_ci`
- 业务时区：`America/Los_Angeles`
- 数据库存储时区：UTC
- 币种：仅 USD
- 核心表数量：24
- 当前状态：设计完成；M1.1B 的 9 张企业身份与 SaaS 表已由 Alembic revision `0002` 实施，其余表尚未实施

本文定义字段、类型、约束和索引，但不包含 DDL、SQLAlchemy ORM、Alembic migration、种子数据、
Gold SQL、API 或应用代码。本文不改变冻结业务口径；若发生冲突，以
[`business-definitions-v1.md`](business-definitions-v1.md) 为准。

## 2. 数据库命名规范

### 2.1 表、字段和逻辑简称

- 表名使用单数、完整语义的 `snake_case`，不使用 MySQL 保留字。
- 主外键字段使用被引用实体的完整名称，不使用 `id`、`type`、`status` 以外的无上下文简称。
- 时间字段统一以 `_at` 结尾，业务自然日以 `_date` 结尾。
- 金额字段统一以 `_amount` 结尾，币种字段统一为 `currency_code`。
- 布尔字段以 `is_` 或 `has_` 开头。
- 外部系统标识以 `external_` 开头，来源事件去重键统一为 `source_event_id`。

后续 Gold SQL、Text2SQL 语义层和文档统一使用以下映射：

| 逻辑简称 | 正式表名 | 说明 |
| --- | --- | --- |
| `plan` | `saas_plan_version` | 套餐版本，不使用 `plan` 保留简称 |
| `payment`、`payment_attempt` | `invoice_payment_attempt` | 仅指 SaaS 账单支付尝试 |
| `order` | `commerce_order` | 商城订单 |
| `order_item` | `commerce_order_item` | 商城订单商品明细 |
| `refund` | `commerce_refund` | 商城退款 |
| `refund_allocation` | `refund_item_allocation` | 退款商品金额分配 |
| `channel` | `marketing_channel` | 营销渠道 |
| `campaign` | `marketing_campaign` | 营销活动 |
| `daily_spend` | `campaign_daily_spend` | 活动自然日实际花费 |
| `touch` | `marketing_touch` | 营销触达 |
| SaaS `state_event` | `subscription_state_event` | 订阅状态与 MRR 变化事件 |
| `ticket` | `support_ticket` | 客服工单 |
| 客服 `status_event` | `ticket_status_event` | 工单状态事件 |
| 客服 `interaction` | `ticket_interaction` | 工单交互元数据 |

商城不新增支付表。商城首次支付成功事实由 `commerce_order.first_paid_at` 表达；因此不得在商城
上下文中把 `payment` 错误映射为 `invoice_payment_attempt`。

### 2.2 主键、业务键和外键

- 默认主键为 `<table>_id BIGINT UNSIGNED AUTO_INCREMENT`。
- 内部主键只用于关系连接，不承载外部业务语义，也不得被更新。
- 稳定外部 ID 使用 `VARCHAR(128)`、ASCII 字符集和二进制排序规则，保持大小写敏感。
- 可重放事件同时保留内部主键和唯一 `source_event_id`。
- 外键列与目标主键类型必须完全一致，均为 `BIGINT UNSIGNED`。
- 外键默认 `ON DELETE RESTRICT ON UPDATE RESTRICT`，避免级联删除历史事实。
- 不使用名称、邮箱、金额或时间戳单独作为身份连接键。

`merchant` 是有意设计的例外：`merchant_assignment_id` 是行主键，`merchant_id` 是可跨多个归属区间
重复的稳定商家身份键，详见第 5 节。

### 2.3 约束和索引名称

| 类型 | 命名格式 | 示例 |
| --- | --- | --- |
| 主键 | MySQL 固定名称 `PRIMARY` | `PRIMARY (organization_id)` |
| 外键 | `fk_<child>__<parent>` | `fk_subscription__organization` |
| 唯一约束 | `uq_<table>__<key>` | `uq_subscription__external_id` |
| Check | `ck_<table>__<rule>` | `ck_subscription__period_order` |
| 普通索引 | `ix_<table>__<columns>` | `ix_subscription__org_status` |

MySQL 标识符最长 64 字符。超长名称只允许使用本文表简称缩短，并必须在 migration 中保持确定性，
不得让 Alembic 自动产生随机或不可读名称。

### 2.4 状态、布尔值和测试标记

- 状态字段使用 `VARCHAR(32)` 加 MySQL 8.4 `CHECK`，不使用数据库 `ENUM`。
- 布尔字段使用 `BOOLEAN NOT NULL`；在 MySQL 中物理映射为 `TINYINT(1)`。
- `is_test` 默认 `FALSE`，所有身份、主业务对象和事件事实均显式保存或可沿唯一外键链继承。
- `is_test = FALSE` 只表示本行未标记为测试，不代表上游归属链一定为正式数据。
- 正式指标必须同时检查事实和规定归属链，数据库默认值不能替代全链路测试排除。

## 3. 数据类型与默认值规范

### 3.1 通用数据类型

| 数据 | MySQL 类型 | 规则 |
| --- | --- | --- |
| 内部 ID | `BIGINT UNSIGNED` | 主键自动递增；外键不自动递增 |
| 稳定外部 ID | `VARCHAR(128)` | ASCII、区分大小写；按业务范围唯一 |
| 状态、类型、原因代码 | `VARCHAR(32)` 或 `VARCHAR(64)` | 受控代码必须有 Check 或数据质量字典 |
| 名称、标题 | `VARCHAR(255)` | 使用 `utf8mb4`；禁止承担连接语义 |
| 短说明 | `VARCHAR(500)` | 仅在明确需要时使用；M1 不保存客服正文 |
| 业务时刻 | `DATETIME(6)` | UTC；微秒精度 |
| 业务自然日 | `DATE` | 仅用于已按业务时区确定的日期事实 |
| 数量 | `INT UNSIGNED` | 必须通过 Check 排除零或非法范围 |
| 金额 | `DECIMAL(19,4)` | 精确十进制；禁止 float/double |
| 币种 | `CHAR(3)` | M1 仅允许 `USD` |
| 版本号 | `SMALLINT UNSIGNED` | 从 1 开始 |
| 布尔值 | `BOOLEAN` | 必须 `NOT NULL` 且有明确默认值 |

核心 24 表不使用 JSON。M1 的分析字段必须结构化并可约束；未来只有在存在明确、不可合理列化的
载荷且同时具备 JSON Schema、权限和查询限制时，才可另行设计 JSON 字段。

### 3.2 金额与精度

- 所有权威金额使用 `DECIMAL(19,4)`，包括规范化 MRR、账单组成、商品金额、退款分配、平台服务费和广告花费。
- `FLOAT` 和 `DOUBLE` 禁止用于金额、比率分子分母或持久化业务结果。
- `currency_code` 默认 `USD`，并通过 `CHECK (currency_code = 'USD')` 阻止其他币种进入 M1。
- 缺失必需金额使用 `NULL` 并使事实不合格；不得用默认零掩盖缺失。
- 只有业务上合法的零金额允许保存为 `0.0000`。
- 原始收费、商品金额和退款分配通常要求 `>= 0`；Merchant Net Sales 等允许为负的派生指标不落表。
- 年付金额除以 12 后保留 4 位小数；Gold SQL 聚合前不得先格式化或降为两位小数。

### 3.3 文本、外部 ID 和敏感信息

- 外部 ID 最大 128 字符，禁止保存支付凭证、访问令牌或密钥。
- 代码最大 64 字符；状态和固定类型最大 32 字符。
- 企业名、活动名、商品标题最大 255 字符，使用默认 `utf8mb4_0900_ai_ci` 排序规则。
- 外部 ID、来源事件 ID 和需要确定性决胜的代码使用 ASCII 二进制排序规则。
- M1 不保存客服正文、营销原始载荷、支付卡信息、用户邮箱或电话号码。

### 3.4 默认值

- `is_test`、`is_robot`、`is_spam` 默认 `FALSE`；`is_production` 默认 `TRUE`。
- `currency_code` 默认 `USD`。
- `recorded_at` 默认 `CURRENT_TIMESTAMP(6)`；可变实体的 `updated_at` 默认当前时间并在更新时刷新。
- 业务状态、业务发生时间、金额、外键和外部 ID 不设置推测性默认值。
- 事件表不通过默认值伪造 `occurred_at`、`effective_at` 或成功时间。

## 4. 时间设计

### 4.1 五类时间

| 时间类别 | 字段模式 | 含义 |
| --- | --- | --- |
| 业务发生时间 | `occurred_at`、`first_paid_at`、`succeeded_at` | 真实业务动作发生时刻 |
| 生效时间 | `effective_at`、`assignment_valid_from` | 状态、价格或关系开始产生业务效力的时刻 |
| 记录时间 | `recorded_at`、`received_at`、`processed_at` | 数据进入、接收或处理系统的时刻 |
| 创建时间 | `created_at` | 业务对象在来源系统创建的时刻 |
| 更新时间 | `updated_at` | 当前行最后被合法更新的记录时刻 |

所有 `DATETIME(6)` 值必须在应用边界转换为 UTC，数据库连接建立后必须把 session `time_zone` 固定为
`+00:00`，以保证 `CURRENT_TIMESTAMP(6)` 默认值同样是 UTC。MySQL `DATETIME` 本身不携带时区，因此
写入接口和测试必须拒绝没有时区语义的输入。报表边界先按 `America/Los_Angeles` 解释，再转换为 UTC 左闭右开
参数；不得直接用 UTC 日期代替洛杉矶业务日期。`campaign_daily_spend.business_date` 是已经按业务时区
确定的例外。

### 4.2 指标的权威时间

- **MRR/ARR**：从 `subscription_state_event.effective_at` 之前的最后有效状态和规范化 MRR 重建；
  `as of` 时点本身不包含在未来事件中。MRR 不从账单或支付日期推断。
- **SaaS Revenue**：使用 `invoice_payment_attempt.succeeded_at`，只汇总成功尝试的订阅费用部分。
- **GMV/Order Count/AOV**：使用 `commerce_order.first_paid_at`，并在固定快照截止时间检查订单未取消。
- **Refund Amount**：使用 `commerce_refund.succeeded_at`；不得移回订单支付周期。
- **Platform Transaction Revenue**：使用 `platform_fee_charge.succeeded_at`。
- **168 小时归因**：使用 `marketing_touch.occurred_at` 与权威 `conversion_at` 比较，窗口为
  `[conversion_at - 168 hours, conversion_at]`。同一时刻以区分大小写的 `source_event_id` 确定顺序。
- **产品活跃**：使用 `key_product_event.occurred_at`，滚动窗口为 `[as_of - 30 days, as_of)`。
- **Ticket reopen**：使用 `ticket_status_event.effective_at`。Resolution Time 选择截止时间前最后一次
  使工单保持 solved/closed 且之后没有未解决 reopen 的解决时刻。

迟到数据按原业务时间归期，但只在固定快照截止前已记录的数据中可见。`recorded_at` 只用于快照完整性和
审计，不能替代指标业务时间。

## 5. merchant 建模决策

### 5.1 方案比较

| 维度 | 方案 A：单表 `merchant` | 方案 B：`merchant` + `merchant_organization_assignment` |
| --- | --- | --- |
| 稳定身份 | `merchant_id` 在多个区间行中重复 | `merchant` 一行一个稳定身份 |
| 历史归属 | 每行一个 organization 有效区间 | 独立 assignment 表保存有效区间 |
| 历史准确性 | 可准确表达，但区间不重叠需外部校验 | 表意最清晰，身份与关系各自约束 |
| 查询复杂度 | 事件直接引用 assignment 行，按 `merchant_id` 汇总 | 多一次 assignment 连接 |
| 表数量 | 保持 M1 的 24 张 | 增加到 25 张 |
| Gold Questions | 足以支持事件时归属和 merchant 分组 | 同样支持，长期更易扩展 |
| 维护成本 | 稳定属性可能跨区间重复 | 多一张表和一层 migration 依赖 |

### 5.2 选择与约束

M1 选择 **方案 A**，与逻辑模型已确定的“一行一个归属有效区间”和 24 表范围保持一致：

- `merchant_assignment_id` 是物理行主键。
- `merchant_id` 是稳定商家身份键，由应用分配，不自动递增，可跨区间重复。
- 业务唯一键为 `(merchant_id, assignment_valid_from)`。
- 订单、活动和事件保存发生时命中的 `merchant_assignment_id`，避免查询时猜测历史归属。
- Gold SQL 按稳定 `merchant_id` 汇总商家，按 assignment 行的 `organization_id` 解析事件时归属。
- 同一 `merchant_id` 的区间不得重叠；MySQL 8.4 无排他区间约束，该规则由写入服务、集成测试和
  数据质量任务共同保证。
- 同一 `merchant_id` 各区间的 `external_merchant_id`、测试标记等稳定属性必须一致，由数据质量任务对账。

如果后续出现频繁重新归属、独立 merchant 主数据生命周期或大量不带事件时点的 merchant 外键，必须在
创建首个 production migration 前重新评估方案 B，不得在已上线数据中静默改变 `merchant_id` 语义。

## 6. 24 个核心表总览

| # | 数据域 | 正式表名 | 一行代表什么 |
| ---: | --- | --- | --- |
| 1 | 企业与身份 | `organization` | 一个稳定企业身份 |
| 2 | 企业与身份 | `organization_member` | 一个 organization 成员关系生命周期 |
| 3 | 企业与身份 | `consumer` | 一个商城消费者身份 |
| 4 | 企业与身份 | `merchant` | 一个 merchant 到 organization 的归属有效区间 |
| 5 | SaaS | `saas_plan_version` | 一个 SaaS 套餐版本 |
| 6 | SaaS | `subscription` | 一个 organization 的一次订阅生命周期 |
| 7 | SaaS | `subscription_state_event` | 一个订阅在一个生效时点净额化后的状态/MRR 变化 |
| 8 | SaaS | `subscription_invoice` | 一张订阅账单 |
| 9 | SaaS | `invoice_payment_attempt` | 对一张订阅账单的一次支付尝试 |
| 10 | 商城 | `product` | 一个 merchant 的商品 |
| 11 | 商城 | `commerce_order` | 一笔商城订单 |
| 12 | 商城 | `commerce_order_item` | 订单中的一条商品明细 |
| 13 | 商城 | `commerce_refund` | 一次退款生命周期 |
| 14 | 商城 | `refund_item_allocation` | 一次退款分配到一条订单明细的商品金额 |
| 15 | 商城 | `platform_fee_charge` | 一次平台交易服务费收取尝试 |
| 16 | 营销 | `marketing_channel` | 一个受治理渠道定义 |
| 17 | 营销 | `marketing_campaign` | 一个 organization/merchant 发起的活动 |
| 18 | 营销 | `campaign_daily_spend` | 一个活动在一个业务日的最终实际花费 |
| 19 | 营销 | `marketing_touch` | 一次可识别营销触达 |
| 20 | 营销 | `attributed_conversion` | 一个权威转化的一次 V1 最终归因结果 |
| 21 | 产品使用 | `key_product_event` | 一次去重后的关键产品事件 |
| 22 | 客服 | `support_ticket` | 一张结构化客服工单 |
| 23 | 客服 | `ticket_status_event` | 一次工单状态变化 |
| 24 | 客服 | `ticket_interaction` | 一次结构化工单交互元数据 |

## 7. 企业与身份域物理设计

### 7.1 `organization`

**用途与粒度**：保存购买 SaaS、注册使用产品或经营商城的稳定企业身份；一行一个 organization。

**主键与业务键**：主键 `organization_id`；业务唯一键 `external_organization_id`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `organization_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 内部主键 |
| `external_organization_id` | `VARCHAR(128)` | 否 | 无 | 稳定外部企业 ID |
| `organization_name` | `VARCHAR(255)` | 否 | 无 | 企业显示名，受限信息 |
| `status` | `VARCHAR(32)` | 否 | 无 | `registered/active/suspended/closed` |
| `registered_at` | `DATETIME(6)` | 否 | 无 | 注册 cohort 业务时间 |
| `closed_at` | `DATETIME(6)` | 是 | `NULL` | 企业关闭业务时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 显式测试企业标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 首次记录时间 |
| `updated_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 最后更新时间 |

**约束与索引**：

- 外键：无。
- `uq_organization__external_id (external_organization_id)`。
- `ck_organization__status` 限制状态集合。
- `ck_organization__closed_time`：`closed_at IS NULL OR closed_at >= registered_at`；closed 状态要求关闭时间。
- `ix_organization__test_registered (is_test, registered_at)` 支撑注册 cohort 和测试排除。
- `ix_organization__status (status)` 支撑当前实体筛选。

**策略与覆盖**：名称和外部 ID 属于受限业务信息；不保存地址、联系人或凭证。删除和主键更新均
`RESTRICT`，关闭通过状态与 `closed_at` 表达。支撑 Logo Churn、SaaS 新增付费、Activation Rate、
Active Organization Count 及 organization 级跨域分析。直接支撑 `GQ-SAA-001/002/005/006/008/009`、
`GQ-MKT-001/004/008`、`GQ-PRD-001–008`、`GQ-XDM-002–005/007/008`。

### 7.2 `organization_member`

**用途与粒度**：保存一个 SaaS 成员在一个 organization 中的关系生命周期；不与 consumer 合并。

**主键与业务键**：主键 `organization_member_id`；业务唯一键 `external_membership_id`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `organization_member_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 内部主键 |
| `external_membership_id` | `VARCHAR(128)` | 否 | 无 | 稳定成员关系 ID |
| `organization_id` | `BIGINT UNSIGNED` | 否 | 无 | 所属 organization |
| `external_account_id` | `VARCHAR(128)` | 是 | `NULL` | 外部登录账号引用，个人敏感信息 |
| `status` | `VARCHAR(32)` | 否 | 无 | `invited/active/removed/expired` |
| `first_invited_at` | `DATETIME(6)` | 是 | `NULL` | 首次成功邀请时间 |
| `accepted_at` | `DATETIME(6)` | 是 | `NULL` | 首次接受邀请时间 |
| `effective_from` | `DATETIME(6)` | 否 | 无 | 关系生效时间 |
| `effective_to` | `DATETIME(6)` | 是 | `NULL` | 关系失效时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试成员关系标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 首次记录时间 |
| `updated_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 最后更新时间 |

**外键、约束和索引**：

- `fk_org_member__organization`：`organization_id` → `organization.organization_id`。
- `uq_org_member__external_id (external_membership_id)`。
- `ck_org_member__status` 限制状态集合。
- `ck_org_member__effective_range`：`effective_to IS NULL OR effective_to > effective_from`。
- `ck_org_member__invite_order`：接受时间不得早于邀请时间。
- `ix_org_member__org_effective (organization_id, effective_from, effective_to)` 支撑事件时归属。
- `ix_org_member__org_invited (organization_id, first_invited_at, is_test)` 支撑激活条件。

**策略与覆盖**：`external_account_id` 敏感且不得返回 Gold 明细。关系结束后更新状态和
`effective_to`，不硬删除；首次邀请时间不可覆盖。支撑 Activation Rate、成员触发的企业活跃和身份映射。
直接支撑 `GQ-PRD-001/002/005/006/007/008`、`GQ-XDM-003`。

### 7.3 `consumer`

**用途与粒度**：保存商城消费者业务身份；一行一个稳定 consumer，不与 member 自动合并。

**主键与业务键**：主键 `consumer_id`；业务唯一键 `external_consumer_id`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `consumer_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 内部主键 |
| `external_consumer_id` | `VARCHAR(128)` | 否 | 无 | 稳定消费者 ID |
| `status` | `VARCHAR(32)` | 否 | 无 | `active/blocked/closed` |
| `first_identified_at` | `DATETIME(6)` | 否 | 无 | 首次稳定识别时间 |
| `created_at` | `DATETIME(6)` | 否 | 无 | 消费者身份创建时间 |
| `closed_at` | `DATETIME(6)` | 是 | `NULL` | 关闭时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试消费者标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 首次记录时间 |
| `updated_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 最后更新时间 |

**约束与索引**：

- 外键：无。
- `uq_consumer__external_id (external_consumer_id)`。
- `ck_consumer__status` 限制状态集合。
- `ck_consumer__time_order`：首次识别和关闭时间不得早于创建时间。
- `ix_consumer__test_created (is_test, created_at)`；`ix_consumer__status (status)`。

**策略与覆盖**：不保存邮箱、电话、设备图或跨账号映射。关闭用状态和时间表达，历史订单仍保留。
Commerce 新增付费时间来自首个合格订单而不是本表。支撑 Commerce 新增付费客户、Commerce CAC、
归因和消费者订单分析。直接支撑 `GQ-COM-001`、`GQ-MKT-002/004/008`。

### 7.4 `merchant`

**用途与粒度**：保存 merchant 稳定身份到 organization 的受治理历史归属；一行一个有效区间。

**主键与业务键**：主键 `merchant_assignment_id`；稳定身份键 `merchant_id`；业务唯一键
`(merchant_id, assignment_valid_from)`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `merchant_assignment_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 归属区间行主键 |
| `merchant_id` | `BIGINT UNSIGNED` | 否 | 无 | 跨区间稳定商家身份键 |
| `external_merchant_id` | `VARCHAR(128)` | 否 | 无 | 稳定外部 merchant ID |
| `organization_id` | `BIGINT UNSIGNED` | 否 | 无 | 区间内归属 organization |
| `merchant_name` | `VARCHAR(255)` | 否 | 无 | 商家显示名，受限信息 |
| `status` | `VARCHAR(32)` | 否 | 无 | `pending/approved/active/suspended/closed` |
| `applied_at` | `DATETIME(6)` | 是 | `NULL` | 申请时间 |
| `approved_at` | `DATETIME(6)` | 是 | `NULL` | 审核通过时间 |
| `activated_at` | `DATETIME(6)` | 是 | `NULL` | 启用时间 |
| `closed_at` | `DATETIME(6)` | 是 | `NULL` | 商家关闭时间 |
| `assignment_valid_from` | `DATETIME(6)` | 否 | 无 | organization 归属生效时间 |
| `assignment_valid_to` | `DATETIME(6)` | 是 | `NULL` | organization 归属失效时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 商家身份/归属测试标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 首次记录时间 |
| `updated_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 最后更新时间 |

**外键、约束和索引**：

- `fk_merchant__organization`：`organization_id` → `organization.organization_id`。
- `uq_merchant__identity_start (merchant_id, assignment_valid_from)`。
- `uq_merchant__external_start (external_merchant_id, assignment_valid_from)`。
- `ck_merchant__status` 限制状态；`ck_merchant__assignment_range` 保证结束晚于开始。
- `ix_merchant__identity_range (merchant_id, assignment_valid_from, assignment_valid_to)`。
- `ix_merchant__org_range (organization_id, assignment_valid_from, assignment_valid_to)`。
- 区间不重叠和跨区间稳定属性一致性不由数据库单行约束保证。

**策略与覆盖**：事件发生后不得改写其 `merchant_assignment_id`；归属纠错必须作为受审计的数据修复。
删除 `RESTRICT`，历史区间只允许关闭，不能物理删除。支撑 merchant 级 GMV、退款、平台收入、营销成本、
企业激活和事件时 organization 映射。直接支撑 `GQ-COM-001/003/005/008`、
`GQ-PRD-001/002/005/006/007/008`、`GQ-XDM-002/003/006/007`。

## 8. SaaS 域物理设计

### 8.1 `saas_plan_version`

**用途与粒度**：保存 SaaS 套餐的版本化价格和计费周期；一行一个套餐版本。

**主键与业务键**：主键 `saas_plan_version_id`；业务唯一键 `(plan_code, version_number)`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `saas_plan_version_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 套餐版本主键 |
| `plan_code` | `VARCHAR(64)` | 否 | 无 | 稳定套餐代码 |
| `version_number` | `SMALLINT UNSIGNED` | 否 | 无 | 套餐版本号，从 1 开始 |
| `plan_name` | `VARCHAR(255)` | 否 | 无 | 套餐显示名 |
| `tier_code` | `VARCHAR(64)` | 否 | 无 | 分析层级，如 `enterprise` |
| `billing_interval` | `VARCHAR(32)` | 否 | 无 | `monthly/annual` |
| `recurring_amount` | `DECIMAL(19,4)` | 否 | 无 | 折扣前基准周期费用；事实金额在事件中固化 |
| `currency_code` | `CHAR(3)` | 否 | `USD` | 币种 |
| `status` | `VARCHAR(32)` | 否 | 无 | `draft/active/retired` |
| `effective_from` | `DATETIME(6)` | 否 | 无 | 版本生效时间 |
| `effective_to` | `DATETIME(6)` | 是 | `NULL` | 版本失效时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试套餐标记 |
| `created_at` | `DATETIME(6)` | 否 | 无 | 来源创建时间 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 首次记录时间 |
| `updated_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 最后更新时间 |

**约束与索引**：

- 外键：无。
- `uq_saas_plan_ver__code_version (plan_code, version_number)`。
- Check：版本号大于零、周期仅 monthly/annual、金额非负、币种 USD、状态集合、有效区间有序。
- `ix_saas_plan_ver__tier_effective (tier_code, effective_from, effective_to)`。
- `ix_saas_plan_ver__status (status)`。

**策略与覆盖**：已被订阅事件引用的版本不可改价格或删除；新价格创建新版本。套餐和价格属于受限
商业信息。支撑 MRR/ARR、MRR 变化和套餐分群。直接支撑 `GQ-SAA-001/003/004/005/006/007/008/009`、
`GQ-PRD-005`、`GQ-XDM-004/005/008`。

### 8.2 `subscription`

**用途与粒度**：保存一个 organization 的一次订阅生命周期和当前便利状态；历史指标使用事件表。

**主键与业务键**：主键 `subscription_id`；业务唯一键 `external_subscription_id`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `subscription_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 内部主键 |
| `external_subscription_id` | `VARCHAR(128)` | 否 | 无 | 稳定外部订阅 ID |
| `organization_id` | `BIGINT UNSIGNED` | 否 | 无 | 订阅主体 |
| `current_plan_version_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 当前套餐版本便利引用 |
| `current_status` | `VARCHAR(32)` | 否 | 无 | 当前订阅状态 |
| `created_at` | `DATETIME(6)` | 否 | 无 | 订阅创建业务时间 |
| `first_activated_at` | `DATETIME(6)` | 是 | `NULL` | 首次激活生效时间，不可覆盖 |
| `current_period_started_at` | `DATETIME(6)` | 是 | `NULL` | 当前计费周期开始 |
| `current_period_ends_at` | `DATETIME(6)` | 是 | `NULL` | 当前计费周期结束 |
| `cancel_scheduled_at` | `DATETIME(6)` | 是 | `NULL` | 取消安排时间 |
| `cancellation_effective_at` | `DATETIME(6)` | 是 | `NULL` | 取消生效时间 |
| `expires_at` | `DATETIME(6)` | 是 | `NULL` | 到期时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试订阅标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 首次记录时间 |
| `updated_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 最后更新时间 |

**外键、约束和索引**：

- `fk_subscription__organization`；`fk_subscription__current_plan`。
- `uq_subscription__external_id (external_subscription_id)`。
- `ck_subscription__status`：`pending/trialing/active/paused/cancel_scheduled/cancelled/expired`。
- Check 保证当前周期结束晚于开始、取消生效不早于取消安排、生命周期时间不早于创建。
- `ix_subscription__org_status (organization_id, current_status)`。
- `ix_subscription__plan_status (current_plan_version_id, current_status)`。
- `ix_subscription__cancel_effective (cancellation_effective_at)`。

**策略与覆盖**：当前状态和当前套餐可更新，但不得覆盖状态事件；删除 `RESTRICT`。合同外部 ID、价格关系
属于受限商业信息。支撑全部 SaaS 指标、套餐分群及 organization 首次付费关系。直接支撑
`GQ-SAA-001–009`、`GQ-PRD-005`、`GQ-XDM-001/004/005/008`。

### 8.3 `subscription_state_event`

**用途与粒度**：保存订阅在一个生效时点净额化后的状态或规范化 MRR 变化；事件不可变。

**主键与业务键**：主键 `subscription_state_event_id`；唯一 `source_event_id`，并唯一
`(subscription_id, effective_at)`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `subscription_state_event_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 事件主键 |
| `source_event_id` | `VARCHAR(128)` | 否 | 无 | 稳定来源事件 ID |
| `subscription_id` | `BIGINT UNSIGNED` | 否 | 无 | 所属订阅 |
| `event_type` | `VARCHAR(32)` | 否 | 无 | MRR/状态事件类型 |
| `status_before` | `VARCHAR(32)` | 是 | `NULL` | 生效前状态 |
| `status_after` | `VARCHAR(32)` | 是 | `NULL` | 生效后状态 |
| `plan_version_before_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 生效前套餐版本 |
| `plan_version_after_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 生效后套餐版本 |
| `billing_interval_before` | `VARCHAR(32)` | 是 | `NULL` | 生效前计费周期 |
| `billing_interval_after` | `VARCHAR(32)` | 是 | `NULL` | 生效后计费周期 |
| `recurring_amount_before` | `DECIMAL(19,4)` | 否 | 无 | 生效前折扣后周期费用 |
| `recurring_amount_after` | `DECIMAL(19,4)` | 否 | 无 | 生效后折扣后周期费用 |
| `normalized_mrr_before` | `DECIMAL(19,4)` | 否 | 无 | 生效前规范化 MRR |
| `normalized_mrr_after` | `DECIMAL(19,4)` | 否 | 无 | 生效后规范化 MRR |
| `currency_code` | `CHAR(3)` | 否 | `USD` | 币种 |
| `effective_at` | `DATETIME(6)` | 否 | 无 | 状态/MRR 业务生效时间 |
| `created_at` | `DATETIME(6)` | 否 | 无 | 来源事件创建时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试事件标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 记录时间和快照可见时间 |

**外键、约束和索引**：

- 外键到 `subscription`、生效前/后 `saas_plan_version`。
- `uq_sub_state_event__source_id (source_event_id)`。
- `uq_sub_state_event__sub_effective (subscription_id, effective_at)` 保证同一时点先净额化为一行。
- `event_type` 限制为 `first_activation/expansion/contraction/pause/resume/cancellation_effective/expiration`。
- 状态和计费周期使用与主表一致的受控集合；金额非负；币种仅 USD。
- 行内 Check 验证 expansion 的 MRR 增加、contraction 的 MRR 减少且 after 大于零、取消/到期的
  `normalized_mrr_after = 0`。复杂合法状态转换仍由应用校验。
- `ix_sub_state_event__type_effective (event_type, effective_at)`。
- `ix_sub_state_event__before_plan (plan_version_before_id)`。
- `ix_sub_state_event__after_plan_time (plan_version_after_id, effective_at)`。

**策略与覆盖**：事件 append-only；纠错使用受审计的替换流程，不原地改变业务时间或金额。金额为受限
商业信息。支撑 MRR、ARR、New/Expansion/Contraction/Churned MRR、Logo 和 Revenue Churn。
直接支撑 `GQ-SAA-001/003–009`、`GQ-XDM-004/005`。

### 8.4 `subscription_invoice`

**用途与粒度**：保存一张订阅账单及当前账单状态；账单生成不代表收入。

**主键与业务键**：主键 `subscription_invoice_id`；业务唯一键 `external_invoice_id`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `subscription_invoice_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 账单主键 |
| `external_invoice_id` | `VARCHAR(128)` | 否 | 无 | 稳定外部账单 ID |
| `subscription_id` | `BIGINT UNSIGNED` | 否 | 无 | 所属订阅 |
| `status` | `VARCHAR(32)` | 否 | 无 | `draft/open/paid/void/uncollectible` |
| `subscription_fee_amount` | `DECIMAL(19,4)` | 否 | 无 | 折扣后不含税订阅费用 |
| `tax_amount` | `DECIMAL(19,4)` | 否 | 无 | 税费 |
| `one_time_amount` | `DECIMAL(19,4)` | 否 | 无 | 一次性费用 |
| `total_amount` | `DECIMAL(19,4)` | 否 | 无 | 三项金额合计 |
| `currency_code` | `CHAR(3)` | 否 | `USD` | 币种 |
| `issued_at` | `DATETIME(6)` | 是 | `NULL` | 正式开账时间 |
| `due_at` | `DATETIME(6)` | 是 | `NULL` | 到期时间 |
| `voided_at` | `DATETIME(6)` | 是 | `NULL` | 作废时间 |
| `paid_at` | `DATETIME(6)` | 是 | `NULL` | 当前派生的最终支付完成时间 |
| `created_at` | `DATETIME(6)` | 否 | 无 | 账单创建时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试账单标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 首次记录时间 |
| `updated_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 最后更新时间 |

**外键、约束和索引**：

- `fk_subscription_invoice__subscription`。
- `uq_subscription_invoice__external_id (external_invoice_id)`。
- Check：状态集合、各金额非负、`total_amount = subscription_fee_amount + tax_amount + one_time_amount`、
  币种 USD、到期不早于开账、状态与 voided/paid 时间一致。
- `ix_subscription_invoice__sub_issued (subscription_id, issued_at)`。
- `ix_subscription_invoice__status_due (status, due_at)`。

**策略与覆盖**：金额和外部账单号为受限信息。状态可更新，金额在产生支付尝试后不得静默修改；账单不
物理删除。为 SaaS Revenue 提供账单范围，收入仍来自支付尝试。直接支撑 `GQ-SAA-002`。

### 8.5 `invoice_payment_attempt`

**用途与粒度**：保存对订阅账单的一次支付尝试；成功、失败和取消尝试均保留。

**主键与业务键**：主键 `invoice_payment_attempt_id`；业务唯一键 `external_payment_attempt_id`；
`provider_transaction_id` 在非空时唯一。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `invoice_payment_attempt_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 支付尝试主键 |
| `external_payment_attempt_id` | `VARCHAR(128)` | 否 | 无 | 稳定尝试 ID/回调去重键 |
| `provider_transaction_id` | `VARCHAR(128)` | 是 | `NULL` | 支付提供商交易 ID，不是凭证 |
| `subscription_invoice_id` | `BIGINT UNSIGNED` | 否 | 无 | 所属账单 |
| `status` | `VARCHAR(32)` | 否 | 无 | `pending/succeeded/failed/cancelled` |
| `subscription_fee_amount` | `DECIMAL(19,4)` | 否 | 无 | 成功时计入 SaaS Revenue 的部分 |
| `tax_amount` | `DECIMAL(19,4)` | 否 | 无 | 税费 |
| `one_time_amount` | `DECIMAL(19,4)` | 否 | 无 | 一次性费用 |
| `total_amount` | `DECIMAL(19,4)` | 否 | 无 | 支付尝试总额 |
| `currency_code` | `CHAR(3)` | 否 | `USD` | 币种 |
| `attempted_at` | `DATETIME(6)` | 否 | 无 | 尝试发生时间 |
| `succeeded_at` | `DATETIME(6)` | 是 | `NULL` | 支付成功时间，SaaS Revenue 权威时间 |
| `failed_at` | `DATETIME(6)` | 是 | `NULL` | 支付失败时间 |
| `cancelled_at` | `DATETIME(6)` | 是 | `NULL` | 取消时间 |
| `failure_code` | `VARCHAR(64)` | 是 | `NULL` | 受控失败原因，不保存提供商原文 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试支付尝试标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 记录/快照可见时间 |

**外键、约束和索引**：

- `fk_invoice_payment__invoice`：到账单。
- 唯一约束分别覆盖 external attempt ID 和非空 provider transaction ID。
- Check：状态集合、金额非负、金额合计、币种 USD；succeeded/failed/cancelled 状态必须且只能有对应
  终态时间，终态时间不得早于 `attempted_at`。
- `ix_invoice_payment__invoice_status (subscription_invoice_id, status)`。
- `ix_invoice_payment__status_success (status, succeeded_at)` 支撑收入周期。

**策略与覆盖**：事件 append-only，失败重试创建新行；重复回调复用稳定业务键。提供商 ID 和金额为高敏
受限信息，不保存支付凭证。支撑 SaaS Revenue、SaaS 新增付费、SaaS CAC/ROAS 和归因收入。
直接支撑 `GQ-SAA-002/007`、`GQ-MKT-001/003/004/005/006/007/008`、`GQ-PRD-008`、
`GQ-XDM-001/003`。

## 9. 商城域物理设计

### 9.1 `product`

**用途与粒度**：保存一个 merchant 的商品当前实体；一行一个稳定商品。

**主键与业务键**：主键 `product_id`；业务唯一键 `external_product_id`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `product_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 商品主键 |
| `external_product_id` | `VARCHAR(128)` | 否 | 无 | 稳定外部商品 ID |
| `merchant_assignment_id` | `BIGINT UNSIGNED` | 否 | 无 | 商品创建时有效的 merchant 归属行 |
| `product_title` | `VARCHAR(255)` | 否 | 无 | 商品标题 |
| `category_code` | `VARCHAR(64)` | 否 | 无 | M1 受控商品类别代码 |
| `status` | `VARCHAR(32)` | 否 | 无 | `draft/active/inactive/archived` |
| `created_at` | `DATETIME(6)` | 否 | 无 | 商品创建时间 |
| `first_published_at` | `DATETIME(6)` | 是 | `NULL` | 首次发布时间，不可覆盖 |
| `archived_at` | `DATETIME(6)` | 是 | `NULL` | 归档时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试商品标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 首次记录时间 |
| `updated_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 最后更新时间 |

**外键、约束和索引**：

- `fk_product__merchant_assignment`：到 `merchant.merchant_assignment_id`。
- `uq_product__external_id (external_product_id)`。
- Check：状态集合；首次发布和归档不得早于创建，archived 状态要求 `archived_at`。
- `ix_product__merchant_status (merchant_assignment_id, status)`。
- `ix_product__category_status (category_code, status)`。

**策略与覆盖**：标题通常非敏感，但购买关系属于敏感交易信息。商品状态和标题可更新，首次发布时间不可
覆盖；有订单引用后不得删除。`merchant_assignment_id` 仅表示商品创建时归属，订单和产品事件必须保存
各自发生时的 assignment。为防商品后续改类改变历史结果，订单明细保存购买时类别快照。支撑商品/类别
GMV、退款和商品发布行为。直接支撑 `GQ-COM-001/006`、`GQ-XDM-006`。

### 9.2 `commerce_order`

**用途与粒度**：保存一笔商城订单及固定快照中的当前状态和关键不可覆盖时刻。

**主键与业务键**：主键 `commerce_order_id`；业务唯一键 `external_order_id`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `commerce_order_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 订单主键 |
| `external_order_id` | `VARCHAR(128)` | 否 | 无 | 稳定外部订单 ID |
| `consumer_id` | `BIGINT UNSIGNED` | 否 | 无 | 下单消费者 |
| `merchant_assignment_id` | `BIGINT UNSIGNED` | 否 | 无 | 下单/支付业务时有效的 merchant 归属 |
| `status` | `VARCHAR(32)` | 否 | 无 | 订单当前状态 |
| `currency_code` | `CHAR(3)` | 否 | `USD` | 币种 |
| `created_at` | `DATETIME(6)` | 否 | 无 | 订单创建时间 |
| `first_paid_at` | `DATETIME(6)` | 是 | `NULL` | 首次支付成功时间，GMV 权威时间 |
| `fulfilled_at` | `DATETIME(6)` | 是 | `NULL` | 履约时间 |
| `completed_at` | `DATETIME(6)` | 是 | `NULL` | 完成时间，激活第三条件使用 |
| `cancelled_at` | `DATETIME(6)` | 是 | `NULL` | 取消时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试订单标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 记录/快照可见时间 |
| `updated_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 当前状态最后更新时间 |

**外键、约束和索引**：

- 外键到 `consumer` 和 `merchant.merchant_assignment_id`。
- `uq_commerce_order__external_id (external_order_id)`。
- 状态集合：`created/payment_pending/paid/fulfilled/completed/cancelled`。
- Check：币种 USD；支付、履约、完成、取消时间不早于创建；fulfilled/completed 必须有支付时间；
  completed 要求完成时间，cancelled 要求取消时间。
- `ix_commerce_order__paid_status (first_paid_at, status, is_test)` 支撑 GMV 周期和取消过滤。
- `ix_commerce_order__merchant_paid (merchant_assignment_id, first_paid_at)`。
- `ix_commerce_order__consumer_paid (consumer_id, first_paid_at)` 支撑首次付费。
- `ix_commerce_order__completed (completed_at, status)` 支撑激活条件。

**策略与覆盖**：外部订单 ID 和购买关系属于敏感交易信息。当前状态可更新，但首次支付和完成时间不可
覆盖；取消可使固定快照重算历史 GMV。删除 `RESTRICT`。支撑 GMV、Order Count、AOV、Merchant Net
Sales、Commerce 新增付费和企业激活。直接支撑 `GQ-COM-001–008`、`GQ-MKT-002/004/005/008`、
`GQ-PRD-001/005/006/007/008`、`GQ-XDM-001/003/006/007`。

### 9.3 `commerce_order_item`

**用途与粒度**：保存订单的一条商品明细和购买时类别快照；商品金额是 GMV 权威基础事实。

**主键与业务键**：主键 `commerce_order_item_id`；业务唯一键 `(commerce_order_id, external_order_item_id)`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `commerce_order_item_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 订单明细主键 |
| `external_order_item_id` | `VARCHAR(128)` | 否 | 无 | 订单范围内稳定外部明细 ID |
| `commerce_order_id` | `BIGINT UNSIGNED` | 否 | 无 | 所属订单 |
| `product_id` | `BIGINT UNSIGNED` | 否 | 无 | 商品引用 |
| `product_category_code` | `VARCHAR(64)` | 否 | 无 | 购买时类别快照 |
| `quantity` | `INT UNSIGNED` | 否 | 无 | 购买数量，大于零 |
| `discounted_item_amount` | `DECIMAL(19,4)` | 否 | 无 | 该明细折扣后商品总额，不含税运费 |
| `currency_code` | `CHAR(3)` | 否 | `USD` | 币种 |
| `created_at` | `DATETIME(6)` | 否 | 无 | 明细创建时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试明细标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 记录时间 |

**外键、约束和索引**：

- 外键到 `commerce_order` 和 `product`。
- `uq_order_item__order_external (commerce_order_id, external_order_item_id)`。
- Check：`quantity > 0`、金额非负、币种 USD。
- `ix_order_item__order (commerce_order_id)`；`ix_order_item__product (product_id)`。
- `ix_order_item__category_order (product_category_code, commerce_order_id)` 支撑类别聚合。

**策略与覆盖**：本表无独立状态枚举，合格性继承订单状态。交易明细敏感；创建后 append-only，纠错需
受审计，不随商品当前类别变化。支撑 GMV、
AOV、Merchant Net Sales、商品类别退款分析。直接支撑 `GQ-COM-001–006/008`、
`GQ-XDM-006/007`。

### 9.4 `commerce_refund`

**用途与粒度**：保存一次商城退款生命周期；成功完成形成独立反向事件。

**主键与业务键**：主键 `commerce_refund_id`；业务唯一键 `external_refund_id`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `commerce_refund_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 退款主键 |
| `external_refund_id` | `VARCHAR(128)` | 否 | 无 | 稳定外部退款 ID |
| `commerce_order_id` | `BIGINT UNSIGNED` | 否 | 无 | 被退款订单 |
| `status` | `VARCHAR(32)` | 否 | 无 | `requested/pending/succeeded/failed/cancelled` |
| `item_refund_amount` | `DECIMAL(19,4)` | 否 | 无 | 商品金额退款，指标权威金额 |
| `tax_refund_amount` | `DECIMAL(19,4)` | 否 | 无 | 退税金额，不计入指标 |
| `shipping_refund_amount` | `DECIMAL(19,4)` | 否 | 无 | 退运费，不计入指标 |
| `total_refund_amount` | `DECIMAL(19,4)` | 否 | 无 | 三项金额合计 |
| `currency_code` | `CHAR(3)` | 否 | `USD` | 币种 |
| `reason_code` | `VARCHAR(64)` | 是 | `NULL` | 受控退款原因，不保存正文 |
| `requested_at` | `DATETIME(6)` | 否 | 无 | 申请时间 |
| `processed_at` | `DATETIME(6)` | 是 | `NULL` | 开始/完成处理记录时间 |
| `succeeded_at` | `DATETIME(6)` | 是 | `NULL` | 成功完成时间，Refund 权威时间 |
| `failed_at` | `DATETIME(6)` | 是 | `NULL` | 失败时间 |
| `cancelled_at` | `DATETIME(6)` | 是 | `NULL` | 取消时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试退款标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 快照可见时间 |
| `updated_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 状态更新时间 |

**外键、约束和索引**：

- `fk_commerce_refund__order`。
- `uq_commerce_refund__external_id (external_refund_id)`。
- Check：状态集合、四项金额非负、总额等于组成合计、币种 USD；终态与对应时间一致且不早于申请。
- `ix_commerce_refund__status_success (status, succeeded_at)`。
- `ix_commerce_refund__order (commerce_order_id)`。

**策略与覆盖**：金额和原因代码受限；状态可推进，成功后关键金额和成功时间不可静默修改。失败和待处理
不进入 Refund Amount。支撑 Refund Amount、Refund Rate 和 Merchant Net Sales。直接支撑
`GQ-COM-002/003/005/006/007/008`、`GQ-XDM-006/007`。

### 9.5 `refund_item_allocation`

**用途与粒度**：保存一次退款分配到一条订单商品明细的商品金额；不含税费和运费。

**主键与业务键**：主键 `refund_item_allocation_id`；唯一 `external_refund_allocation_id`，并唯一
`(commerce_refund_id, commerce_order_item_id)`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `refund_item_allocation_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 分配主键 |
| `external_refund_allocation_id` | `VARCHAR(128)` | 否 | 无 | 稳定外部分配 ID |
| `commerce_refund_id` | `BIGINT UNSIGNED` | 否 | 无 | 所属退款 |
| `commerce_order_item_id` | `BIGINT UNSIGNED` | 否 | 无 | 被分配订单明细 |
| `allocated_item_amount` | `DECIMAL(19,4)` | 否 | 无 | 分配的商品退款金额 |
| `currency_code` | `CHAR(3)` | 否 | `USD` | 币种 |
| `created_at` | `DATETIME(6)` | 否 | 无 | 分配创建时间 |
| `corrected_at` | `DATETIME(6)` | 是 | `NULL` | 受审计更正时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试分配标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 记录时间 |
| `updated_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 更正后的更新时间 |

**外键、约束和索引**：

- 外键到 `commerce_refund` 和 `commerce_order_item`。
- 唯一约束覆盖外部 ID 及 refund/item 组合。
- Check：分配金额非负、币种 USD、更正时间不早于创建。
- `ix_refund_alloc__refund (commerce_refund_id)`。
- `ix_refund_alloc__order_item (commerce_order_item_id)`。

**策略与覆盖**：本表无独立状态枚举，指标资格继承 refund 的 succeeded 状态。金额敏感。成功退款的
分配合计必须等于 `commerce_refund.item_refund_amount`，且明细必须
属于被退款订单；两项是跨行/跨表规则，由应用事务、集成测试和数据质量任务保证。支撑 Refund Amount、
Refund Rate、Merchant Net Sales 和类别退款。直接支撑 `GQ-COM-002/003/005/006/008`、
`GQ-XDM-006/007`。

### 9.6 `platform_fee_charge`

**用途与粒度**：保存平台针对订单的一次交易服务费收取尝试；成功事实形成 Commerce Revenue。

**主键与业务键**：主键 `platform_fee_charge_id`；业务唯一键 `external_fee_charge_id`；非空
`provider_charge_id` 唯一。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `platform_fee_charge_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 收费尝试主键 |
| `external_fee_charge_id` | `VARCHAR(128)` | 否 | 无 | 稳定收费 ID |
| `provider_charge_id` | `VARCHAR(128)` | 是 | `NULL` | 提供商收费 ID，不是凭证 |
| `commerce_order_id` | `BIGINT UNSIGNED` | 否 | 无 | 对应订单 |
| `status` | `VARCHAR(32)` | 否 | 无 | `pending/succeeded/failed/cancelled` |
| `fee_amount` | `DECIMAL(19,4)` | 否 | 无 | 平台交易服务费金额 |
| `currency_code` | `CHAR(3)` | 否 | `USD` | 币种 |
| `attempted_at` | `DATETIME(6)` | 否 | 无 | 收费尝试时间 |
| `succeeded_at` | `DATETIME(6)` | 是 | `NULL` | 收费成功时间，收入权威时间 |
| `failed_at` | `DATETIME(6)` | 是 | `NULL` | 失败时间 |
| `cancelled_at` | `DATETIME(6)` | 是 | `NULL` | 取消时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试收费标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 记录时间 |

**外键、约束和索引**：

- `fk_platform_fee__order`。
- 唯一约束覆盖 external ID 和非空 provider ID。
- Check：状态集合、金额非负、币种 USD；终态与对应时间一致且不早于尝试。
- `ix_platform_fee__status_success (status, succeeded_at)`。
- `ix_platform_fee__order (commerce_order_id)`。

**策略与覆盖**：事件 append-only；重试创建新行，只有稳定去重后的 succeeded 行进入收入。不实现服务费
退回。金额和提供商 ID 受限。支撑 Platform Transaction Revenue、Commerce Revenue 和 Commerce
ROAS。直接支撑 `GQ-COM-005/008`、`GQ-MKT-003/006/007/008`、`GQ-XDM-001/002`。

## 10. 营销域物理设计

### 10.1 `marketing_channel`

**用途与粒度**：保存一个受治理渠道定义及其有效期；`direct` 是渠道类型，unknown 不是渠道行。

**主键与业务键**：主键 `marketing_channel_id`；业务唯一键 `channel_code`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `marketing_channel_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 渠道主键 |
| `channel_code` | `VARCHAR(64)` | 否 | 无 | 稳定渠道代码 |
| `channel_name` | `VARCHAR(255)` | 否 | 无 | 渠道显示名 |
| `channel_type` | `VARCHAR(32)` | 否 | 无 | `paid/organic/referral/direct` |
| `status` | `VARCHAR(32)` | 否 | 无 | `active/inactive` |
| `effective_from` | `DATETIME(6)` | 否 | 无 | 定义生效时间 |
| `effective_to` | `DATETIME(6)` | 是 | `NULL` | 定义失效时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试渠道标记 |
| `created_at` | `DATETIME(6)` | 否 | 无 | 定义创建时间 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 记录时间 |
| `updated_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 更新时间 |

**约束与索引**：

- 外键：无。
- `uq_marketing_channel__code (channel_code)`。
- Check：channel type、状态和有效区间；`channel_type = 'direct'` 的渠道代码必须使用治理的 direct 代码。
- `ix_marketing_channel__type_status (channel_type, status)`。
- `ix_marketing_channel__effective (effective_from, effective_to)`。

**策略与覆盖**：渠道定义通常非敏感；已被事实引用后不可删除或改变历史语义，变更语义需新定义版本
决策。unknown/unattributed 只保存在归因结果中。支撑 CAC、ROAS、Attributed Revenue 和渠道趋势。
直接支撑 `GQ-MKT-001–008`、`GQ-PRD-008`、`GQ-XDM-002/003`。

### 10.2 `marketing_campaign`

**用途与粒度**：保存 organization 或 merchant 发起的一项营销活动；预算不作为实际花费事实。

**主键与业务键**：主键 `marketing_campaign_id`；业务唯一键 `external_campaign_id`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `marketing_campaign_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 活动主键 |
| `external_campaign_id` | `VARCHAR(128)` | 否 | 无 | 稳定外部活动 ID |
| `organization_id` | `BIGINT UNSIGNED` | 否 | 无 | 活动主要归属 organization |
| `merchant_assignment_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 商城活动发生时 merchant 归属 |
| `primary_channel_id` | `BIGINT UNSIGNED` | 否 | 无 | 主要营销渠道 |
| `campaign_name` | `VARCHAR(255)` | 否 | 无 | 活动名称，受限信息 |
| `status` | `VARCHAR(32)` | 否 | 无 | `draft/active/paused/completed/cancelled` |
| `created_at` | `DATETIME(6)` | 否 | 无 | 活动创建时间，激活条件使用 |
| `started_at` | `DATETIME(6)` | 是 | `NULL` | 开始投放时间 |
| `ended_at` | `DATETIME(6)` | 是 | `NULL` | 结束时间 |
| `status_updated_at` | `DATETIME(6)` | 否 | 无 | 当前状态更新时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试活动标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 记录时间 |
| `updated_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 行更新时间 |

**外键、约束和索引**：

- 外键到 `organization`、可选 `merchant` assignment 和 `marketing_channel`。
- `uq_marketing_campaign__external_id (external_campaign_id)`。
- Check：状态集合；结束晚于开始；状态更新时间不早于创建。
- `ix_marketing_campaign__channel_created (primary_channel_id, created_at)`。
- `ix_marketing_campaign__org_created (organization_id, created_at, is_test)` 支撑企业激活。
- `ix_marketing_campaign__merchant_created (merchant_assignment_id, created_at)`。

**策略与覆盖**：名称、投放关系属于受限信息。活动状态可更新，创建时间不可覆盖；删除 `RESTRICT`。
若 merchant assignment 非空，其 organization 必须等于 `organization_id`，由应用和数据质量校验。
支撑 Activation Rate、CAC、ROAS、Attributed Revenue 和活动效率。直接支撑
`GQ-MKT-001/002/005/006/007`、`GQ-PRD-001/005/006/007/008`、`GQ-XDM-002/003/007`。

### 10.3 `campaign_daily_spend`

**用途与粒度**：保存一个活动在一个洛杉矶业务自然日的最终实际广告花费；更正更新同一业务行。

**主键与业务键**：主键 `campaign_daily_spend_id`；业务唯一键 `(marketing_campaign_id, business_date)`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `campaign_daily_spend_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 花费主键 |
| `marketing_campaign_id` | `BIGINT UNSIGNED` | 否 | 无 | 所属活动 |
| `business_date` | `DATE` | 否 | 无 | `America/Los_Angeles` 业务日期 |
| `status` | `VARCHAR(32)` | 否 | 无 | `provisional/confirmed/corrected` |
| `spend_amount` | `DECIMAL(19,4)` | 否 | 无 | 当日最终实际花费 |
| `currency_code` | `CHAR(3)` | 否 | `USD` | 币种 |
| `confirmed_at` | `DATETIME(6)` | 是 | `NULL` | 花费确认 UTC 时刻 |
| `corrected_at` | `DATETIME(6)` | 是 | `NULL` | 最近更正 UTC 时刻 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试花费标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 首次记录时间 |
| `updated_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 最终值更新时间 |

**外键、约束和索引**：

- `fk_campaign_spend__campaign`。
- `uq_campaign_spend__campaign_date (marketing_campaign_id, business_date)`。
- Check：状态集合、花费非负、币种 USD；confirmed/corrected 要求确认时间，corrected 要求更正时间。
- `ix_campaign_spend__date_status (business_date, status, is_test)`。
- `ix_campaign_spend__campaign_date (marketing_campaign_id, business_date)`。

**策略与覆盖**：花费为受限商业信息。provisional 行不进入正式指标；corrected 行保存最终值而不是与原值
相加。更正需要审计，删除 `RESTRICT`。支撑实际花费、CAC、ROAS 和趋势。直接支撑
`GQ-MKT-001/002/005/006/007`、`GQ-XDM-002/007`。

### 10.4 `marketing_touch`

**用途与粒度**：保存一次已去重且可解析到一个业务主体的营销接触。

**主键与业务键**：主键 `marketing_touch_id`；业务唯一键 `source_event_id`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `marketing_touch_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 触达主键 |
| `source_event_id` | `VARCHAR(128)` | 否 | 无 | 来源事件 ID，同时间决胜键 |
| `marketing_channel_id` | `BIGINT UNSIGNED` | 否 | 无 | 触达渠道 |
| `marketing_campaign_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 可选活动 |
| `organization_id` | `BIGINT UNSIGNED` | 是 | `NULL` | SaaS 归因主体 |
| `consumer_id` | `BIGINT UNSIGNED` | 是 | `NULL` | Commerce 归因主体 |
| `touch_type` | `VARCHAR(32)` | 否 | 无 | `non_direct/direct` |
| `quality_status` | `VARCHAR(32)` | 否 | 无 | `accepted/rejected` |
| `occurred_at` | `DATETIME(6)` | 否 | 无 | 真实触达时间，归因窗口使用 |
| `received_at` | `DATETIME(6)` | 否 | 无 | 接收时间 |
| `processed_at` | `DATETIME(6)` | 是 | `NULL` | 处理完成时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试触达标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 记录时间 |

**外键、约束和索引**：

- 外键到 channel、可选 campaign、organization 和 consumer。
- `uq_marketing_touch__source_id (source_event_id)`。
- Check：organization 与 consumer 恰好一个非空；touch type 和质量状态集合；接收/处理不得早于发生。
- direct touch 必须引用 direct 类型 channel；non-direct 不得引用 direct channel，此跨表规则由应用校验。
- `ix_marketing_touch__org_time (organization_id, occurred_at, source_event_id)`。
- `ix_marketing_touch__consumer_time (consumer_id, occurred_at, source_event_id)`。
- `ix_marketing_touch__channel_time (marketing_channel_id, occurred_at)`。
- `ix_marketing_touch__campaign_time (marketing_campaign_id, occurred_at)`。

**策略与覆盖**：事件 append-only，rejected 行保留用于质量审计但不参与归因。不保存设备原始标识和原始
载荷；身份连接属于敏感信息。支撑 168 小时最后非直接触达、渠道分布和转化漏斗。直接支撑
`GQ-MKT-003/004/008`、`GQ-XDM-003`。

### 10.5 `attributed_conversion`

**用途与粒度**：保存一个权威业务转化在 `last_non_direct_168h_v1` 下的唯一最终归因结果。

**主键与业务键**：主键 `attributed_conversion_id`。业务唯一性由 conversion type 和对应权威事实外键
共同保证，不使用无法声明外键的自由多态字符串。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `attributed_conversion_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 归因主键 |
| `conversion_type` | `VARCHAR(32)` | 否 | 无 | 五种受控转化类型 |
| `organization_id` | `BIGINT UNSIGNED` | 是 | `NULL` | SaaS 转化主体 |
| `consumer_id` | `BIGINT UNSIGNED` | 是 | `NULL` | Commerce 转化主体 |
| `invoice_payment_attempt_id` | `BIGINT UNSIGNED` | 是 | `NULL` | SaaS 首付或 Revenue 权威事实 |
| `commerce_order_id` | `BIGINT UNSIGNED` | 是 | `NULL` | Commerce 首付或归因 GMV 权威事实 |
| `platform_fee_charge_id` | `BIGINT UNSIGNED` | 是 | `NULL` | Commerce Revenue 权威事实 |
| `marketing_touch_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 被选中的非 direct 触达 |
| `marketing_channel_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 最终渠道；unknown 时为空 |
| `marketing_campaign_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 最终活动；可为空 |
| `attribution_result` | `VARCHAR(32)` | 否 | 无 | `non_direct/direct/unknown_unattributed` |
| `attribution_reason_code` | `VARCHAR(64)` | 否 | 无 | 决策原因代码 |
| `model_version` | `VARCHAR(64)` | 否 | `last_non_direct_168h_v1` | 归因模型版本 |
| `conversion_at` | `DATETIME(6)` | 否 | 无 | 权威事实转化时间 |
| `window_started_at` | `DATETIME(6)` | 否 | 无 | `conversion_at - 168 hours` |
| `history_complete` | `BOOLEAN` | 否 | 无 | 归因窗口历史是否完整 |
| `attributed_at` | `DATETIME(6)` | 否 | 无 | 归因计算时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试归因结果标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 记录/版本可见时间 |

**外键、约束和索引**：

- 显式外键到 organization、consumer、payment attempt、order、fee charge、touch、channel 和 campaign。
- 三个唯一约束分别为 `(conversion_type, invoice_payment_attempt_id, model_version)`、
  `(conversion_type, commerce_order_id, model_version)`、
  `(conversion_type, platform_fee_charge_id, model_version)`；MySQL 允许其他行的 NULL，不影响各自事实
  在同一模型版本内的唯一性。M1 Gold SQL 必须显式筛选 `last_non_direct_168h_v1`。
- `conversion_type`：`saas_first_payment/saas_revenue/commerce_first_payment/commerce_revenue/attributed_gmv`。
- Check 要求三个权威事实外键恰好一个非空，并与 conversion type 匹配；SaaS 类型要求 organization 且
  consumer 为空，Commerce 类型相反。
- non-direct 要求 touch 和 channel 非空；direct 要求 touch 为空且 channel 指向 direct；unknown 要求
  touch/channel/campaign 为空并有数据不完整原因。跨表 channel 类型由应用校验。
- `window_started_at = conversion_at - INTERVAL 168 HOUR`；direct 要求 `history_complete = TRUE`，
  history 不完整必须为 unknown。
- `ix_attr_conversion__type_time (conversion_type, conversion_at)`。
- `ix_attr_conversion__channel_time (marketing_channel_id, conversion_at)`。
- `ix_attr_conversion__result_time (attribution_result, conversion_at)`。
- `ix_attr_conversion__org_type_time (organization_id, conversion_type, conversion_at)`。
- `ix_attr_conversion__consumer_type_time (consumer_id, conversion_type, conversion_at)`。
- `ix_attr_conversion__payment (invoice_payment_attempt_id)`。
- `ix_attr_conversion__order (commerce_order_id)`。
- `ix_attr_conversion__fee (platform_fee_charge_id)`。
- `ix_attr_conversion__touch (marketing_touch_id)`。
- `ix_attr_conversion__campaign (marketing_campaign_id)`。

**策略与覆盖**：归因结果是版本化派生事实；同一权威事实和模型版本的重复计算必须幂等，结果变化需先
定义替换和有效结果规则。M1 查询只使用一个 V1 最终版本，不实现多触点。身份连接和收入关联敏感。支撑 CAC、ROAS、
Attributed Revenue、新增付费客户和未归因披露。直接支撑 `GQ-MKT-001–008`、`GQ-PRD-005/008`、
`GQ-XDM-002/003`。

## 11. 产品使用域物理设计

### 11.1 `key_product_event`

**用途与粒度**：保存一次去重后的合格或被拒绝关键产品事件；一行只能归属一个 organization。

**主键与业务键**：主键 `key_product_event_id`；业务唯一键 `source_event_id`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `key_product_event_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 事件主键 |
| `source_event_id` | `VARCHAR(128)` | 否 | 无 | 稳定来源事件 ID |
| `organization_id` | `BIGINT UNSIGNED` | 否 | 无 | 唯一分析归属 organization |
| `organization_member_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 可选成员 actor |
| `merchant_assignment_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 可选事件时 merchant 归属 |
| `marketing_campaign_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 可选活动来源对象 |
| `product_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 可选商品来源对象 |
| `commerce_order_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 可选订单来源对象 |
| `event_name` | `VARCHAR(64)` | 否 | 无 | V1 受控关键事件名 |
| `event_version` | `SMALLINT UNSIGNED` | 否 | 无 | 事件定义版本，从 1 开始 |
| `quality_status` | `VARCHAR(32)` | 否 | 无 | `accepted/rejected` |
| `is_robot` | `BOOLEAN` | 否 | `FALSE` | 机器人事件标记 |
| `occurred_at` | `DATETIME(6)` | 否 | 无 | 业务发生时间，活跃/趋势使用 |
| `received_at` | `DATETIME(6)` | 否 | 无 | 事件接收时间 |
| `processed_at` | `DATETIME(6)` | 是 | `NULL` | 处理完成时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试事件标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 记录时间 |

**外键、约束和索引**：

- 外键到 organization、member、merchant assignment、campaign、product 和 order。
- `uq_key_product_event__source_id (source_event_id)`。
- 事件名限制为 `marketing_campaign_created/marketing_campaign_updated/analytics_report_viewed/`
  `product_published/commerce_order_completed/automation_marketing_used`；版本大于零。
- Check：质量状态集合；接收/处理不得早于发生；accepted 正式事件不能是 robot 或 test。
- 事件名所需来源对象通过行内 Check 保证，例如 product published 要求 `product_id`，order completed 要求
  `commerce_order_id`。引用对象的 organization 一致性属于跨表校验。
- `ix_key_product_event__org_time (organization_id, occurred_at)` 支撑 30 日活跃快照。
- `ix_key_product_event__name_time (event_name, occurred_at)` 支撑功能趋势。
- `ix_key_product_event__member_time (organization_member_id, occurred_at)`。
- `ix_key_product_event__merchant_time (merchant_assignment_id, occurred_at)`。
- `ix_key_product_event__campaign_time (marketing_campaign_id, occurred_at)`。
- `ix_key_product_event__product_time (product_id, occurred_at)`。
- `ix_key_product_event__order_time (commerce_order_id, occurred_at)`。

**策略与覆盖**：事件 append-only，不保存自由文本、页面载荷或设备标识。重复上报由 source ID 唯一约束
拒绝；rejected 事件保留质量审计但不参与正式指标。事件引用的 member/merchant 必须在 occurred_at 时归属
本行 organization，由应用和数据质量任务验证。支撑 Active Organization Count、关键功能事件量和使用
organization 数，以及流失前使用变化。直接支撑 `GQ-PRD-002/003/004`、`GQ-XDM-004/008`。

## 12. 客服域物理设计

### 12.1 `support_ticket`

**用途与粒度**：保存一张结构化客服工单、当前便利状态和最终有效 CSAT；不保存正文。

**主键与业务键**：主键 `support_ticket_id`；业务唯一键 `external_ticket_id`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `support_ticket_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 工单主键 |
| `external_ticket_id` | `VARCHAR(128)` | 否 | 无 | 稳定外部工单 ID |
| `organization_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 可选 organization 归属 |
| `merchant_assignment_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 可选 merchant 归属 |
| `consumer_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 可选 consumer 归属 |
| `association_status` | `VARCHAR(32)` | 否 | 无 | `resolved/partial/unresolved` |
| `primary_object_type` | `VARCHAR(32)` | 是 | `NULL` | `subscription/order/product` |
| `subscription_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 可选主要订阅对象 |
| `commerce_order_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 可选主要订单对象 |
| `product_id` | `BIGINT UNSIGNED` | 是 | `NULL` | 可选主要商品对象 |
| `current_status` | `VARCHAR(32)` | 否 | 无 | 当前工单状态 |
| `priority` | `VARCHAR(32)` | 否 | 无 | `low/normal/high/urgent` |
| `category_code` | `VARCHAR(64)` | 否 | 无 | 受控问题分类 |
| `support_channel` | `VARCHAR(32)` | 否 | 无 | `email/web/chat/phone/api` |
| `created_at` | `DATETIME(6)` | 否 | 无 | 工单创建时间 |
| `first_human_response_at` | `DATETIME(6)` | 是 | `NULL` | 当前派生的首次有效人工公开响应 |
| `latest_solved_at` | `DATETIME(6)` | 是 | `NULL` | 当前派生的最近解决时间 |
| `closed_at` | `DATETIME(6)` | 是 | `NULL` | 关闭时间 |
| `csat_score` | `TINYINT UNSIGNED` | 是 | `NULL` | 最终有效 1–5 分 |
| `csat_submitted_at` | `DATETIME(6)` | 是 | `NULL` | 最终有效答卷提交时间 |
| `is_spam` | `BOOLEAN` | 否 | `FALSE` | 垃圾/误建标记 |
| `is_production` | `BOOLEAN` | 否 | `TRUE` | 是否生产工单 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试工单标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 首次记录时间 |
| `updated_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 当前派生状态更新时间 |

**外键、约束和索引**：

- 外键到 organization、merchant assignment、consumer、subscription、order 和 product。
- `uq_support_ticket__external_id (external_ticket_id)`。
- current status：`new/open/pending/solved/closed/cancelled`；association status、priority、channel 使用上述集合。
- 三个主要对象外键至多一个非空，且必须与 `primary_object_type` 匹配；type 为空时三个外键均为空。
- Check：CSAT 分数与提交时间同时为空或同时非空，分数 1–5；响应、解决、关闭、答卷时间不早于创建。
- solved/closed 当前状态要求 `latest_solved_at`；closed 要求 `closed_at`。
- `ix_support_ticket__created_priority (created_at, priority, category_code)`。
- `ix_support_ticket__current_status (current_status, is_test, is_spam, is_production)`。
- `ix_support_ticket__org_created (organization_id, created_at)`。
- `ix_support_ticket__merchant_created (merchant_assignment_id, created_at)`。
- `ix_support_ticket__consumer_created (consumer_id, created_at)`。
- `ix_support_ticket__subscription_created (subscription_id, created_at)`。
- `ix_support_ticket__order_created (commerce_order_id, created_at)`。
- `ix_support_ticket__product_created (product_id, created_at)`。
- `ix_support_ticket__csat_time (csat_submitted_at)`。

**策略与覆盖**：身份、分类和业务对象关联敏感；不保存请求者姓名、联系方式或工单正文。当前状态及派生
响应/解决时间可更新，但指标必须用 interaction/status event 验证；CSAT 只保留最终有效答卷，M1 不保存
修订历史。工单不硬删除。支撑所有客服指标和结构化跨域关联。直接支撑 `GQ-SUP-001–007`、
`GQ-XDM-005/006/008`。

### 12.2 `ticket_status_event`

**用途与粒度**：保存一次不可丢失的工单状态变化；重开事件不得被当前状态覆盖。

**主键与业务键**：主键 `ticket_status_event_id`；业务唯一键 `source_event_id`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `ticket_status_event_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 状态事件主键 |
| `source_event_id` | `VARCHAR(128)` | 否 | 无 | 稳定来源事件 ID；同时间决胜键 |
| `support_ticket_id` | `BIGINT UNSIGNED` | 否 | 无 | 所属工单 |
| `event_type` | `VARCHAR(32)` | 否 | 无 | `opened/pending/solved/closed/reopened/cancelled` |
| `status_before` | `VARCHAR(32)` | 是 | `NULL` | 变化前状态 |
| `status_after` | `VARCHAR(32)` | 否 | 无 | 变化后状态 |
| `effective_at` | `DATETIME(6)` | 否 | 无 | 状态生效时间，指标权威时间 |
| `created_at` | `DATETIME(6)` | 否 | 无 | 来源事件创建时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试状态事件标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 快照可见时间 |

**外键、约束和索引**：

- `fk_ticket_status_event__ticket`。
- `uq_ticket_status_event__source_id (source_event_id)`。
- Check：event type 和状态集合；`effective_at >= support_ticket.created_at` 属于跨表校验；行内保证
  `created_at >= effective_at` 不是必需条件，因为来源事件可能迟到创建，只要求两者语义分别保留。
- 行内映射：solved → solved、closed → closed、reopened → open、cancelled → cancelled；除首次 opened 外，
  `status_before <> status_after`。
- `ix_ticket_status_event__ticket_time (support_ticket_id, effective_at, source_event_id)` 支撑 as-of 最新状态。
- `ix_ticket_status_event__type_time (event_type, effective_at, support_ticket_id)` 支撑解决和重开去重。

**策略与覆盖**：事件 append-only；相同工单相同生效时刻允许多个不同事件，但必须用 `source_event_id`
确定顺序。合法状态转换链、最后解决后是否仍重开属于跨行规则。支撑 Resolution Time、Reopen Rate、
Open Ticket Count。直接支撑 `GQ-SUP-001–007`、`GQ-XDM-005/008`。

### 12.3 `ticket_interaction`

**用途与粒度**：保存一次工单交互的结构化元数据，用于识别首次成功的人工公开响应；不保存正文。

**主键与业务键**：主键 `ticket_interaction_id`；业务唯一键 `source_event_id`。

| 字段 | 类型 | NULL | 默认值 | 含义 |
| --- | --- | --- | --- | --- |
| `ticket_interaction_id` | `BIGINT UNSIGNED` | 否 | 自动递增 | 交互主键 |
| `source_event_id` | `VARCHAR(128)` | 否 | 无 | 稳定来源交互 ID |
| `support_ticket_id` | `BIGINT UNSIGNED` | 否 | 无 | 所属工单 |
| `actor_type` | `VARCHAR(32)` | 否 | 无 | `requester/support_agent/bot/system` |
| `visibility` | `VARCHAR(32)` | 否 | 无 | `public/internal` |
| `is_human` | `BOOLEAN` | 否 | 无 | 是否人工操作 |
| `delivery_status` | `VARCHAR(32)` | 否 | 无 | `pending/succeeded/failed` |
| `external_actor_id` | `VARCHAR(128)` | 是 | `NULL` | 外部 actor 引用，敏感 |
| `occurred_at` | `DATETIME(6)` | 否 | 无 | 交互发生时间 |
| `sent_at` | `DATETIME(6)` | 是 | `NULL` | 成功发送时间 |
| `is_test` | `BOOLEAN` | 否 | `FALSE` | 测试交互标记 |
| `recorded_at` | `DATETIME(6)` | 否 | 当前 UTC 时间 | 记录时间 |

**外键、约束和索引**：

- `fk_ticket_interaction__ticket`。
- `uq_ticket_interaction__source_id (source_event_id)`。
- Check：actor、visibility、delivery status 集合；bot/system 不能标为 human；succeeded 要求 sent_at，
  failed 不得作为有效响应；sent_at 不早于 occurred_at。
- `ix_ticket_interaction__ticket_time (support_ticket_id, occurred_at)`。
- `ix_ticket_interaction__first_response (support_ticket_id, actor_type, is_human, visibility, delivery_status, sent_at)`。

**策略与覆盖**：事件 append-only，重复投递由 source ID 去重。actor ID 敏感，不保存正文。首次有效人工
响应必须同时满足 support_agent、human、public、succeeded，并按最早 `sent_at` 选择；自动回复、内部备注和
发送失败不结束计时。支撑 First Response Time 和响应覆盖率。直接支撑
`GQ-SUP-002/004/005/007`。

## 13. 数据质量约束分层

### 13.1 数据库能够保证的规则

MySQL 8.4 必须负责可声明且确定的行级和引用完整性：

- 所有主键、外键和 `NOT NULL`；
- 外部业务 ID、来源事件 ID 和明确复合业务键唯一；
- 状态、类型、币种、布尔值和版本号允许范围；
- 单行时间先后关系、有效区间结束晚于开始；
- 金额非负、账单/退款组成金额的行内合计；
- marketing touch 的 organization/consumer 恰好一个；
- attributed conversion 的权威事实外键恰好一个并与 conversion type 匹配；
- support ticket 的主要业务对象至多一个并与 object type 匹配；
- CSAT 分数范围、终态与必要终态时间的一致性；
- 通过 `RESTRICT` 防止父对象被级联删除。

### 13.2 应用层必须保证的规则

以下规则需要读取其他行或其他表，应在写入服务的事务中校验：

- 同一 `merchant_id` 的 organization 归属区间不重叠；事件时间必须命中唯一 assignment；
- organization member 在事件发生时有效，merchant assignment 与事件 organization 一致；
- subscription 状态转换合法，同一生效时点的明细先净额化；首次激活只能一次；
- payment succeeded/failed 事件与外部提供商幂等键一致，失败支付不自动改变订阅效力；
- order item 的商品属于订单 merchant；完成订单必须成功支付且未取消；
- refund allocation 的 order item 属于退款对应订单；成功退款的 allocation 合计等于商品退款金额；
- campaign 的 merchant assignment 属于 campaign.organization；touch 的 campaign/channel 匹配；
- attributed conversion 的主体、时间和金额与权威支付、订单或收费事实一致；
- 非 direct 归因选择窗口内最后一次合格触达，同时间按 source event ID 决胜；
- ticket 的 organization、merchant、consumer 和主要业务对象关联互相一致；
- ticket status event 形成合法状态序列，interaction 的工单时间不早于工单创建。

应用校验失败必须拒绝写入或将来源记录隔离为无资格数据，不得静默修正业务含义。

### 13.3 测试必须保证的规则

单元和集成测试必须覆盖：

- 月付/年付 MRR 规范化、未生效取消、同一时点净额化和 organization Logo Churn 去重；
- 成功/失败/重复支付尝试只统计一次成功收入；
- GMV 不扣退款，取消订单被排除，部分和跨月退款按完成期统计；
- allocation 不复制 GMV，分配合计与退款商品金额一致；
- 168 小时左右边界、同时间触达决胜、direct 与 unknown/unattributed 分离；
- 14 日激活窗口、三种条件按类型去重、未成熟 cohort 不进分母；
- 产品事件重复、机器人、测试和错误 organization 映射被排除；
- 工单多次 solved/reopened 的最后解决时间、Reopen distinct 计数和 Open as-of 重建；
- 每张表的状态、时间、金额、唯一和外键约束拒绝非法数据；
- migration 从空库升级、降级、再次升级后结构一致。

### 13.4 数据质量任务必须保证的规则

定期数据质量检查负责不能可靠放入同步写事务的全量规则：

- merchant 有效区间不重叠、无缺口要求是否满足、稳定属性跨区间一致；
- subscription 当前便利状态与最后有效 state event 一致；
- invoice paid 状态与成功 payment attempt 对账；成功交易/收费 provider ID 无重复；
- refund allocation 总额、币种、订单范围与 refund 对账；
- attributed conversion 每个权威事实每种 conversion type 恰好一个有效结果，窗口和主体完整性正确；
- key product event 和 ticket 的跨域归属可追溯且没有一对多复制；
- 测试标记沿 organization、member、consumer、merchant、order、payment、refund、campaign、ticket
  归属链一致；
- 缺失必需金额、业务时间、状态、关键映射和不支持币种的事实被隔离并报告；
- 迟到和更正数据在固定数据快照中的可见性与 `recorded_at` 一致。

### 13.5 测试数据排除决策

数据库不创建“正式数据视图”或自动级联测试标记。每个事实保留自己的 `is_test`，同时沿固定归属链排除：

| 事实 | 必查测试链 |
| --- | --- |
| SaaS state/invoice/payment | fact → subscription → organization；同时检查 plan |
| order/order item | fact → order → consumer + merchant assignment → organization；同时检查 product |
| refund/allocation | fact → refund → order → consumer + merchant assignment → organization |
| platform fee | fact → order → consumer + merchant assignment → organization |
| campaign spend/touch | fact → campaign/channel + organization/consumer/merchant assignment |
| attributed conversion | result + selected touch + channel/campaign + subject + authoritative conversion fact |
| key product event | event + organization + actor/source object |
| ticket status/interaction | event → ticket + ticket analysis ownership |

缺失关键归属不能按“非测试”处理；应标记数据质量错误并禁止进入正式跨域指标。

## 14. 删除、更新与历史保留总则

- 主数据和可变业务对象使用状态和结束时间关闭，生产历史不硬删除。
- 事件事实原则上 append-only；重复回调由业务唯一键幂等拒绝。
- 已被事实引用的 plan、organization、consumer、merchant assignment、product、channel 和 campaign
  删除均被外键 `RESTRICT` 阻止。
- 当前便利字段允许更新，但不得替代历史事件：subscription 当前状态、invoice/order/refund 当前状态、
  support ticket 当前状态和派生时间均需与事件/事实对账。
- 金额、业务时间或身份归属纠错必须保留审计信息；M1.1A 只规定原则，不新增通用审计表。
- 测试环境清理按外键逆依赖顺序显式删除，不通过生产级 cascade 简化 fixture。

## 15. migration 分阶段计划

### 15.1 M1.1B：企业身份 + SaaS

**创建表**：`organization`、`organization_member`、`consumer`、`merchant`、`saas_plan_version`、
`subscription`、`subscription_state_event`、`subscription_invoice`、`invoice_payment_attempt`。

**依赖顺序**：organization → member/merchant/subscription；plan → subscription/state event；subscription →
state event/invoice → payment attempt。consumer 在本阶段建立，供下一阶段订单引用。

**验证**：空库 upgrade；PK/FK/unique/check 元数据；非法状态和时间拒绝；月付/年付、首次激活、升级、
降级、取消生效、失败/成功支付的最小集成数据；downgrade 后无残留对象，再次 upgrade。

**回滚**：按 payment attempt → invoice → state event → subscription → plan → member/merchant/consumer →
organization 的逆依赖删除。若已有下游阶段，不允许单独回滚 M1.1B。

### 15.2 M1.1C：商城交易

**创建表**：`product`、`commerce_order`、`commerce_order_item`、`commerce_refund`、
`refund_item_allocation`、`platform_fee_charge`。

**依赖**：M1.1B 的 consumer、merchant 和 organization；内部顺序为 product/order → order item →
refund/fee → allocation。

**验证**：多明细订单、未支付/取消订单、部分退款、跨期退款、多收费尝试；检查 allocation 跨表规则和
类别快照；确认 GMV、退款和平台费的索引可命中权威时间列。

**回滚**：allocation → refund/fee → order item → order/product。存在营销归因或客服引用时先回滚下游阶段。

### 15.3 M1.1D：营销

**创建表**：`marketing_channel`、`marketing_campaign`、`campaign_daily_spend`、`marketing_touch`、
`attributed_conversion`。

**依赖**：身份表、payment attempt、commerce order、platform fee charge；内部顺序为 channel → campaign →
spend/touch → attributed conversion。

**验证**：一个转化一个结果、三个权威事实外键互斥、SaaS/Commerce 主体互斥、168 小时两端边界、
同时间 source ID 决胜、窗口不完整为 unknown、完整无非 direct 触达为 direct、花费更正不重复相加。

**回滚**：attributed conversion → touch/spend → campaign → channel；不影响已存在的权威业务事实。

### 15.4 M1.1E：产品使用 + 客服

**创建表**：`key_product_event`、`support_ticket`、`ticket_status_event`、`ticket_interaction`。

**依赖**：前序全部身份和可能引用的 campaign、product、order、subscription；内部顺序为 key event、
support ticket → status event/interaction。

**验证**：事件稳定 ID 去重、robot/test/rejected 排除、事件时 organization 归属；工单首次有效人工响应、
solved→reopened→solved、重开后未解决、Open as-of 和 CSAT 1–5 范围。

**回滚**：interaction/status event → ticket → key product event；不级联删除上游业务对象。

### 15.5 M1.1F：约束、索引与验收

各阶段创建表时即带上核心 PK、FK、unique 和行内 Check；M1.1F 不允许把必要完整性延后。本阶段负责：

- 对实际 Gold SQL 查询计划验证复合索引，删除证据不足的重复索引；
- 补充只能在所有表存在后创建的跨域外键或约束；
- 执行 24 表 Schema 清单、列类型、NULL/default、约束名称和索引名称验收；
- 运行全链路测试排除、merchant 区间、refund allocation、attribution 和 ticket reopen 数据质量检查；
- 从空数据库完整 upgrade → downgrade base → upgrade，比较最终 `information_schema`；
- 记录 migration revision、业务定义版本和 Schema 验收结果。

回滚按 M1.1E → D → C → B 的逆序执行。任何阶段 downgrade 若会删除非测试业务数据，必须先备份并由
明确运维流程批准；M1 不设计自动破坏性回滚。

## 16. 指标与 Gold Questions 物理支撑检查

| 重点口径 | 权威物理事实 | 关键防错点 |
| --- | --- | --- |
| MRR/ARR | `subscription_state_event` | effective time as-of、年付除 12、同时间净额化 |
| SaaS Revenue | `invoice_payment_attempt` | succeeded、仅订阅费用、失败重试不重复 |
| GMV/Order Count/AOV | `commerce_order` + `commerce_order_item` | first paid、未取消、明细金额、订单去重 |
| Refund/Net Sales | `commerce_refund` + `refund_item_allocation` | succeeded time、跨期、allocation 不复制 GMV |
| Commerce Revenue | `platform_fee_charge` | 收费成功时间，不等于 GMV 或净销售 |
| CAC/ROAS | spend + attributed conversion + 权威转化事实 | 身份/收入类型分开、零分母、direct/unknown |
| Activation | organization + member + campaign + completed order | 14 日、不同条件任意二项、成熟 cohort |
| Active Organization | `key_product_event` | 30 日 as-of、稳定 ID、唯一 organization |
| First Response | `ticket_interaction` | human + public + succeeded 的最早 sent time |
| Resolution/Reopen/Open | `ticket_status_event` | 最后解决、重开、as-of 最新状态 |
| CSAT | `support_ticket` 最终有效答卷 | 提交时间、1–5 分、无样本为 null |

24 张表共同覆盖 [`m1-gold-question-catalog.md`](m1-gold-question-catalog.md) 的 48 个问题。标记为需澄清的
问题仍必须在澄清后才生成 Gold SQL；物理字段齐备不等于业务定义已经批准。后续 Gold SQL 必须继续验证：

- 洛杉矶业务周期和固定快照截止时间；
- 事实与完整归属链的测试排除；
- 快照、金额、比率和 distinct 计数的可加性；
- 跨域先聚合后连接，避免一对多放大；
- 未批准的收入合计、漏斗、健康度和因果结论不被临时构造。

## 17. 已知限制与后续触发条件

- M1 不落 MRR、Active Organization 或 Open Ticket 周期快照，均按事件重建。
- M1 不保存完整订单状态历史，因此订单历史合格性依赖固定数据快照中的当前取消状态。
- M1 不保存 CSAT 修订历史，只保存最终有效答卷。
- merchant 区间不重叠、状态转换、allocation 合计、归因选择和测试链无法全部由数据库声明式保证。
- M1 不支持多币种、服务费退回、SaaS 净收入、多触点归因、商品分类层级或客服正文。
- 若实际数据量证明事件重建或 Gold SQL 无法满足性能目标，必须先用查询计划和基准数据证明，再设计
  汇总表或快照表；不得在 migration 中提前增加未批准表。
- 若 merchant 身份需要独立生命周期或重新归属成为常态，应升级为方案 B，并在 migration 前形成新的
  架构决定和兼容方案。

以上限制不得由 ORM、Prompt、Gold SQL 或种子数据静默绕过。
