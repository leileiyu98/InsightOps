# M1.0 逻辑数据模型

## 1. 文档目的与边界

本文从已冻结的 `insightcloud-business-definitions 1.0.0` 和计划支持的 Gold
Questions 反推 InsightCloud V1 的逻辑数据需求，为后续物理建模、确定性种子数据、
Gold SQL、Text2SQL 语义层、RAG、受控 Agent 工作流和 Evaluation 提供共同输入。

本文只定义逻辑对象、事实粒度、关系、状态、时间和分析约束，不包含物理字段类型、
DDL、Alembic migration、SQL、ORM、种子数据或应用实现。本文不改变
[`business-definitions-v1.md`](business-definitions-v1.md) 的任何业务口径；发生冲突时，
冻结定义始终优先。

### 1.1 范围分层

- **M1 必须实现**：本文第 4—9 节列出的 24 个核心物理表候选及其逻辑约束。
- **M1 暂不实现**：预聚合指标表、周期快照表、订单完整状态历史、客服答卷历史、
  商品分类独立维表、广告组和素材层级。
- **后续可能扩展**：上述暂不实现对象，以及经新业务定义批准的历史修正和数据治理对象。
- **明确不引入**：多币种、汇率、复杂税务、会计收入确认、复杂佣金结算、多触点归因、
  跨设备身份合并、客服文本 RAG、向量数据库、Agent 运行表、Memory 表和 MCP 表。

## 2. 全局分析约定

### 2.1 时间与数据快照

- 所有业务时刻统一以 UTC 保存，报表周期按 `America/Los_Angeles` 转换后划分。
- 自然日、月和季度使用业务时区的左闭右开区间；夏令时日期不得假设固定为 24 小时。
- 每次 Gold 结果必须绑定数据快照版本和查询截止时间。迟到、更正、取消、退款和重开只使用
  截止时间前已经进入固定快照的记录。
- 事件指标使用本指标指定的发生或生效时间；快照指标使用明确的 `as of`。
- M1 不保存通用日历表。业务时区边界由后续查询层确定性生成；如果后续性能数据证明需要，
  再评估日历维表。

### 2.2 金额、空值与测试数据

- V1 金额仅支持 USD。非 USD 或缺失必需金额的事实不能进入金额指标，也不能按零处理。
- 合格事实集合为空时，加法指标为 `0`；数据缺失、口径不可判定或零分母导致无法计算时为
  `null`，并记录原因。
- 每个身份、主业务对象和事件事实都必须有显式测试标记或能够沿唯一归属链继承测试标记。
- 只依据显式标记排除测试数据，不根据名称、邮箱、金额或其他启发式条件猜测。
- 若事实本身或其归属 organization、member、consumer、merchant、order、payment、refund、
  campaign 被标记为测试，该事实不得进入正式指标。

### 2.3 当前状态、事件历史与快照

| 模式 | M1 用途 | 规则 |
| --- | --- | --- |
| 可变实体 | 保存当前可操作状态和稳定属性 | 不能覆盖指标所需的历史生效时间；需要历史的变化必须另有事件事实 |
| 事件事实 | 保存不可丢失的业务发生、状态变化或支付尝试 | 使用稳定事件标识去重，保留发生时间、记录时间和测试标记 |
| 周期快照 | MRR、活跃企业和 Open Ticket 的可选性能优化 | M1 不落表，由事件历史按 `as of` 重建，不得把多个快照相加 |

## 3. 身份边界与受治理连接

### 3.1 身份定义

- **organization**：购买 SaaS、注册使用 InsightCloud，也可能经营商城的企业主体。
- **organization member**：在某一 organization 范围内使用 SaaS 的员工身份。
- **consumer**：在商城下单和支付的消费者身份。
- **merchant**：organization 在商城中的经营角色，通过有有效期的受治理关系归属 organization。

organization 与 consumer 不属于同一种用户实体。member 与 consumer 即使来自同一登录账号，
V1 也不自动合并。consumer 只按稳定 consumer 业务标识去重，不做跨账号或跨设备身份合并。

### 3.2 允许的身份连接路径

| 来源 | 目标 | 连接依据 | 基数与时间规则 | 禁止行为 |
| --- | --- | --- | --- | --- |
| member | organization | 成员关系中的稳定 organization 标识 | 多对一；使用事件发生时有效的成员关系 | 按邮箱或姓名推断归属 |
| merchant | organization | 受治理的 merchant—organization 有效区间 | 每个时点至多归属一个 organization；有效区间不得重叠 | 同一事件同时复制给多个 organization |
| order | consumer | 订单创建时保存的稳定 consumer 标识 | 多对一；不跨设备合并 | 通过 member 账号间接合并消费者 |
| order/product | merchant | 稳定 merchant 标识 | 多对一；再按事件时刻解析 organization | 直接按商家名称连接 organization |
| product event | organization | 事件时有效的 member 或 merchant 映射，或已验证的直接 organization 标识 | 每个事件最多归属一个 organization | 映射缺失时猜测归属 |
| ticket | organization/merchant/consumer | 工单创建时受治理的请求者与业务归属标识 | 可有一个主要分析归属；多对象引用不代表互斥分组 | 将一张工单在计数中重复展开 |

跨域查询必须先在各自权威事实粒度聚合，再通过上述路径连接聚合结果。关键映射缺失时应澄清、
降级为单域分析或拒绝连接。

### 3.3 M1 核心表候选清单

| 数据域 | M1 必须实现的核心表候选 | 数量 |
| --- | --- | ---: |
| 企业与身份 | organization、organization_member、consumer、merchant | 4 |
| SaaS | saas_plan_version、subscription、subscription_state_event、subscription_invoice、invoice_payment_attempt | 5 |
| 商城 | product、commerce_order、commerce_order_item、commerce_refund、refund_item_allocation、platform_fee_charge | 6 |
| 营销 | marketing_channel、marketing_campaign、campaign_daily_spend、marketing_touch、attributed_conversion | 5 |
| 产品使用 | key_product_event | 1 |
| 客服 | support_ticket、ticket_status_event、ticket_interaction | 3 |
| **合计** |  | **24** |

这里的“表候选”用于控制 M1 物理模型规模，不是 DDL 承诺。后续物理设计只能在不改变本文事实粒度、
身份边界和指标口径的前提下命名字段和约束；如果需要突破 24 表，必须先说明新增对象的明确分析用途。

## 4. 企业与身份域（4 个核心表候选）

### 4.1 `organization`

- **业务用途、粒度和主键**：一行代表一个企业身份；业务主键为稳定 organization ID。
- **关系与状态**：关联 member、subscription、campaign 和 merchant；状态至少区分 registered、
  active、suspended、closed，另有 SaaS 或商城角色不能替代 organization 状态。
- **时间语义**：保存注册、创建、关闭和记录更新时间；注册 cohort 使用注册业务时刻。
- **事实类型和报表时间**：可变实体；注册量和激活率分母使用注册时间，活跃企业使用独立事件和
  `as of`，不能使用当前 organization 状态替代。
- **测试与敏感性**：必须有显式测试标记；企业名称和外部客户标识属于受限业务信息。
- **依赖指标**：Logo Churn Rate、新增付费 organization、Activation Rate、Active Organization
  Count，以及全部 organization 级跨域分析。
- **重复风险**：连接多个订阅、成员、商家或工单后直接计数会复制 organization；必须先去重或
  分域聚合。

### 4.2 `organization_member`

- **业务用途、粒度和主键**：一行代表一个 organization 与一个 SaaS 成员身份的关系生命周期；
  业务主键为稳定 membership ID，不与 consumer ID 共用。
- **关系与状态**：多对一归属 organization；状态至少区分 invited、active、removed、expired。
- **时间语义**：保存首次成功邀请、接受、关系生效和结束时刻；企业激活条件使用首次成功邀请时间。
- **事实类型和报表时间**：可变实体，保留不可覆盖的首次邀请时间；M1 不单独保存重复邀请事件。
- **测试与敏感性**：成员及关系均可标记测试；登录账号引用、联系方式和显示名属于个人敏感信息，
  Gold Questions 不要求返回明细。
- **依赖指标**：Activation Rate、member 触发的 Active Organization Count、关键功能使用趋势。
- **重复风险**：一个 organization 有多个 member；把成员行为连接订阅后汇总会复制 MRR 或收入。

### 4.3 `consumer`

- **业务用途、粒度和主键**：一行代表一个商城消费者业务身份；业务主键为稳定 consumer ID。
- **关系与状态**：关联订单和营销触达；不与 member 自动合并。状态至少区分 active、blocked、closed。
- **时间语义**：保存创建、首次可识别和关闭时刻；新增 Commerce 付费客户的转化时刻来自首个合格
  订单首次支付，不来自 consumer 创建时间。
- **事实类型和报表时间**：可变实体；V1 不保存跨设备身份图。
- **测试与敏感性**：必须有测试标记；联系方式、设备或外部账号标识属于个人敏感信息。
- **依赖指标**：Commerce 新增付费客户数、Commerce CAC、Commerce 归因和消费者维度订单分析。
- **重复风险**：一个 consumer 有多个订单和触达；订单与触达明细直接连接会复制 GMV。

### 4.4 `merchant`

- **业务用途、粒度和主键**：一行代表一个 merchant 对某 organization 的受治理归属有效区间，
  业务主键为 merchant ID 与有效起始时刻；稳定 merchant ID 可跨区间保持不变。
- **关系与状态**：关联 organization、product、order 和 campaign；区间内状态至少区分 pending、
  approved、active、suspended、closed，同一 merchant 的 organization 归属区间不得重叠。
- **时间语义**：保存归属生效/失效、申请、批准、启用和关闭时间；订单与产品事件按其业务发生时刻
  选择有效映射。
- **事实类型和报表时间**：带有效期的可变实体；M1 不另建映射桥表。
- **测试与敏感性**：merchant 和归属 organization 都可触发测试排除；商家名称和外部标识属于受限
  业务信息。
- **依赖指标**：GMV、Order Count、Refund Amount、Merchant Net Sales、Platform Transaction
  Revenue、商家营销成本、商城订单激活条件。
- **重复风险**：跨多个有效区间或 organization 映射连接时可能复制交易；必须使用事件时点命中唯一
  区间。

## 5. SaaS 套餐、订阅和账单域（5 个核心表候选）

### 5.1 `saas_plan_version`

- **业务用途、粒度和主键**：一行代表一个 SaaS 套餐的一个有效版本；业务主键为 plan ID 与版本号。
- **关系与状态**：被 subscription 引用；状态为 draft、active、retired。计费周期 V1 仅允许 monthly
  或 annual。
- **时间语义**：保存版本生效和失效时刻；订阅事件引用当时的版本，不能用当前价格回写历史。
- **事实类型和报表时间**：可变参考实体；不直接形成收入事件。
- **测试与敏感性**：通常非敏感；测试套餐需显式标记且只服务测试订阅。
- **依赖指标**：MRR、ARR、各类 MRR 变动及套餐分组分析。
- **重复风险**：按 plan ID 连接全部版本会复制订阅；必须按订阅引用版本或有效期唯一命中。

### 5.2 `subscription`

- **业务用途、粒度和主键**：一行代表一个 organization 的一次订阅生命周期；业务主键为稳定
  subscription ID。
- **关系与状态**：多对一关联 organization 和 plan version，一对多关联状态事件和账单；当前状态
  至少区分 pending、trialing、active、paused、cancel_scheduled、cancelled、expired。
- **时间语义**：保存创建、首次激活、当前周期、取消安排、生效和到期时刻；历史报表以状态事件的
  生效时间为准。
- **事实类型和报表时间**：可变实体，当前状态仅用于便利读取；MRR 和流失必须从事件历史按
  `as of` 重建。
- **测试与敏感性**：自身或 organization 测试时排除；合同外部标识和价格属于受限商业信息。
- **依赖指标**：全部 SaaS 指标和 organization 首次付费转化。
- **重复风险**：organization 可有多个订阅；Logo Churn 必须判断最后一个有效订阅失效，不能把订阅
  流失数当作 organization 流失数。

### 5.3 `subscription_state_event`

- **业务用途、粒度和主键**：一行代表同一订阅在一个生效时点净额化后的一次状态或规范化 MRR
  变化；业务主键为稳定 subscription event ID。
- **关系与状态**：多对一关联 subscription；记录变更前后有效状态、plan version、折扣后周期费用、
  计费周期和规范化 MRR。事件类型包括 first_activation、expansion、contraction、pause、resume、
  cancellation_effective、expiration。
- **时间语义**：区分事件生效、创建和记录时间；所有 MRR 变动使用生效时间。
- **事实类型和报表时间**：不可变事件事实；同一订阅同一生效时点的明细变化必须先净额化为一行。
- **测试与敏感性**：继承 subscription 和 organization 测试标记，也保留事实自身标记；金额为受限
  商业信息。
- **依赖指标**：MRR、ARR、New/Expansion/Contraction/Churned MRR、Logo Churn Rate、Revenue
  Churn Rate。
- **重复风险**：未先净额化会把同一时点同时计作 Expansion 和 Contraction；与账单或支付连接后
  直接汇总会复制 MRR 变化。

### 5.4 `subscription_invoice`

- **业务用途、粒度和主键**：一行代表一张订阅账单；业务主键为稳定 invoice ID。
- **关系与状态**：关联一个 subscription，一对多关联支付尝试；状态至少区分 draft、open、paid、
  void、uncollectible。
- **时间语义**：保存生成、到期、作废和最终支付完成时刻；账单生成时间不是 SaaS Revenue 时间。
- **事实类型和报表时间**：可变实体；账单金额按折扣后订阅费、税费和一次性费用分别保留逻辑成分。
- **测试与敏感性**：账单或上游身份为测试时排除；账单金额和外部账单号属于受限商业信息。
- **依赖指标**：为 SaaS Revenue 提供账单范围和订阅费用组成，但收入事实来自成功支付尝试。
- **重复风险**：一张账单可有多次支付尝试；按账单金额连接尝试后汇总会重复收入。

### 5.5 `invoice_payment_attempt`

- **业务用途、粒度和主键**：一行代表对一张订阅账单的一次支付尝试；成功支付仍是一条尝试事实；
  业务主键为稳定 payment attempt ID。
- **关系与状态**：多对一关联 invoice；状态至少区分 pending、succeeded、failed、cancelled。成功记录
  需区分折扣后不含税订阅费用、税费和一次性费用。
- **时间语义**：保存尝试、成功、失败和记录时间；SaaS Revenue 使用支付成功时间。
- **事实类型和报表时间**：事件事实；失败重试必须保留，成功事实不可被后续账单状态覆盖。
- **测试与敏感性**：自身、invoice、subscription 或 organization 为测试时排除；支付提供商标识和金额
  属于高敏受限信息，不保存支付凭证。
- **依赖指标**：SaaS Revenue、SaaS 新增付费 organization、SaaS CAC、归因 SaaS Revenue、SaaS Attributed ROAS。
- **重复风险**：多次尝试只能统计 succeeded；同一成功交易的重复回调必须以稳定业务标识去重。

## 6. 商城商品、订单和退款域（6 个核心表候选）

### 6.1 `product`

- **业务用途、粒度和主键**：一行代表一个 merchant 的商品；业务主键为稳定 product ID。
- **关系与状态**：多对一关联 merchant，被 order item 引用；状态为 draft、active、inactive、archived。
  M1 使用受控 category code，不单独建商品分类表。
- **时间语义**：保存创建、首次发布、下架和更新时间；关键产品事件使用发布发生时间，不使用当前状态。
- **事实类型和报表时间**：可变实体。
- **测试与敏感性**：测试商品或测试 merchant 必须排除；商品标题通常非敏感，成本等未定义属性不进入 M1。
- **依赖指标**：按商品或类别的 GMV、Refund Amount、Refund Rate、关键功能使用趋势。
- **重复风险**：商品多次出现在订单明细；按商品连接退款和订单时必须分别聚合。

### 6.2 `commerce_order`

- **业务用途、粒度和主键**：一行代表一笔商城订单；业务主键为稳定 order ID。
- **关系与状态**：关联一个 consumer 和一个 merchant，一对多关联 order item、refund 和 fee charge；
  状态至少区分 created、payment_pending、paid、fulfilled、completed、cancelled。
- **时间语义**：保存创建、首次支付成功、履约、完成、取消和记录时间；GMV、Order Count、AOV 使用
  首次支付成功时间，激活第三条件还要求完成时间存在。
- **事实类型和报表时间**：可变实体，保留关键不可覆盖时间；固定数据快照中的当前取消状态决定历史
  订单是否仍合格。完整订单状态事件历史在 M1 暂不实现。
- **测试与敏感性**：订单、consumer、merchant 或 organization 为测试时排除；订单外部标识和购买关系
  属于敏感交易信息。
- **依赖指标**：GMV、Order Count、AOV、Merchant Net Sales、Commerce 新增付费客户、企业激活。
- **重复风险**：订单有多明细、多退款和多收费；Order Count 必须按 order 去重，不能在展开明细后计数。

### 6.3 `commerce_order_item`

- **业务用途、粒度和主键**：一行代表订单中的一条商品明细；业务主键为稳定 order item ID。
- **关系与状态**：多对一关联 order 和 product，被退款分配引用；M1 不单独维护明细状态机。
- **时间语义**：创建时间随订单；GMV 报表时间继承订单首次支付成功时间。
- **事实类型和报表时间**：不可变交易明细事实；保存数量及折扣后商品金额，税费和运费不得混入。
- **测试与敏感性**：自身、order、product 或上游身份测试时排除；购买明细属于敏感交易信息。
- **依赖指标**：GMV、AOV、Merchant Net Sales、商品和类别分析。
- **重复风险**：同一明细被多个退款分配连接时会复制 GMV；GMV 必须先按唯一明细计算。

### 6.4 `commerce_refund`

- **业务用途、粒度和主键**：一行代表一次退款生命周期；业务主键为稳定 refund ID。
- **关系与状态**：关联一个 order，一对多关联退款分配；状态至少区分 requested、pending、succeeded、
  failed、cancelled。
- **时间语义**：保存申请、处理、成功完成和记录时间；Refund Amount 使用成功完成时间，不回移到订单
  支付周期。
- **事实类型和报表时间**：可变业务对象，成功完成是独立反向事件；失败或待处理不进入指标。
- **测试与敏感性**：自身、order 或上游身份测试时排除；退款原因代码属于受限业务信息，M1 不保存文本。
- **依赖指标**：Refund Amount、Refund Rate、Merchant Net Sales。
- **重复风险**：一笔退款可覆盖多个明细；不能按 refund 总额连接每条明细后重复汇总。

### 6.5 `refund_item_allocation`

- **业务用途、粒度和主键**：一行代表一次退款分配到一条 order item 的商品金额；业务主键为稳定
  refund allocation ID，refund 与 order item 的组合必须可确定性去重。
- **关系与状态**：多对一关联 refund 和 order item；只表达商品金额分配，不包含税费和运费。
- **时间语义**：报表时间继承 refund 成功完成时间；创建和更正时间另行保留。
- **事实类型和报表时间**：事件明细事实。
- **测试与敏感性**：继承 refund、order item 及上游测试标记；金额属于敏感交易信息。
- **依赖指标**：Refund Amount、Refund Rate、Merchant Net Sales、按商品或类别退款分析。
- **重复风险**：同一退款的分配合计必须与成功商品退款金额一致；连接 order item 后不得再次汇总订单 GMV。

### 6.6 `platform_fee_charge`

- **业务用途、粒度和主键**：一行代表平台针对订单成功或尝试收取的一项交易服务费；业务主键为稳定
  fee charge ID。
- **关系与状态**：多对一关联 order；状态为 pending、succeeded、failed、cancelled。
- **时间语义**：保存收费尝试和成功时间；Platform Transaction Revenue 使用收费成功时间。
- **事实类型和报表时间**：事件事实；V1 不实现服务费退回或复杂佣金结算。
- **测试与敏感性**：自身、order 或上游身份测试时排除；金额属于受限商业信息。
- **依赖指标**：Platform Transaction Revenue、Commerce Revenue、归因 Commerce Revenue、Commerce Attributed ROAS。
- **重复风险**：一个订单可有多个收费尝试；仅稳定去重后的 succeeded 事实进入收入。

## 7. 营销渠道、活动、花费和归因域（5 个核心表候选）

### 7.1 `marketing_channel`

- **业务用途、粒度和主键**：一行代表一个受治理渠道定义；业务主键为稳定 channel ID。
- **关系与状态**：关联 campaign 和 touch；状态为 active、inactive。`direct` 是明确渠道分类，
  `unknown/unattributed` 是无法判定的归因结果，两者不能共用标识。
- **时间语义**：保存定义生效和失效时间；事件按发生时有效映射解析渠道。
- **事实类型和报表时间**：带有效期的参考实体。
- **治理规则**：`channel_code` 创建后不可修改；`channel_name` 是可变显示名，可更新但不得改变代码的历史
  业务含义。语义变化必须创建新 channel code。
- **测试与敏感性**：测试渠道不得参与正式归因；渠道定义通常非敏感。
- **依赖指标**：CAC、Attributed ROAS、Attributed Revenue、新增付费客户数和渠道趋势。
- **重复风险**：渠道版本或层级多对多映射会复制花费；M1 每个事件只映射一个有效渠道。

### 7.2 `marketing_campaign`

- **业务用途、粒度和主键**：一行代表一个 organization 或 merchant 发起的营销活动；业务主键为稳定
  campaign ID。
- **关系与状态**：关联一个主要 channel，可关联 organization 和可选 merchant；状态至少区分 draft、
  active、paused、completed、cancelled。
- **时间语义**：保存创建、开始、结束和状态更新时间；企业激活条件使用非测试活动创建时间。
- **事实类型和报表时间**：可变实体；预算不是实际花费事实。
- **测试与敏感性**：活动、渠道或归属身份测试时排除；活动名称、预算属于受限商业信息。
- **依赖指标**：Activation Rate、CAC、Attributed ROAS、Attributed Revenue、活动效率分析。
- **重复风险**：活动连接每日花费、多个触达和转化后会产生笛卡尔放大；三类事实必须先分别聚合。

### 7.3 `campaign_daily_spend`

- **业务用途、粒度和主键**：一行代表一个 campaign 在一个业务自然日确认的实际广告花费；业务主键为
  campaign ID 与业务日期。
- **关系与状态**：多对一关联 campaign；每行是一版 final revision，更正通过追加更高 version 并引用被
  替代 revision 实现，不使用 provisional 状态，也不原地更新。
- **时间语义**：业务日期按 `America/Los_Angeles` 划分，同时保留 finalized 和 recorded UTC 时刻。
- **事实类型和报表时间**：自然日周期事实，不是累计快照。先筛选 `recorded_at <= snapshot_cutoff`，再在
  每个 campaign/date 的可见 revision 中选择最大 version；不得先取全局最大 version。
- **测试与敏感性**：活动或花费行测试时排除；花费属于受限商业信息。
- **依赖指标**：CAC、Attributed ROAS、营销花费和渠道/活动效率趋势。
- **重复风险**：与触达或转化明细直接连接会复制花费；跨日相加只允许不重叠日期和互斥活动范围。

### 7.4 `marketing_touch`

- **业务用途、粒度和主键**：一行代表一次可识别营销接触；业务主键为稳定来源事件 ID。
- **关系与状态**：关联 channel、可选 campaign，以及 organization 或 consumer 中恰好一个归因主体；
  touch type 区分非 direct 合格触达和 direct 访问。
- **时间语义**：区分接触发生、接收、处理和 recorded 可见时间；168 小时窗口使用真实发生时刻，但一次
  归因只能读取其 `source_data_cutoff_at` 之前可见的 touch。
- **事实类型和报表时间**：事件事实；同时间触达使用稳定来源事件 ID 决定顺序。
- **测试与敏感性**：触达、渠道、活动或主体测试时排除；设备和营销标识属于个人敏感信息。
- **依赖指标**：最后非直接触达归因、Attributed Revenue、CAC、Attributed ROAS、新增付费客户渠道分布。
- **重复风险**：一个转化可有多个候选触达；不能把全部候选都连接到收入，必须先选唯一归因结果。

### 7.5 `attributed_conversion`

- **业务用途、粒度和主键**：一行代表一个已确认业务转化的一次 V1 最终归因结果；业务主键为
  conversion type 与权威转化事实 ID，每个转化最多一行。
- **关系与状态**：转化类型明确区分 SaaS 首次付费、SaaS Revenue、Commerce 首次付费、Commerce
  Revenue 和归因 GMV；引用唯一权威支付、收费或订单事实。归因结果为具体非 direct 渠道/活动、
  direct 或 unknown/unattributed。
- **时间语义**：转化时间来自权威支付、收费或订单首次支付成功时间；归因计算和版本时间另行保留。
- **事实类型和报表时间**：按 source-data cutoff 版本化的 append-only 派生事实，结果必须能追溯至最终
  selected touch 和权威转化；V1 模型固定为 168 小时最后非直接触达，候选窗口为
  `[转化时刻 − 168 小时, 转化时刻]`。晚到 touch 不覆盖旧结果，而是在更晚 cutoff 追加结果。
- **测试与敏感性**：触达、转化、渠道、活动或主体任一测试时不得形成正式归因；身份连接属于敏感信息。
- **依赖指标**：Attributed Revenue、CAC、Attributed ROAS、新增付费客户数及 unattributed 披露；不得把
  Attributed ROAS 命名为财务 ROI。
- **重复风险**：同一收入事实不得拥有多个有效归因结果；不同收入类型不能合并成未命名的通用收入。

## 8. 产品使用行为域（1 个核心表候选）

### 8.1 `key_product_event`

- **业务用途、粒度和主键**：一行代表一次去重后的关键产品事件；业务主键为稳定来源事件 ID。
- **关系与状态**：必须解析到唯一 organization，并可引用 member、merchant、campaign、product 或 order
  来源对象。V1 事件集合为创建/修改营销活动、查看经营分析报表、发布商品、完成真实商城订单和使用
  自动化营销功能；事件名称和版本必须受控。
- **时间语义**：区分业务发生、接收和处理时间；激活条件使用各权威域事件，30 日活跃和使用趋势使用
  业务发生时间。
- **事实类型和报表时间**：不可变事件事实；重试、重复上报、机器人和更正需通过稳定 ID 与质量状态治理。
- **测试与敏感性**：事件、来源对象、actor 或 organization 测试时排除；不保存页面自由文本和原始载荷。
- **依赖指标**：Active Organization Count、关键功能使用趋势，并用于流失前使用下降的跨域分群分析。
- **重复风险**：同一业务动作被多端重复上报时会高估使用量；一个事件只能归属一个 organization，
  按事件类型分组的 distinct organization 不能直接相加。

## 9. 客服工单域（3 个核心表候选）

### 9.1 `support_ticket`

- **业务用途、粒度和主键**：一行代表一张结构化客服工单；业务主键为稳定 ticket ID。
- **关系与状态**：可关联 organization、merchant、consumer 和一个主要业务对象；当前状态至少区分 new、
  open、pending、solved、closed、cancelled。保存优先级、分类及最终有效 CSAT 分数和提交时间。
- **时间语义**：保存创建、当前首次有效人工响应、最近解决、关闭和更新时间；指标时间仍由交互和状态
  事件验证，不能只信当前派生时间。
- **事实类型和报表时间**：可变实体；CSAT 使用最终有效答卷，M1 不保存答卷修订历史。
- **测试与敏感性**：测试、垃圾或非生产工单排除；请求者身份和分类属于敏感信息，不保存正文。
- **依赖指标**：First Response Time、Resolution Time、Reopen Rate、CSAT、Open Ticket Count，以及客户
  风险关联分析。
- **重复风险**：工单可有多个状态事件和交互；工单数必须先按 ticket 去重，多对象关联不能被当作互斥分组。

### 9.2 `ticket_status_event`

- **业务用途、粒度和主键**：一行代表一次工单状态变化；业务主键为稳定 ticket status event ID。
- **关系与状态**：多对一关联 ticket，记录前后状态；事件类型包括 opened、pending、solved、closed、
  reopened、cancelled。reopened 必须保留，不能用当前状态覆盖。
- **时间语义**：区分状态生效和记录时间；Resolution Time、Reopen Rate 和 Open Ticket Count 使用生效时间。
- **事实类型和报表时间**：不可变事件事实；查询截止时间前最新有效事件决定 `as of` 状态。
- **测试与敏感性**：继承 ticket 测试标记并保留自身标记；不保存状态备注文本。
- **依赖指标**：Resolution Time、Reopen Rate、Open Ticket Count。
- **重复风险**：同一工单同周期多次解决或重开在分子、分母内各只去重一次；跨期重开不能回移到原解决期。

### 9.3 `ticket_interaction`

- **业务用途、粒度和主键**：一行代表一次结构化工单交互元数据；业务主键为稳定 interaction ID。
- **关系与状态**：多对一关联 ticket；actor type、visibility、human/bot、delivery status 用于识别首次有效
  人工公开响应。M1 不保存消息正文。
- **时间语义**：保存交互发生、发送成功和记录时间；First Response Time 使用首次成功的人工作用公开响应时刻。
- **事实类型和报表时间**：事件事实；自动回复、机器人、内部备注和发送失败均不结束首次响应计时。
- **测试与敏感性**：继承 ticket 测试标记；actor 标识属于敏感信息，正文明确不在范围内。
- **依赖指标**：First Response Time 及响应覆盖率。
- **重复风险**：重复投递回调会产生多个交互；必须按稳定来源标识去重后选择最早合格响应。

## 10. 指标到逻辑模型映射

以下所有指标均使用 USD、固定数据快照和全链路测试排除规则。后续 Gold SQL 必须显式引用
`insightcloud-business-definitions 1.0.0`。

### 10.1 SaaS 指标

| 指标 | 依赖实体 | 业务时间 | 状态过滤 | 重复风险 | Gold SQL 重点验证 |
| --- | --- | --- | --- | --- | --- |
| MRR | subscription、state event、plan、organization | 状态/价格变更生效时间，明确 `as of` | 有效、付费、非试用/暂停/已生效取消 | 多事件、多订阅和计划版本复制 | 事件时点重建、年付除以 12、期末取消生效前仍有效 |
| ARR | 与 MRR 相同 | 与 MRR 相同 | 与 MRR 相同 | 把支付收入当 ARR | 先正确计算 MRR 再乘 12，不跨快照求和 |
| New MRR | subscription state event | 首次激活生效时间 | 首次从非有效变有效 | 同时点未净额化、恢复误算新增 | 首次激活唯一性和年/月付规范化 |
| Expansion MRR | subscription state event | 变更生效时间 | 变更后仍有效且 MRR 正差额 | 同时点明细正负重复 | 订阅时点净额化后只取正差额 |
| Contraction MRR | subscription state event | 变更生效时间 | 订阅仍有效且 MRR 负差额绝对值 | 与 Churned MRR 混淆 | 仍有效条件及正数损失表达 |
| Churned MRR | subscription state event | 取消生效时间 | 取消使订阅失效 | 按取消安排时间统计 | 使用生效前全部 MRR，排除未生效取消 |
| Logo Churn Rate | organization、subscription、state event | 最后有效订阅失效时间；期初 `as of` | 期初至少一有效订阅，本期变为零 | 把订阅数当 organization 数 | organization 每期一次、分母期初快照、零分母为 null |
| Revenue Churn Rate | subscription state event | 取消生效时间；期初 `as of` | 合格 Churned MRR | 分组比率简单平均 | 本期 Churned MRR 除以期初 MRR |
| SaaS Revenue | invoice、payment attempt、subscription、organization | 支付成功时间 | succeeded，订阅费用部分，非税/一次性费用 | 账单多次尝试和重复回调 | 只计成功尝试、年付集中收入、与 MRR 分离 |

### 10.2 电商指标

| 指标 | 依赖实体 | 业务时间 | 状态过滤 | 重复风险 | Gold SQL 重点验证 |
| --- | --- | --- | --- | --- | --- |
| GMV | order、order item、product、merchant | 订单首次支付成功时间 | 已支付、截止快照未取消 | 多明细、多退款连接复制 | 唯一明细商品金额，不扣退款和税运费 |
| Order Count | order | 首次支付成功时间 | 已支付、未取消 | 明细展开后重复订单 | distinct order，多次支付尝试不重复 |
| AOV | order、order item | 与 GMV 相同 | 分子分母同一合格订单集合 | 分组 AOV 简单平均 | GMV/Order Count，零订单为 null |
| Refund Amount | refund、refund allocation、order item | 退款成功完成时间 | refund succeeded | 多明细退款重复总额 | 只计商品退款分配，支持跨月和部分退款 |
| Refund Rate | GMV 事实与退款事实 | 分子退款完成时间，分母支付时间 | 各自合格状态 | 把退款移回订单月 | 同期 Refund Amount/GMV，允许超过 100% |
| Merchant Net Sales | GMV 事实与退款事实 | 各自业务时间 | 各自合格状态 | 在订单粒度错误净额化 | 同期 GMV−Refund Amount，允许负值 |
| Platform Transaction Revenue | fee charge、order、merchant | 服务费成功时间 | fee succeeded | 订单多个收费尝试 | 不等于 GMV/净销售，退款不自动冲减 |

### 10.3 营销指标

| 指标 | 依赖实体 | 业务时间 | 状态过滤 | 重复风险 | Gold SQL 重点验证 |
| --- | --- | --- | --- | --- | --- |
| CAC | daily spend、attributed conversion、权威支付/订单主体 | 花费确认时间与首次付费转化时间 | confirmed spend；合格首次付费；渠道可判定 | 同一客户多次付费、多触达 | 分 SaaS/Commerce 身份，范围一致，零客户为 null |
| Attributed ROAS | daily spend、attributed conversion、权威收入事实 | 花费业务日期与收入转化时间 | cutoff 可见的 final spend revision；明确 SaaS 或 Commerce 收入 | 多触达复制收入、跨收入类型相加 | 168 小时物化归因、收入类型命名、零花费为 null |
| Attributed Revenue | attributed conversion、payment attempt 或 fee charge | 权威收入成功时间 | 唯一有效归因，权威收入合格 | 一个转化多归因 | SaaS/Commerce 分开，direct 与 unattributed 分开 |
| 新增付费客户数 | organization/consumer、attributed conversion、权威转化事实 | 首次成功订阅支付或首个合格订单支付时间 | 对应身份首次合格付费 | 混合 organization 与 consumer | 身份明确、主体去重、首付唯一性 |

所有营销指标还必须验证连续 168 小时窗口、同时间触达的稳定 ID 决胜规则、数据集开始处未成熟窗口
归入 unknown/unattributed，以及无合格非 direct 触达但身份和窗口完整时归入 direct。

### 10.4 产品使用指标

| 指标 | 依赖实体 | 业务时间 | 状态过滤 | 重复风险 | Gold SQL 重点验证 |
| --- | --- | --- | --- | --- | --- |
| Activation Rate | organization、member、campaign、merchant、order | 注册时间及三类条件首次满足时间 | 14 日左闭右开；三项中任意两项；成熟 cohort | 重复邀请、同类条件多次累计 | 第二个不同条件时刻，未成熟 pending 不进分母 |
| Active Organization Count | key product event、organization、身份映射 | 事件发生时间和明确 `as of` | 过去 30 日至少一合格事件 | 多事件类型重复 organization | 稳定事件去重、事件时映射、快照不可跨期相加 |
| 关键功能使用趋势 | key product event、organization | 事件发生时间 | V1 受控事件名/版本，排除重复、机器人和测试 | 重复上报、按类型 distinct 相加 | 事件量与 distinct organization 分开，版本和空周期稳定 |

### 10.5 客服指标

| 指标 | 依赖实体 | 业务时间 | 状态过滤 | 重复风险 | Gold SQL 重点验证 |
| --- | --- | --- | --- | --- | --- |
| First Response Time | ticket、interaction | ticket 创建至首次合格响应 | 人工、公开、发送成功；排除 bot/内部备注 | 重复投递或选错响应 | 24×7 实时、未响应为 null、同时披露覆盖率 |
| Resolution Time | ticket、status event | 创建至截止时仍保持解决/关闭的最后解决时间 | 已解决/关闭且之后未重开未解决 | 选择首次解决而忽略重开 | 包含等待和重开，未完成为 null，披露覆盖率 |
| Reopen Rate | status event、ticket | 分子重开时间，分母解决时间 | 周期内 distinct ticket | 同一工单多次事件重复 | 分子分母分别去重，跨期可超过 100% |
| CSAT | ticket 最终有效答卷属性 | 答卷提交时间 | 1—5 分最终有效答卷 | 对分组均值简单平均 | 算术平均、无样本 null、同时给有效答卷数 |
| Open Ticket Count | ticket、status event | 截止 `as of` 最新状态 | 非 solved/closed/cancelled | 跨快照求和、重开遗漏 | 最新事件重建，重开重新为 open |

## 11. 确定性业务现象的数据需求

| # | 必须可复现的现象 | 最小模型支撑 |
| ---: | --- | --- |
| 1 | Enterprise 套餐流失增加 | plan version、subscription state event、organization |
| 2 | 流失前产品使用下降 | key product event 与 churn event 按 organization、时间窗聚合后连接 |
| 3 | 流失客户高优先级工单增加 | ticket、status event 与 churn organization 分群连接 |
| 4 | 渠道花费增加但付费转化下降 | daily spend 与首次付费 attributed conversion 分别按渠道周期聚合 |
| 5 | 活动 Attributed ROAS 明显下降 | campaign spend、attributed revenue 和明确收入类型 |
| 6 | 商品类别退款率异常上升 | product category code、order item、refund allocation |
| 7 | 商家 GMV 增长但退款和营销成本上升 | merchant—organization 映射、订单、退款、campaign spend |
| 8 | SaaS 实际收入下降但 MRR 未同步下降 | payment attempt 与 subscription state event 的不同时间语义 |
| 9 | 新 organization 注册增加但激活率下降 | organization cohort 和三项激活条件事实 |
| 10 | 测试身份和交易不进入指标 | 各身份和事实的显式测试标记及排除链 |
| 11 | 跨月订单退款 | order 首次支付时间与 refund 完成时间分别归期 |
| 12 | 无触点的 unattributed 转化 | attributed conversion 的窗口不完整或身份不可判定原因 |
| 13 | direct 与 unknown/unattributed 不混淆 | channel 分类和明确 attribution result/reason |
| 14 | 工单重新开启 | ticket status event 的 solved→reopened→solved 或未解决序列 |
| 15 | 年付 MRR 按月折算 | annual plan version、周期费用及 state event 规范化 MRR |

## 12. 模型设计专项检查

### 12.1 多对多与重复聚合

- 订单—明细、订单—退款、活动—花费、活动—触达、转化—候选触达、工单—状态事件均是一对多。
- 任何跨域金额或计数必须先在权威事实粒度聚合，再连接聚合结果。
- refund allocation 只用于分配退款商品金额，不能承载或复制订单 GMV。
- attributed conversion 保证一个权威转化只有一个有效 V1 归因结果。
- merchant 有效区间和事件时点映射保证单一 organization 归属，不允许重叠区间。

### 12.2 状态与事件

- subscription 和 ticket 的当前状态与事件历史同时存在；历史指标只使用事件历史重建。
- invoice、order 和 refund 保存当前状态及关键时间，M1 固定数据快照决定截止时已知状态。
- 支付尝试、退款成功、服务费成功、营销触达、产品事件和工单状态变化均保留独立事实。
- 当前状态字段不能覆盖首次支付、取消生效、退款完成、解决或重开时间。

### 12.3 跨期与收入边界

- 退款按完成期统计，不回移订单支付期；GMV 不因退款减少。
- MRR/ARR 是 `as of` 规范化经常性规模，SaaS Revenue 是支付成功期实际订阅费用收入。
- GMV、Merchant Net Sales 和 Platform Transaction Revenue 分别表示交易规模、周期净销售规模和
  平台服务费收入，不互换、不直接相加。

### 12.4 归因、时区与测试排除

- 168 小时使用真实时刻比较，触达可早于报表期，转化仍归入转化期。
- direct 只用于身份和窗口完整但没有合格非 direct 触达的情况；数据不完整使用
  unknown/unattributed。
- UTC 保存与 `America/Los_Angeles` 报表边界并存，涵盖夏令时边界。
- 测试排除同时检查事实自身与唯一归属链，缺失关键映射不能通过猜测补齐。

### 12.5 Gold SQL 稳定性

- 所有事实有稳定业务标识、明确粒度、确定性时间和状态集合。
- 所有比率可追溯到基础分子、分母；零分母规则与空周期规则明确。
- Gold 数据快照固定版本和截止时间，迟到或更正不会使同一基线漂移。
- 同时间触达、重复回调、重复上报和多次状态事件均有确定性去重或排序规则。
- M1 暂不支持的能力不会被 Gold Questions 或后续 Gold SQL 临时补充定义。

## 13. M1 暂不实现与未来扩展

| 对象 | 当前决定 | 未来触发条件 |
| --- | --- | --- |
| MRR/活跃企业/Open Ticket 周期快照 | 不落表，按事件重建 | 数据规模证明重建无法满足性能目标 |
| 商品分类维表 | product 保存受控 category code | 分类需要层级、版本或独立治理 |
| organization member 邀请事件历史 | 保存首次成功邀请和关系生命周期 | 需要分析重复邀请或邀请渠道 |
| 完整订单状态历史 | 保存关键时刻和快照内当前状态 | 需要历史任意时点订单状态审计 |
| CSAT 答卷历史 | ticket 保存最终有效答卷 | 需要问卷修订、覆盖率流程或多问卷版本 |
| 广告组与素材 | 不实现 | Gold Questions 明确需要且业务层级获批准 |
| 客服正文与 RAG | 不实现 | 新里程碑完成权限、脱敏和文本治理设计 |

上述扩展不得在 M1.0 文档之外自动实施。
