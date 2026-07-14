# M1.0 Gold Questions 规划目录

## 1. 文档目的与边界

本文规划 InsightCloud V1 后续 Text2SQL、RAG、Agent 和 Evaluation 使用的 Gold
Questions。所有问题引用 `insightcloud-business-definitions 1.0.0`，并映射到
[`m1-logical-data-model.md`](m1-logical-data-model.md) 的逻辑实体。

本文不提供 Gold SQL、查询实现、种子数据或具体数值答案。问题中的时间范围、分组和预期结果形态
是后续确定性数据集的设计输入，不代表当前已有真实业务结果。

## 2. 统一约定

- 业务时区为 `America/Los_Angeles`，数据时刻以 UTC 保存并在报表时转换。
- 除非问题另有说明，数据快照截止时间规划为 `2026-01-15 00:00:00` 业务时区，快照版本后续由
  种子数据里程碑确定。
- “月末”表示下一自然月开始前的最后状态，并以该下一月起点作为明确 `as of` 边界。
- 所有正式指标排除事实自身及归属链上的测试 organization、member、consumer、merchant、order、
  payment、refund、campaign 和 ticket。
- 预期指标、实体、时间和状态均以冻结定义为准。标记为需要澄清的问题在澄清前不应生成查询。
- L3 原因分析只要求下钻可观察关联，不允许把相关性表述为因果关系。

## 3. 难度与类型分配

### 3.1 按数据域和难度

| 数据域 | L1 | L2 | L3 | 合计 |
| --- | ---: | ---: | ---: | ---: |
| SaaS | 3 | 4 | 2 | 9 |
| 商城 | 3 | 3 | 2 | 8 |
| 营销 | 2 | 4 | 2 | 8 |
| 企业增长与产品使用 | 3 | 3 | 2 | 8 |
| 客服 | 3 | 3 | 1 | 7 |
| 跨域 | 0 | 3 | 5 | 8 |
| **合计** | **14** | **20** | **14** | **48** |

### 3.2 按主问题类型

| 主问题类型 | 数量 |
| --- | ---: |
| 指标查询 | 4 |
| 趋势分析 | 4 |
| 分群比较 | 4 |
| 异常检测 | 4 |
| 漏斗分析 | 4 |
| 收入变化分析 | 4 |
| 客户流失分析 | 4 |
| 营销效率分析 | 4 |
| 退款与商品分析 | 4 |
| 产品使用和激活分析 | 4 |
| 客服与客户风险分析 | 4 |
| 跨域归因分析 | 4 |
| **合计** | **48** |

## 4. 后续种子数据现象标识

| 标识 | 必须稳定复现的业务现象 |
| --- | --- |
| P01 | 某段时间 Enterprise 套餐流失增加 |
| P02 | 流失客户在此前出现产品使用下降 |
| P03 | 流失客户同时出现高优先级客服工单增加 |
| P04 | 某营销渠道花费增加，但付费转化下降 |
| P05 | 某活动 ROAS 明显下降 |
| P06 | 某商品类别退款率异常上升 |
| P07 | 某商家 GMV 增长，但退款和营销成本同时上升 |
| P08 | 某时间段 SaaS 实际收入下降，但 MRR 没有同步下降 |
| P09 | 某批新 organization 注册增加，但激活率下降 |
| P10 | 测试 organization、consumer 和交易不能进入正式指标 |
| P11 | 存在跨月订单退款 |
| P12 | 无营销触点且应归入 unknown/unattributed 的转化 |
| P13 | 存在 direct 转化，且不能与 unknown/unattributed 混淆 |
| P14 | 存在客服工单重新开启 |
| P15 | 存在年付订阅，MRR 按月折算 |

表格中的“基线”表示后续种子数据需要包含正常业务路径、零值或可对照分群，不额外引入新口径。

## 5. SaaS Gold Questions（9 个）

| ID | 自然语言问题 | 难度 | 数据域 | 类型 | 业务意图 | 期望指标 | 期望逻辑实体 | 业务时间范围 | 预期结果形态 | 歧义与澄清 | 种子现象 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GQ-SAA-001 | 截至 2025 年 6 月末，各套餐的 MRR 和 ARR 分别是多少？ | L1 | SaaS | 指标查询 | 获得同一快照时点的经常性收入规模 | MRR、ARR | organization、saas_plan_version、subscription、subscription_state_event | `as of` 2025-07-01 00:00 | 按套餐的金额表和总计 | 否；明确为快照指标 | P15、P10 |
| GQ-SAA-002 | 2025 年第二季度每个月的 SaaS Revenue 是多少？ | L1 | SaaS | 指标查询 | 查看实际成功收款的订阅费用收入 | SaaS Revenue | subscription_invoice、invoice_payment_attempt、subscription、organization | 2025-04-01 至 2025-07-01 | 月度时间序列 | 否；已明确实际支付收入 | P10、基线成功与失败支付 |
| GQ-SAA-003 | 2025 年第二季度每个月的 Churned MRR 是多少？ | L1 | SaaS | 客户流失分析 | 衡量取消生效带来的经常性收入损失 | Churned MRR | subscription、subscription_state_event、saas_plan_version | 2025-04-01 至 2025-07-01 | 月度金额序列 | 否；按取消生效时间 | P01、基线未生效取消 |
| GQ-SAA-004 | 2025 年 1—6 月各月末 MRR 和 ARR 的趋势如何，按套餐展示？ | L2 | SaaS | 趋势分析 | 比较多快照的规模变化但不跨快照求和 | MRR、ARR | organization、saas_plan_version、subscription、subscription_state_event | 2025-02-01 至 2025-07-01 的六个月末 `as of` | 套餐分组的双指标时间序列 | 否；每月独立重建快照 | P15、基线月付套餐 |
| GQ-SAA-005 | 2025 年 5 月到 6 月，New、Expansion、Contraction 和 Churned MRR 如何解释月末 MRR 的变化？ | L2 | SaaS | 收入变化分析 | 用互斥变动量构建 MRR 变化桥 | MRR、New MRR、Expansion MRR、Contraction MRR、Churned MRR | subscription、subscription_state_event、plan、organization | 2025-05-01 至 2025-07-01，月初/月末快照 | 变化桥表及各变动类型贡献 | 否；不要求取消后再次激活 | P01、P15、基线升级降级 |
| GQ-SAA-006 | 2025 年第二季度各套餐的 Logo Churn Rate 和 Revenue Churn Rate 有何差异？ | L2 | SaaS | 分群比较 | 区分客户数量流失与收入流失 | Logo Churn Rate、Revenue Churn Rate | organization、plan、subscription、subscription_state_event | 期初 2025-04-01 `as of`，事件期至 2025-07-01 | 套餐比较表，含基础分子分母 | 否；套餐需按期初有效订阅归属 | P01、基线多订阅 organization |
| GQ-SAA-007 | 2025 年 4—6 月 SaaS Revenue 下降时，月末 MRR 是否同步下降？ | L2 | SaaS | 收入变化分析 | 验证实际支付收入与经常性规模的时间差 | SaaS Revenue、MRR | invoice_payment_attempt、subscription、subscription_state_event、plan | 2025-04-01 至 2025-07-01，收入按月、MRR 按月末 | 两条时间序列和差异说明 | 否；禁止把两指标相加或互换 | P08、P15 |
| GQ-SAA-008 | 2025 年 5—6 月 Enterprise 套餐流失是否比第一季度明显增加，增加集中在哪个月？ | L3 | SaaS | 异常检测 | 验证已设计流失异常并定位时间 | Churned MRR、Logo Churn Rate、Revenue Churn Rate | plan、organization、subscription、subscription_state_event | 基线 2025-01-01 至 2025-04-01，对比 2025-05-01 至 2025-07-01 | 对比趋势、异常月份和基础计数 | 否；“明显”由确定性数据差异呈现，不设统计显著性 | P01 |
| GQ-SAA-009 | Enterprise 客户在 2025 年第二季度为什么流失，能否按取消前的订阅变化下钻？ | L3 | SaaS | 客户流失分析 | 下钻流失前的扩张、收缩与取消序列 | Churned MRR、Contraction MRR、Logo Churn Rate | organization、plan、subscription、subscription_state_event | 流失事件前 90 日及 2025 年第二季度 | organization 级事件序列和分群摘要 | 是；必须将“为什么”澄清为可观察变化，不能声称因果 | P01、基线多阶段订阅变更 |

## 6. 商城 Gold Questions（8 个）

| ID | 自然语言问题 | 难度 | 数据域 | 类型 | 业务意图 | 期望指标 | 期望逻辑实体 | 业务时间范围 | 预期结果形态 | 歧义与澄清 | 种子现象 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GQ-COM-001 | 2025 年 6 月商城的 GMV、Order Count 和 AOV 分别是多少？ | L1 | 商城 | 指标查询 | 获得合格支付订单的规模、数量和客单价 | GMV、Order Count、AOV | commerce_order、commerce_order_item、product、merchant、consumer | 2025-06-01 至 2025-07-01，按首次支付成功时间 | 三个标量及 AOV 分子分母 | 否 | P10、基线多明细订单 |
| GQ-COM-002 | 2025 年 6 月成功退款金额和 Refund Rate 是多少，其中多少退款对应 5 月支付的订单？ | L1 | 商城 | 退款与商品分析 | 量化本期退款并验证跨期退款 | Refund Amount、Refund Rate、GMV | refund、refund_item_allocation、order、order_item | 退款期 2025-06-01 至 2025-07-01；订单支付期单列 | 标量、跨期来源拆分和基础分母 | 否；退款按完成时间 | P11、P10 |
| GQ-COM-003 | 2025 年 6 月各商家的 Merchant Net Sales 是多少？ | L1 | 商城 | 退款与商品分析 | 查看同期交易规模扣除成功退款后的净销售 | Merchant Net Sales、GMV、Refund Amount | merchant、order、order_item、refund、refund_item_allocation | 2025-06-01 至 2025-07-01 | 商家分组金额表 | 否；允许负值 | P11、基线无退款商家 |
| GQ-COM-004 | 2025 年 1—6 月 GMV、Order Count 和 AOV 的月度趋势如何？ | L2 | 商城 | 趋势分析 | 观察交易规模和订单结构变化 | GMV、Order Count、AOV | order、order_item | 2025-01-01 至 2025-07-01 | 三指标月度时间序列 | 否；AOV 每月从基础事实重算 | 基线季节性变化、P10 |
| GQ-COM-005 | 2025 年第二季度各商家的 GMV、Refund Amount、Merchant Net Sales 和 Platform Transaction Revenue 有何差异？ | L2 | 商城 | 分群比较 | 比较商家交易规模、退款和平台收入 | GMV、Refund Amount、Merchant Net Sales、Platform Transaction Revenue | merchant、order、order_item、refund、refund_allocation、platform_fee_charge | 2025-04-01 至 2025-07-01，各指标按自身业务时间 | 商家比较表和排名 | 否；四项分别聚合后连接 | P07、P11 |
| GQ-COM-006 | 2025 年 6 月哪个商品类别的 Refund Rate 相比 4—5 月异常上升？ | L2 | 商城 | 异常检测 | 定位退款率异常类别并展示基础金额 | Refund Rate、Refund Amount、GMV | product、order_item、order、refund、refund_item_allocation | 基线 2025-04-01 至 2025-06-01，对比 2025-06-01 至 2025-07-01 | 类别趋势、异常排序和分子分母 | 否；类别使用受控 category code | P06、P11 |
| GQ-COM-007 | 2025 年第二季度从订单创建、支付到完成和退款的漏斗转化率是多少？ | L3 | 商城 | 漏斗分析 | 规划订单生命周期漏斗 | Order Count；其他阶段计数尚未冻结为指标 | order、order_item、refund | 2025-04-01 至 2025-07-01，需确认 cohort 起点与观察截止 | 阶段计数和转化率漏斗 | 是；V1 未冻结创建到完成漏斗的分母、窗口和退款阶段定义，必须先澄清 | 基线成功、失败、取消、部分退款路径 |
| GQ-COM-008 | 2025 年第二季度 GMV 增长最多的商家，其 Merchant Net Sales 和 Platform Transaction Revenue 是否也同步增长？ | L3 | 商城 | 收入变化分析 | 区分商家交易增长、退款后净销售和平台收入 | GMV、Merchant Net Sales、Platform Transaction Revenue、Refund Amount | merchant、order、order_item、refund、refund_allocation、platform_fee_charge | 2025 年第一季度对比第二季度 | 商家排名、季度变化表和非同步项 | 否；三类金额不得合并 | P07、P11 |

## 7. 营销 Gold Questions（8 个）

| ID | 自然语言问题 | 难度 | 数据域 | 类型 | 业务意图 | 期望指标 | 期望逻辑实体 | 业务时间范围 | 预期结果形态 | 歧义与澄清 | 种子现象 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GQ-MKT-001 | 2025 年第二季度各渠道的 SaaS CAC 是多少？ | L1 | 营销、SaaS | 营销效率分析 | 比较获取首付 organization 的周期效率 | SaaS CAC、SaaS 新增付费客户数、实际花费 | channel、campaign、daily_spend、attributed_conversion、invoice_payment_attempt、organization | 2025-04-01 至 2025-07-01 | 渠道表，含花费、客户数和 CAC | 否；明确 SaaS 身份 | P04、P10 |
| GQ-MKT-002 | 2025 年第二季度各渠道的 Commerce CAC 是多少？ | L1 | 营销、商城 | 营销效率分析 | 比较获取首购 consumer 的周期效率 | Commerce CAC、Commerce 新增付费客户数、实际花费 | channel、campaign、daily_spend、attributed_conversion、order、consumer | 2025-04-01 至 2025-07-01 | 渠道表，含花费、客户数和 CAC | 否；明确 consumer 身份 | P04、P10 |
| GQ-MKT-003 | 2025 年 6 月 SaaS Revenue 和 Commerce Revenue 分别归因到了哪些渠道，direct 和 unknown/unattributed 各占多少？ | L2 | 营销、SaaS、商城 | 跨域归因分析 | 核对两类收入归因分布和未归因披露 | Attributed SaaS Revenue、Attributed Commerce Revenue | touch、attributed_conversion、channel、payment_attempt、platform_fee_charge | 2025-06-01 至 2025-07-01，触达回看 168 小时 | 两套独立渠道分布和未归因金额 | 否；收入类型分别展示 | P12、P13 |
| GQ-MKT-004 | 2025 年第二季度从营销触达到新增付费客户的漏斗如何，SaaS 和 Commerce 分别展示？ | L2 | 营销、SaaS、商城 | 漏斗分析 | 比较两种身份的触达与首次付费阶段 | 新增付费客户数；触达主体数为阶段基础计数 | touch、attributed_conversion、organization、consumer、payment_attempt、order | 2025-04-01 至 2025-07-01，触达回看 168 小时 | 两个身份范围的阶段计数漏斗 | 否；已明确不混合身份，漏斗只展示基础计数 | P04、P12、P13 |
| GQ-MKT-005 | 2025 年 5—6 月哪个渠道花费上升但新增付费客户数下降，SaaS 和 Commerce 分别如何？ | L2 | 营销、SaaS、商城 | 营销效率分析 | 定位投入增加但首付转化下降的渠道 | 实际花费、SaaS/Commerce 新增付费客户数、CAC | channel、campaign、daily_spend、attributed_conversion、权威转化事实 | 2025-05-01 至 2025-07-01，按月比较 | 渠道变化表和反向变化标记 | 否；两个身份分别计算 | P04 |
| GQ-MKT-006 | 2025 年 6 月哪个活动的 ROAS 相比 4—5 月明显下降？ | L2 | 营销 | 异常检测 | 定位活动效率异常 | ROAS、Attributed Revenue、实际花费 | campaign、daily_spend、attributed_conversion、权威收入事实 | 基线 2025-04-01 至 2025-06-01，对比 6 月 | 活动趋势和异常排序 | 是；问题未指定 SaaS 或 Commerce Revenue，必须先澄清收入类型 | P05 |
| GQ-MKT-007 | 2025 年第二季度各活动的 ROAS 表现如何，哪些活动最有效？ | L3 | 营销 | 营销效率分析 | 对活动效率进行排名和下钻 | ROAS、Attributed Revenue、实际花费 | campaign、channel、daily_spend、attributed_conversion、权威收入事实 | 2025-04-01 至 2025-07-01 | 活动排名、分子分母和渠道分组 | 是；“ROAS”必须明确 SaaS 或 Commerce，不得混合排名 | P05、基线零花费或零收入活动 |
| GQ-MKT-008 | 给定 2025 年 6 月的转化，哪些应归为 direct，哪些应归为 unknown/unattributed，边界案例是什么？ | L3 | 营销、SaaS、商城 | 跨域归因分析 | 验证 168 小时窗口、身份完整性和未成熟历史 | 归因结果、Attributed Revenue、新增付费客户数 | touch、attributed_conversion、channel、权威转化事实、organization、consumer | 转化期 2025-06-01 至 2025-07-01，逐笔回看 168 小时 | 按归因结果和原因代码的案例表 | 否；规则已冻结，不能把未知伪装成 direct | P12、P13、基线同时间触达决胜 |

## 8. 企业增长与产品使用 Gold Questions（8 个）

| ID | 自然语言问题 | 难度 | 数据域 | 类型 | 业务意图 | 期望指标 | 期望逻辑实体 | 业务时间范围 | 预期结果形态 | 歧义与澄清 | 种子现象 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GQ-PRD-001 | 2025 年第二季度已完成 14 日观察窗口的注册 organization，其 Activation Rate 是多少？ | L1 | 企业增长 | 产品使用和激活分析 | 衡量成熟注册 cohort 的激活结果 | Activation Rate、Activated Organization Count | organization、member、campaign、merchant、order | 注册期 2025-04-01 至 2025-07-01，仅纳入截止快照已成熟 cohort | 标量、分子分母及 pending 数 | 否 | P09、P10 |
| GQ-PRD-002 | 截至 2025 年 7 月 1 日的 Active Organization Count 是多少？ | L1 | 产品使用 | 产品使用和激活分析 | 获得滚动 30 日活跃企业快照 | Active Organization Count | key_product_event、organization、member、merchant | `[2025-06-01, 2025-07-01)`，`as of` 7 月 1 日 | 标量及合格事件覆盖 | 否 | P02、P10 |
| GQ-PRD-003 | 2025 年 6 月各关键功能的事件次数和使用 organization 数是多少？ | L1 | 产品使用 | 产品使用和激活分析 | 了解关键功能使用规模 | 关键功能使用趋势的基础事件数和 distinct organization 数 | key_product_event、organization | 2025-06-01 至 2025-07-01 | 功能分组表 | 否；两种计数分别展示 | P02、基线重复上报 |
| GQ-PRD-004 | 2025 年 1—6 月各关键功能使用 organization 数的趋势如何？ | L2 | 产品使用 | 趋势分析 | 发现功能采用随时间的变化 | 关键功能使用趋势 | key_product_event、organization | 2025-01-01 至 2025-07-01 | 月度功能时间序列 | 否；跨功能 distinct 数不相加 | P02、基线空月份 |
| GQ-PRD-005 | 2025 年第二季度不同注册来源和套餐的 organization Activation Rate 有何差异？ | L2 | 企业增长、营销、SaaS | 分群比较 | 比较成熟 cohort 的激活表现 | Activation Rate | organization、member、campaign、merchant、order、attributed_conversion、subscription | 注册期 2025-04-01 至 2025-07-01，观察至各自第 14 日 | 来源与套餐交叉分组表，含分子分母 | 是；注册来源若无法由冻结归因唯一确定，应使用 unknown 或澄清来源定义 | P09、P12 |
| GQ-PRD-006 | 2025 年第二季度注册 organization 从完成 0 项、1 项到满足 2 项激活条件的漏斗如何？ | L2 | 企业增长 | 漏斗分析 | 展示三项激活条件的成熟 cohort 进展 | Activation Rate、Activated Organization Count、条件阶段计数 | organization、member、campaign、merchant、order | 注册期 2025-04-01 至 2025-07-01，仅成熟 cohort | 互斥阶段计数漏斗和最终激活率 | 否；条件按不同类型去重 | P09、基线三种条件组合 |
| GQ-PRD-007 | 2025 年 5—6 月新注册 organization 增加时，成熟 cohort 的 Activation Rate 是否下降？ | L3 | 企业增长 | 产品使用和激活分析 | 验证注册增长与激活下降的反向变化 | 注册 organization 数、Activation Rate、Activated Organization Count | organization、member、campaign、merchant、order | 2025-05-01 至 2025-07-01，按注册月 cohort 并等待 14 日成熟 | cohort 趋势、分子分母和变化方向 | 否；未成熟 cohort 不进入率 | P09 |
| GQ-PRD-008 | 不同首次付费归因渠道的 organization，在注册后 14 日内 Activation Rate 是否有差异？ | L3 | 企业增长、营销、SaaS | 跨域归因分析 | 连接首次付费归因和企业激活 cohort | Activation Rate、SaaS 新增付费客户数 | organization、attributed_conversion、payment_attempt、member、campaign、merchant、order | 2025 年第二季度注册 cohort，观察 14 日并按首次付费归因分组 | 渠道分群的激活率和基础样本数 | 否；direct 与 unknown/unattributed 分开 | P09、P12、P13 |

## 9. 客服 Gold Questions（7 个）

| ID | 自然语言问题 | 难度 | 数据域 | 类型 | 业务意图 | 期望指标 | 期望逻辑实体 | 业务时间范围 | 预期结果形态 | 歧义与澄清 | 种子现象 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GQ-SUP-001 | 截至 2025 年 7 月 1 日的 Open Ticket Count 是多少？ | L1 | 客服 | 指标查询 | 获得指定时点未解决工单负荷 | Open Ticket Count | support_ticket、ticket_status_event | `as of` 2025-07-01 00:00 | 标量及当前状态分布 | 否 | P14、P10 |
| GQ-SUP-002 | 2025 年 6 月创建工单的平均 First Response Time 和 Resolution Time 是多少？ | L1 | 客服 | 客服与客户风险分析 | 衡量响应与解决效率及样本覆盖 | First Response Time、Resolution Time | support_ticket、ticket_interaction、ticket_status_event | 工单创建 cohort 2025-06-01 至 2025-07-01，截止快照观察 | 两个均值、合格样本数和覆盖率 | 否；统一 24×7 实际经过时间 | 基线未响应、未解决和机器人回复 |
| GQ-SUP-003 | 2025 年第二季度的 Reopen Rate 和 CSAT 分别是多少？ | L1 | 客服 | 客服与客户风险分析 | 查看重开与满意度表现 | Reopen Rate、CSAT | support_ticket、ticket_status_event | 状态事件和答卷提交期 2025-04-01 至 2025-07-01 | 两个标量及各自基础样本数 | 否；两指标时间字段不同 | P14、基线无答卷工单 |
| GQ-SUP-004 | 2025 年 1—6 月 First Response Time 和 Resolution Time 的月度趋势如何？ | L2 | 客服 | 趋势分析 | 观察工单创建 cohort 的服务效率变化 | First Response Time、Resolution Time | ticket、interaction、status_event | 工单创建月 2025-01-01 至 2025-07-01，统一截止快照 | 月度均值、样本数和覆盖率 | 否；整体值从工单级时长重算 | P03、P14 |
| GQ-SUP-005 | 2025 年第二季度不同优先级和问题分类的 First Response Time、Resolution Time 和 CSAT 有何差异？ | L2 | 客服 | 分群比较 | 比较支持体验分群 | First Response Time、Resolution Time、CSAT | ticket、interaction、status_event | 工单创建期与答卷提交期分别披露 | 优先级和分类比较表，含样本量 | 否；不可对分组均值再简单平均 | P03、基线多分类工单 |
| GQ-SUP-006 | 2025 年 5—6 月高优先级工单是否异常增加，集中在哪些问题分类？ | L2 | 客服 | 异常检测 | 定位高优先级支持负荷异常 | 工单创建计数、Open Ticket Count | ticket、status_event | 基线 2025-01-01 至 2025-05-01，对比 5—6 月；Open 使用月末 `as of` | 趋势、分类排名和月末快照 | 否；工单创建数是基础事实计数，不替代 Open Ticket Count | P03 |
| GQ-SUP-007 | 2025 年第二季度重新开启的工单，后续 Resolution Time 和 CSAT 表现如何？ | L3 | 客服 | 客服与客户风险分析 | 评估重开 cohort 的后续处理表现 | Reopen Rate、Resolution Time、CSAT | ticket、status_event、interaction | 重开事件 2025-04-01 至 2025-07-01，观察至快照截止 | 重开工单 cohort 表、均值和覆盖率 | 否；未再次解决的时长为 null | P14、基线重开后未解决与再次解决 |

## 10. 跨域 Gold Questions（8 个）

| ID | 自然语言问题 | 难度 | 数据域 | 类型 | 业务意图 | 期望指标 | 期望逻辑实体 | 业务时间范围 | 预期结果形态 | 歧义与澄清 | 种子现象 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GQ-XDM-001 | 2025 年第二季度 SaaS Revenue 和 Commerce Revenue 各自如何变化，是否存在不同步月份？ | L2 | SaaS、商城 | 收入变化分析 | 并列比较两种平台收入而不混合口径 | SaaS Revenue、Commerce Revenue | payment_attempt、subscription、platform_fee_charge、order | 2025-04-01 至 2025-07-01，各按成功时间 | 两条月度序列和不同步标记 | 否；不提供未批准的合计收入 | P08、基线两类收入反向变化 |
| GQ-XDM-002 | 2025 年第二季度各 merchant 的营销花费、Attributed Commerce Revenue 和 Commerce ROAS 如何？ | L2 | 商城、营销 | 跨域归因分析 | 连接商家归属、活动成本和平台交易收入 | Attributed Commerce Revenue、Commerce ROAS、实际花费 | merchant、organization、campaign、daily_spend、attributed_conversion、platform_fee_charge | 2025-04-01 至 2025-07-01 | merchant 比较表，含未归因披露 | 否；先按活动/收入事实聚合再连接 merchant | P07、P12、P13 |
| GQ-XDM-003 | 2025 年第二季度从营销触达、organization 注册、激活到 SaaS 首次付费的漏斗如何？ | L2 | 营销、企业增长、SaaS | 漏斗分析 | 规划组织获客和激活的跨域阶段表现 | Activation Rate、SaaS 新增付费客户数、阶段基础计数 | touch、organization、member、campaign、merchant、order、payment_attempt、attributed_conversion | 注册 cohort 2025-04-01 至 2025-07-01，激活观察 14 日，触达回看 168 小时 | 阶段计数、成熟样本和转化漏斗 | 是；触达到注册的分母与观察窗口未在 V1 冻结，执行前需确认 | P04、P09、P12 |
| GQ-XDM-004 | 2025 年第二季度流失的 Enterprise organization，在流失前 60 日是否出现关键产品使用下降？ | L3 | SaaS、产品使用 | 客户流失分析 | 验证流失前使用变化的可观察关联 | Churned MRR、Logo Churn Rate、关键功能使用趋势 | plan、subscription、subscription_state_event、key_product_event、organization | 流失事件 2025-04-01 至 2025-07-01；每个事件前 60 日对比更早 60 日 | 流失 organization 分群、事件趋势和对照组 | 否；结论只描述关联 | P01、P02 |
| GQ-XDM-005 | 2025 年第二季度流失的 Enterprise organization，在流失前 60 日是否出现更多高优先级客服工单？ | L3 | SaaS、客服 | 客户流失分析 | 验证支持问题与流失的可观察关联 | Logo Churn Rate、Churned MRR、工单创建计数、Open Ticket Count | plan、subscription、state_event、ticket、ticket_status_event、organization | 流失事件 2025-04-01 至 2025-07-01；流失前 60 日 | 流失与未流失分群比较、基础样本 | 否；不声称客服导致流失 | P01、P03、P14 |
| GQ-XDM-006 | 2025 年 6 月退款率异常上升的商品类别，相关客服工单量和问题分类是否也发生变化？ | L3 | 商城、客服 | 退款与商品分析 | 联合下钻退款异常与结构化客服问题 | Refund Rate、Refund Amount、工单创建计数 | product、order_item、order、refund、refund_allocation、ticket、merchant | 退款和工单期 2025-06-01 至 2025-07-01，对比 4—5 月 | 类别趋势、工单分类表和关联说明 | 否；工单需有可靠商品或订单关联，否则披露不可连接 | P06、P11 |
| GQ-XDM-007 | 2025 年第二季度哪个 merchant 的 GMV 增长最多，同时退款和营销成本也上升？ | L3 | 商城、营销 | 退款与商品分析 | 验证增长质量和获客成本压力 | GMV、Refund Amount、Refund Rate、Merchant Net Sales、实际花费 | merchant、organization、order、order_item、refund、refund_allocation、campaign、daily_spend | 2025 年第一季度对比第二季度 | merchant 排名、季度变化和三类基础金额 | 否；交易和花费先分域聚合 | P07、P11 |
| GQ-XDM-008 | 截至 2025 年 7 月 1 日，哪些 Enterprise organization 同时出现近 30 日产品使用下降和未关闭高优先级工单？ | L3 | SaaS、产品使用、客服 | 客服与客户风险分析 | 找出同时存在两个可观察风险信号的企业，不创建健康分数 | Active Organization Count 的基础事件、Open Ticket Count、关键功能使用趋势 | plan、subscription、organization、key_product_event、ticket、ticket_status_event | 产品事件观察至 2025-07-01，比较前后两个 30 日窗口；工单 `as of` 同时点 | organization 级条件列表和聚合计数 | 是；若要求“风险最高”或健康评分必须澄清，V1 未定义风险模型 | P02、P03、P14 |

## 11. 现象到问题覆盖索引

| 现象 | 主要问题 ID | 边界验证 |
| --- | --- | --- |
| P01 Enterprise 流失增加 | GQ-SAA-003、GQ-SAA-008、GQ-XDM-004、GQ-XDM-005 | 套餐、取消生效时间、organization 去重 |
| P02 流失前使用下降 | GQ-PRD-002、GQ-PRD-004、GQ-XDM-004、GQ-XDM-008 | 事件发生时间、60 日窗口、非因果措辞 |
| P03 高优先级工单增加 | GQ-SUP-004、GQ-SUP-006、GQ-XDM-005、GQ-XDM-008 | 创建计数与 Open 快照分开 |
| P04 花费增加转化下降 | GQ-MKT-001、GQ-MKT-002、GQ-MKT-005、GQ-XDM-003 | SaaS/Commerce 身份分开、同期分子分母 |
| P05 活动 ROAS 下降 | GQ-MKT-006、GQ-MKT-007 | 收入类型必须明确、零花费为 null |
| P06 类别退款率上升 | GQ-COM-006、GQ-XDM-006 | 商品退款分配、跨期退款 |
| P07 GMV 增长伴随退款和营销成本上升 | GQ-COM-005、GQ-COM-008、GQ-XDM-002、GQ-XDM-007 | merchant 映射、分域聚合 |
| P08 SaaS Revenue 下降但 MRR 未下降 | GQ-SAA-007、GQ-XDM-001 | 支付时间与快照时点分开 |
| P09 注册增加但激活率下降 | GQ-PRD-001、GQ-PRD-006、GQ-PRD-007、GQ-XDM-003 | 14 日成熟 cohort、两种不同条件 |
| P10 测试数据排除 | GQ-SAA-001、GQ-SAA-002、GQ-COM-001、GQ-MKT-001、GQ-PRD-001、GQ-SUP-001 | 事实和归属链显式标记 |
| P11 跨月退款 | GQ-COM-002、GQ-COM-003、GQ-COM-006、GQ-XDM-007 | 支付期与退款完成期分开 |
| P12 unknown/unattributed | GQ-MKT-003、GQ-MKT-008、GQ-PRD-008、GQ-XDM-002 | 身份/窗口不完整，不伪装 direct |
| P13 direct 不等于 unknown | GQ-MKT-003、GQ-MKT-008、GQ-PRD-008、GQ-XDM-002 | 窗口完整且无非 direct 触达 |
| P14 工单重开 | GQ-SUP-001、GQ-SUP-003、GQ-SUP-007、GQ-XDM-005 | 多次解决/重开去重和最后解决时间 |
| P15 年付 MRR 折算 | GQ-SAA-001、GQ-SAA-004、GQ-SAA-005、GQ-SAA-007 | 年付除以 12，支付收入仍在成功支付期 |

## 12. 模型映射与后续验收规则

### 12.1 问题到模型映射

- 48 个问题的“期望逻辑实体”均来自逻辑模型的 24 个 M1 核心表候选。
- 为控制表格宽度，实体列允许使用无歧义简称：`plan` 指 `saas_plan_version`，`payment_attempt`
  指 `invoice_payment_attempt`，`order`/`order_item`/`refund`/`refund_allocation` 分别指
  `commerce_order`/`commerce_order_item`/`commerce_refund`/`refund_item_allocation`，
  `channel`/`campaign`/`daily_spend`/`touch` 分别指对应的 `marketing_*` 实体，`ticket`、
  `status_event` 和 `interaction` 在客服域分别指 `support_ticket`、`ticket_status_event` 和
  `ticket_interaction`；SaaS 上下文中的 `state_event` 指 `subscription_state_event`。
- 漏斗中的阶段基础计数不是新增冻结业务指标。凡冻结定义不足以确定分母或观察窗口的问题，均明确
  标记为需要澄清。
- 跨域问题必须保留 organization、member、consumer 和 merchant 的身份边界，并先在各域权威粒度
  聚合。

### 12.2 后续 Gold SQL 重点

后续 Gold SQL 必须验证：

- 使用正确的事件时间、业务时区、`as of` 和固定数据快照；
- 正确排除测试身份、测试业务对象和测试事实；
- MRR 快照与支付收入、GMV 与退款、Merchant Net Sales 与平台收入互不混淆；
- 年付 MRR 规范化、跨期退款、未生效取消、失败支付和重复回调边界；
- 168 小时最后非直接触达、稳定 ID 决胜、direct 与 unknown/unattributed；
- 订单、退款、触达、产品事件和工单的一对多连接不会放大金额或计数；
- 比率从基础分子和分母重算，零分母返回 `null`，快照与分组均值不被错误相加；
- 需要澄清的问题在澄清前不生成查询，未批准的漏斗、健康度或因果口径不被临时发明。

## 13. M1.0 交付边界

本目录只完成问题规划和数据需求映射。Gold SQL、标准结果、种子数据、Evaluation 用例文件、模型调用、
RAG、Agent 和任何数据库实现均留待后续明确里程碑，不在 M1.0 自动实施。
