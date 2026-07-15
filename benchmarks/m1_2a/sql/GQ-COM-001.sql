WITH eligible_orders AS (
    SELECT o.commerce_order_id
    FROM commerce_order AS o
    JOIN consumer AS c ON c.consumer_id = o.consumer_id
    JOIN merchant AS m ON m.merchant_assignment_id = o.merchant_assignment_id
    JOIN organization AS org ON org.organization_id = m.organization_id
    WHERE o.first_paid_at >= :jun_start AND o.first_paid_at < :jul_start
      AND o.status <> 'cancelled'
      AND o.recorded_at <= :snapshot_cutoff_utc
      AND o.is_test = 0 AND c.is_test = 0 AND m.is_test = 0 AND org.is_test = 0
),
gmv AS (
    SELECT SUM(i.discounted_item_amount) AS amount
    FROM commerce_order_item AS i
    JOIN eligible_orders AS o ON o.commerce_order_id = i.commerce_order_id
    JOIN product AS p ON p.product_id = i.product_id
    WHERE i.is_test = 0 AND p.is_test = 0
),
orders AS (
    SELECT COUNT(DISTINCT commerce_order_id) AS order_count
    FROM eligible_orders
)
SELECT
    CAST(COALESCE(g.amount, 0) AS DECIMAL(19,4)) AS gmv,
    o.order_count,
    CAST(COALESCE(g.amount, 0) / NULLIF(o.order_count, 0)
        AS DECIMAL(19,4)) AS aov
FROM orders AS o
CROSS JOIN gmv AS g
