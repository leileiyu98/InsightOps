# M1.1C 商城交易 Schema 实施记录

## 目标与范围

本批次将 `docs/m1-physical-data-model.md` 中的商城物理模型实现为 SQLAlchemy 2.x typed declarative
mappings 和 Alembic revision `0003`。

实施表仅包括：

- `product`
- `commerce_order`
- `commerce_order_item`
- `commerce_refund`
- `refund_item_allocation`
- `platform_fee_charge`

不包含营销、产品使用、客服、种子数据、Gold SQL、业务 API、repository/service、权限、Text2SQL、
RAG、Agent、Memory、MCP 或 M1.1D。

## 代码与 Migration 组织

- `insightops.db.models.commerce` 保存六个商城模型，不添加无当前用途的 ORM relationship。
- `insightops.db.models` 显式注册当前全部 15 个模型，供应用和 Alembic 共用同一 metadata。
- revision `0003` 显式创建 DDL，不导入 ORM，也不调用 `Base.metadata.create_all()`。
- upgrade 顺序为 product → order → order item → refund/fee → allocation；downgrade 严格逆序。
- `0001` 和 `0002` 保持不变。

## 权威事实和历史口径

- GMV 的唯一权威金额是 `commerce_order_item.discounted_item_amount`，订单表不复制订单级 GMV。
- GMV、Order Count 和 AOV 使用 `commerce_order.first_paid_at` 归期；AOV 不落表。
- `product` 保存当前实体，订单明细保存购买时 `product_category_code` 快照。商品改名或改类不改变
  历史明细金额和类别分析；M1 不增加分类维表或商品版本历史。
- 退款按 `commerce_refund.succeeded_at` 归期，不回移到订单支付月，也不减少历史 GMV。
- allocation 只分配退款商品金额，不承载 GMV。跨行合计和跨表订单归属不使用 Check 或 trigger 伪造。
- `platform_fee_charge` 只表示一次平台交易服务费收取尝试。成功服务费形成平台交易收入，退款不会自动
  冲减该收入；不实现应收、余额、payout、佣金、结算或会计收入确认。

## 类型、约束和索引

- PK/FK 使用 `BIGINT UNSIGNED`，数量使用 `INT UNSIGNED`，金额使用 `DECIMAL(19,4)`，时间使用
  `DATETIME(6)`，币种只允许 USD。
- 外部 ID、provider ID、商品类别代码、购买时类别代码和退款原因代码使用 ASCII + `ascii_bin`。
- 状态使用普通 `VARCHAR(32) + CHECK`；布尔字段使用 `BOOLEAN + CHECK IN (0, 1)`。
- product、order、refund 和 allocation 的 `updated_at` 由 MySQL
  `ON UPDATE CURRENT_TIMESTAMP(6)` 刷新；order item 和 append-only platform fee 不含 `updated_at`。
- 所有外键显式使用 `ON DELETE RESTRICT ON UPDATE RESTRICT`。
- 不创建 `ix_order_item__order` 和 `ix_refund_alloc__refund`；对应唯一复合索引的左前缀已经支持查询。

## 数据库与应用层边界

数据库保证主外键、唯一性、状态、币种、布尔、金额非负、退款行内合计、单行时间顺序和终态时间一致性。

以下规则保留给后续应用事务或数据质量任务：order item 商品与订单 merchant 一致、来源订单总额对账、
refund/order/item 跨表归属、allocation 跨行合计、累计可退款金额、platform fee 商业规则、merchant
有效区间、状态转换历史，以及测试数据全链路排除。本阶段不实现相应服务、trigger 或自动修复。

## 验证策略

- Metadata 测试验证当前精确 15 表、MySQL 类型、时间精度、ASCII binary collation 和禁止类型。
- 结构测试验证具名 Check/Unique/FK/索引、RESTRICT、默认值、`updated_at` 和重复索引排除。
- 真实 MySQL 测试验证合法状态与非法状态、时间、金额、币种、布尔、外键、唯一性和大小写边界。
- migration 测试分别执行 `0002 → 0003 → 0002 → 0003` 和
  `base → 0003 → base → 0003`，并在 `finally` 中恢复到 `0003` head。
- ORM、migration 和真实 MySQL Schema 通过反射比较保持一致。

## 本地验收结果

- Ruff format check：通过。
- Ruff lint：通过。
- strict mypy：通过，30 个源文件无问题。
- pytest：135 个测试全部通过；仅保留一个来自 Starlette TestClient/httpx 兼容层的既有弃用警告。
- Alembic 增量生命周期 `0002 → 0003 → 0002 → 0003`：通过。
- Alembic 全量生命周期 `base → 0003 → base → 0003`：通过，最终 revision 为 `0003`。
- MySQL 8.4 Schema 反射、类型、collation、默认值、Check、Unique、FK、RESTRICT、索引和
  `ON UPDATE CURRENT_TIMESTAMP(6)`：通过。
- Uvicorn 启动和 `GET /health`：通过，返回 HTTP 200 与 `{"status":"ok"}`。
