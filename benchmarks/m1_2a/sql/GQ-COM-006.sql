WITH periods AS (
    SELECT '2025-04' AS report_month, :apr_start AS period_start, :may_start AS period_end
    UNION ALL SELECT '2025-05', :may_start, :jun_start
    UNION ALL SELECT '2025-06', :jun_start, :jul_start
),
categories AS (
    SELECT DISTINCT product_category_code AS category_code
    FROM commerce_order_item
    WHERE is_test = 0
),
non_test_orders AS (
    SELECT o.commerce_order_id, o.first_paid_at, o.status
    FROM commerce_order AS o
    JOIN consumer AS c ON c.consumer_id = o.consumer_id
    JOIN merchant AS m ON m.merchant_assignment_id = o.merchant_assignment_id
    JOIN organization AS org ON org.organization_id = m.organization_id
    WHERE o.recorded_at <= :snapshot_cutoff_utc
      AND o.is_test = 0 AND c.is_test = 0 AND m.is_test = 0 AND org.is_test = 0
),
gmv_orders AS (
    SELECT commerce_order_id, first_paid_at
    FROM non_test_orders
    WHERE status <> 'cancelled'
),
gmv AS (
    SELECT
        p.report_month,
        i.product_category_code AS category_code,
        SUM(i.discounted_item_amount) AS amount
    FROM periods AS p
    JOIN gmv_orders AS o
      ON o.first_paid_at >= p.period_start AND o.first_paid_at < p.period_end
    JOIN commerce_order_item AS i ON i.commerce_order_id = o.commerce_order_id
    JOIN product AS product ON product.product_id = i.product_id
    WHERE i.is_test = 0 AND product.is_test = 0
    GROUP BY p.report_month, i.product_category_code
),
refunds AS (
    SELECT
        p.report_month,
        i.product_category_code AS category_code,
        SUM(a.allocated_item_amount) AS amount
    FROM periods AS p
    JOIN commerce_refund AS r
      ON r.succeeded_at >= p.period_start AND r.succeeded_at < p.period_end
     AND r.status = 'succeeded'
    JOIN non_test_orders AS o ON o.commerce_order_id = r.commerce_order_id
    JOIN refund_item_allocation AS a ON a.commerce_refund_id = r.commerce_refund_id
    JOIN commerce_order_item AS i
      ON i.commerce_order_item_id = a.commerce_order_item_id
    JOIN product AS product ON product.product_id = i.product_id
    WHERE r.recorded_at <= :snapshot_cutoff_utc
      AND r.is_test = 0 AND a.is_test = 0 AND i.is_test = 0 AND product.is_test = 0
    GROUP BY p.report_month, i.product_category_code
)
SELECT
    p.report_month,
    c.category_code,
    CAST(COALESCE(g.amount, 0) AS DECIMAL(19,4)) AS gmv,
    CAST(COALESCE(r.amount, 0) AS DECIMAL(19,4)) AS refund_amount,
    CAST(COALESCE(r.amount, 0) / NULLIF(g.amount, 0) AS DECIMAL(19,4))
        AS refund_rate
FROM periods AS p
CROSS JOIN categories AS c
LEFT JOIN gmv AS g
  ON g.report_month = p.report_month AND g.category_code = c.category_code
LEFT JOIN refunds AS r
  ON r.report_month = p.report_month AND r.category_code = c.category_code
ORDER BY p.report_month, c.category_code
