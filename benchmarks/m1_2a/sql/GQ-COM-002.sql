WITH eligible_orders AS (
    SELECT o.commerce_order_id, o.first_paid_at
    FROM commerce_order AS o
    JOIN consumer AS c ON c.consumer_id = o.consumer_id
    JOIN merchant AS m ON m.merchant_assignment_id = o.merchant_assignment_id
    JOIN organization AS org ON org.organization_id = m.organization_id
    WHERE o.status <> 'cancelled'
      AND o.recorded_at <= :snapshot_cutoff_utc
      AND o.is_test = 0 AND c.is_test = 0 AND m.is_test = 0 AND org.is_test = 0
),
gmv AS (
    SELECT SUM(i.discounted_item_amount) AS amount
    FROM eligible_orders AS o
    JOIN commerce_order_item AS i ON i.commerce_order_id = o.commerce_order_id
    JOIN product AS p ON p.product_id = i.product_id
    WHERE o.first_paid_at >= :jun_start AND o.first_paid_at < :jul_start
      AND i.is_test = 0 AND p.is_test = 0
),
refunds AS (
    SELECT
        SUM(a.allocated_item_amount) AS amount,
        SUM(CASE WHEN o.first_paid_at >= :may_start AND o.first_paid_at < :jun_start
            THEN a.allocated_item_amount ELSE 0 END) AS prior_month_amount
    FROM commerce_refund AS r
    JOIN eligible_orders AS o ON o.commerce_order_id = r.commerce_order_id
    JOIN refund_item_allocation AS a ON a.commerce_refund_id = r.commerce_refund_id
    JOIN commerce_order_item AS i
      ON i.commerce_order_item_id = a.commerce_order_item_id
    JOIN product AS p ON p.product_id = i.product_id
    WHERE r.status = 'succeeded'
      AND r.succeeded_at >= :jun_start AND r.succeeded_at < :jul_start
      AND r.recorded_at <= :snapshot_cutoff_utc
      AND r.is_test = 0 AND a.is_test = 0 AND i.is_test = 0 AND p.is_test = 0
)
SELECT
    CAST(COALESCE(r.amount, 0) AS DECIMAL(19,4)) AS refund_amount,
    CAST(COALESCE(g.amount, 0) AS DECIMAL(19,4)) AS gmv,
    CAST(COALESCE(r.amount, 0) / NULLIF(g.amount, 0) AS DECIMAL(19,4))
        AS refund_rate,
    CAST(COALESCE(r.prior_month_amount, 0) AS DECIMAL(19,4))
        AS prior_month_order_refund_amount
FROM refunds AS r
CROSS JOIN gmv AS g
