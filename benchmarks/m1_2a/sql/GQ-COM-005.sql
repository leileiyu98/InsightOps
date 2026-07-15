WITH merchants AS (
    SELECT m.merchant_assignment_id, m.merchant_id, m.merchant_name
    FROM merchant AS m
    JOIN organization AS org ON org.organization_id = m.organization_id
    WHERE m.is_test = 0 AND org.is_test = 0
),
eligible_orders AS (
    SELECT o.commerce_order_id, o.merchant_assignment_id, o.first_paid_at
    FROM commerce_order AS o
    JOIN consumer AS c ON c.consumer_id = o.consumer_id
    JOIN merchants AS m ON m.merchant_assignment_id = o.merchant_assignment_id
    WHERE o.status <> 'cancelled'
      AND o.recorded_at <= :snapshot_cutoff_utc
      AND o.is_test = 0 AND c.is_test = 0
),
gmv AS (
    SELECT o.merchant_assignment_id, SUM(i.discounted_item_amount) AS amount
    FROM eligible_orders AS o
    JOIN commerce_order_item AS i ON i.commerce_order_id = o.commerce_order_id
    JOIN product AS p ON p.product_id = i.product_id
    WHERE o.first_paid_at >= :apr_start AND o.first_paid_at < :jul_start
      AND i.is_test = 0 AND p.is_test = 0
    GROUP BY o.merchant_assignment_id
),
refunds AS (
    SELECT o.merchant_assignment_id, SUM(a.allocated_item_amount) AS amount
    FROM commerce_refund AS r
    JOIN eligible_orders AS o ON o.commerce_order_id = r.commerce_order_id
    JOIN refund_item_allocation AS a ON a.commerce_refund_id = r.commerce_refund_id
    JOIN commerce_order_item AS i
      ON i.commerce_order_item_id = a.commerce_order_item_id
    JOIN product AS p ON p.product_id = i.product_id
    WHERE r.status = 'succeeded'
      AND r.succeeded_at >= :apr_start AND r.succeeded_at < :jul_start
      AND r.recorded_at <= :snapshot_cutoff_utc
      AND r.is_test = 0 AND a.is_test = 0 AND i.is_test = 0 AND p.is_test = 0
    GROUP BY o.merchant_assignment_id
),
fees AS (
    SELECT o.merchant_assignment_id, SUM(f.fee_amount) AS amount
    FROM platform_fee_charge AS f
    JOIN eligible_orders AS o ON o.commerce_order_id = f.commerce_order_id
    WHERE f.status = 'succeeded'
      AND f.succeeded_at >= :apr_start AND f.succeeded_at < :jul_start
      AND f.recorded_at <= :snapshot_cutoff_utc
      AND f.is_test = 0
    GROUP BY o.merchant_assignment_id
)
SELECT
    m.merchant_id,
    m.merchant_name,
    CAST(COALESCE(g.amount, 0) AS DECIMAL(19,4)) AS gmv,
    CAST(COALESCE(r.amount, 0) AS DECIMAL(19,4)) AS refund_amount,
    CAST(COALESCE(g.amount, 0) - COALESCE(r.amount, 0) AS DECIMAL(19,4))
        AS merchant_net_sales,
    CAST(COALESCE(f.amount, 0) AS DECIMAL(19,4)) AS platform_transaction_revenue
FROM merchants AS m
LEFT JOIN gmv AS g ON g.merchant_assignment_id = m.merchant_assignment_id
LEFT JOIN refunds AS r ON r.merchant_assignment_id = m.merchant_assignment_id
LEFT JOIN fees AS f ON f.merchant_assignment_id = m.merchant_assignment_id
WHERE g.amount IS NOT NULL OR r.amount IS NOT NULL OR f.amount IS NOT NULL
ORDER BY m.merchant_id
