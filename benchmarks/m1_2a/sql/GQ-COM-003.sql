WITH merchants AS (
    SELECT m.merchant_assignment_id, m.merchant_id, m.merchant_name
    FROM merchant AS m
    JOIN organization AS org ON org.organization_id = m.organization_id
    WHERE m.is_test = 0 AND org.is_test = 0
),
gmv AS (
    SELECT
        o.merchant_assignment_id,
        SUM(i.discounted_item_amount) AS amount
    FROM commerce_order AS o
    JOIN consumer AS c ON c.consumer_id = o.consumer_id
    JOIN commerce_order_item AS i ON i.commerce_order_id = o.commerce_order_id
    JOIN product AS p ON p.product_id = i.product_id
    WHERE o.first_paid_at >= :jun_start AND o.first_paid_at < :jul_start
      AND o.status <> 'cancelled'
      AND o.recorded_at <= :snapshot_cutoff_utc
      AND o.is_test = 0 AND c.is_test = 0 AND i.is_test = 0 AND p.is_test = 0
    GROUP BY o.merchant_assignment_id
),
refunds AS (
    SELECT
        o.merchant_assignment_id,
        SUM(a.allocated_item_amount) AS amount
    FROM commerce_refund AS r
    JOIN commerce_order AS o ON o.commerce_order_id = r.commerce_order_id
    JOIN consumer AS c ON c.consumer_id = o.consumer_id
    JOIN refund_item_allocation AS a ON a.commerce_refund_id = r.commerce_refund_id
    JOIN commerce_order_item AS i
      ON i.commerce_order_item_id = a.commerce_order_item_id
    JOIN product AS p ON p.product_id = i.product_id
    WHERE r.status = 'succeeded'
      AND r.succeeded_at >= :jun_start AND r.succeeded_at < :jul_start
      AND r.recorded_at <= :snapshot_cutoff_utc
      AND r.is_test = 0 AND o.is_test = 0 AND c.is_test = 0
      AND a.is_test = 0 AND i.is_test = 0 AND p.is_test = 0
    GROUP BY o.merchant_assignment_id
)
SELECT
    m.merchant_id,
    m.merchant_name,
    CAST(COALESCE(g.amount, 0) AS DECIMAL(19,4)) AS gmv,
    CAST(COALESCE(r.amount, 0) AS DECIMAL(19,4)) AS refund_amount,
    CAST(COALESCE(g.amount, 0) - COALESCE(r.amount, 0) AS DECIMAL(19,4))
        AS merchant_net_sales
FROM merchants AS m
LEFT JOIN gmv AS g ON g.merchant_assignment_id = m.merchant_assignment_id
LEFT JOIN refunds AS r ON r.merchant_assignment_id = m.merchant_assignment_id
WHERE g.amount IS NOT NULL OR r.amount IS NOT NULL
ORDER BY m.merchant_id
