WITH periods AS (
    SELECT '2025-01' AS report_month, :jan_start AS period_start, :feb_start AS period_end
    UNION ALL SELECT '2025-02', :feb_start, :mar_start
    UNION ALL SELECT '2025-03', :mar_start, :apr_start
    UNION ALL SELECT '2025-04', :apr_start, :may_start
    UNION ALL SELECT '2025-05', :may_start, :jun_start
    UNION ALL SELECT '2025-06', :jun_start, :jul_start
),
eligible_orders AS (
    SELECT p.report_month, o.commerce_order_id
    FROM periods AS p
    JOIN commerce_order AS o
      ON o.first_paid_at >= p.period_start AND o.first_paid_at < p.period_end
    JOIN consumer AS c ON c.consumer_id = o.consumer_id
    JOIN merchant AS m ON m.merchant_assignment_id = o.merchant_assignment_id
    JOIN organization AS org ON org.organization_id = m.organization_id
    WHERE o.status <> 'cancelled'
      AND o.recorded_at <= :snapshot_cutoff_utc
      AND o.is_test = 0 AND c.is_test = 0 AND m.is_test = 0 AND org.is_test = 0
),
monthly AS (
    SELECT
        o.report_month,
        COUNT(DISTINCT o.commerce_order_id) AS order_count,
        SUM(i.discounted_item_amount) AS gmv
    FROM eligible_orders AS o
    JOIN commerce_order_item AS i ON i.commerce_order_id = o.commerce_order_id
    JOIN product AS p ON p.product_id = i.product_id
    WHERE i.is_test = 0 AND p.is_test = 0
    GROUP BY o.report_month
)
SELECT
    p.report_month,
    CAST(COALESCE(m.gmv, 0) AS DECIMAL(19,4)) AS gmv,
    COALESCE(m.order_count, 0) AS order_count,
    CAST(m.gmv / NULLIF(m.order_count, 0) AS DECIMAL(19,4)) AS aov
FROM periods AS p
LEFT JOIN monthly AS m ON m.report_month = p.report_month
ORDER BY p.report_month
