WITH periods AS (
    SELECT 'q1' AS period_name, :jan_start AS period_start, :apr_start AS period_end
    UNION ALL SELECT 'q2', :apr_start, :jul_start
),
merchants AS (
    SELECT m.merchant_assignment_id, m.merchant_id, m.merchant_name
    FROM merchant AS m
    JOIN organization AS org ON org.organization_id = m.organization_id
    WHERE m.is_test = 0 AND org.is_test = 0
),
non_test_orders AS (
    SELECT o.commerce_order_id, o.merchant_assignment_id, o.first_paid_at, o.status
    FROM commerce_order AS o
    JOIN consumer AS c ON c.consumer_id = o.consumer_id
    JOIN merchants AS m ON m.merchant_assignment_id = o.merchant_assignment_id
    WHERE o.recorded_at <= :snapshot_cutoff_utc
      AND o.is_test = 0 AND c.is_test = 0
),
gmv_orders AS (
    SELECT commerce_order_id, merchant_assignment_id, first_paid_at
    FROM non_test_orders
    WHERE status <> 'cancelled'
),
gmv AS (
    SELECT
        p.period_name,
        o.merchant_assignment_id,
        SUM(i.discounted_item_amount) AS amount
    FROM periods AS p
    JOIN gmv_orders AS o
      ON o.first_paid_at >= p.period_start AND o.first_paid_at < p.period_end
    JOIN commerce_order_item AS i ON i.commerce_order_id = o.commerce_order_id
    JOIN product AS product ON product.product_id = i.product_id
    WHERE i.is_test = 0 AND product.is_test = 0
    GROUP BY p.period_name, o.merchant_assignment_id
),
refunds AS (
    SELECT
        p.period_name,
        o.merchant_assignment_id,
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
    GROUP BY p.period_name, o.merchant_assignment_id
),
fees AS (
    SELECT
        p.period_name,
        o.merchant_assignment_id,
        SUM(f.fee_amount) AS amount
    FROM periods AS p
    JOIN platform_fee_charge AS f
      ON f.succeeded_at >= p.period_start AND f.succeeded_at < p.period_end
     AND f.status = 'succeeded'
    JOIN non_test_orders AS o ON o.commerce_order_id = f.commerce_order_id
    WHERE f.recorded_at <= :snapshot_cutoff_utc AND f.is_test = 0
    GROUP BY p.period_name, o.merchant_assignment_id
),
pivoted AS (
    SELECT
        m.merchant_id,
        m.merchant_name,
        SUM(CASE WHEN p.period_name = 'q1' THEN COALESCE(g.amount, 0) ELSE 0 END)
            AS q1_gmv,
        SUM(CASE WHEN p.period_name = 'q2' THEN COALESCE(g.amount, 0) ELSE 0 END)
            AS q2_gmv,
        SUM(CASE WHEN p.period_name = 'q1'
            THEN COALESCE(g.amount, 0) - COALESCE(r.amount, 0) ELSE 0 END)
            AS q1_net_sales,
        SUM(CASE WHEN p.period_name = 'q2'
            THEN COALESCE(g.amount, 0) - COALESCE(r.amount, 0) ELSE 0 END)
            AS q2_net_sales,
        SUM(CASE WHEN p.period_name = 'q1' THEN COALESCE(f.amount, 0) ELSE 0 END)
            AS q1_platform_revenue,
        SUM(CASE WHEN p.period_name = 'q2' THEN COALESCE(f.amount, 0) ELSE 0 END)
            AS q2_platform_revenue
    FROM merchants AS m
    CROSS JOIN periods AS p
    LEFT JOIN gmv AS g
      ON g.period_name = p.period_name
     AND g.merchant_assignment_id = m.merchant_assignment_id
    LEFT JOIN refunds AS r
      ON r.period_name = p.period_name
     AND r.merchant_assignment_id = m.merchant_assignment_id
    LEFT JOIN fees AS f
      ON f.period_name = p.period_name
     AND f.merchant_assignment_id = m.merchant_assignment_id
    GROUP BY m.merchant_id, m.merchant_name
)
SELECT
    merchant_id,
    merchant_name,
    CAST(q1_gmv AS DECIMAL(19,4)) AS q1_gmv,
    CAST(q2_gmv AS DECIMAL(19,4)) AS q2_gmv,
    CAST(q2_gmv - q1_gmv AS DECIMAL(19,4)) AS gmv_change,
    CAST(q1_net_sales AS DECIMAL(19,4)) AS q1_merchant_net_sales,
    CAST(q2_net_sales AS DECIMAL(19,4)) AS q2_merchant_net_sales,
    CAST(q2_net_sales - q1_net_sales AS DECIMAL(19,4)) AS merchant_net_sales_change,
    CAST(q1_platform_revenue AS DECIMAL(19,4)) AS q1_platform_revenue,
    CAST(q2_platform_revenue AS DECIMAL(19,4)) AS q2_platform_revenue,
    CAST(q2_platform_revenue - q1_platform_revenue AS DECIMAL(19,4))
        AS platform_revenue_change
FROM pivoted
WHERE q1_gmv <> 0 OR q2_gmv <> 0
ORDER BY gmv_change DESC, merchant_id
