WITH periods AS (
    SELECT 'q1' AS period_name, :jan_start AS period_start, :apr_start AS period_end,
           :q1_start_date AS spend_start, :q2_start_date AS spend_end
    UNION ALL
    SELECT 'q2', :apr_start, :jul_start, :q2_start_date, :q3_start_date
),
merchants AS (
    SELECT m.merchant_assignment_id, m.merchant_id, m.merchant_name
    FROM merchant AS m
    JOIN organization AS org ON org.organization_id = m.organization_id
    WHERE m.is_test = 0 AND org.is_test = 0
),
orders AS (
    SELECT
        o.commerce_order_id,
        o.merchant_assignment_id,
        o.first_paid_at,
        o.status
    FROM commerce_order AS o
    JOIN consumer AS consumer ON consumer.consumer_id = o.consumer_id
    JOIN merchants AS m ON m.merchant_assignment_id = o.merchant_assignment_id
    WHERE o.recorded_at <= :snapshot_cutoff_utc
      AND o.is_test = 0 AND consumer.is_test = 0
),
gmv AS (
    SELECT p.period_name, o.merchant_assignment_id,
           SUM(i.discounted_item_amount) AS amount
    FROM periods AS p
    JOIN orders AS o
      ON o.first_paid_at >= p.period_start AND o.first_paid_at < p.period_end
     AND o.status <> 'cancelled'
    JOIN commerce_order_item AS i ON i.commerce_order_id = o.commerce_order_id
    JOIN product AS product ON product.product_id = i.product_id
    WHERE i.is_test = 0 AND product.is_test = 0
    GROUP BY p.period_name, o.merchant_assignment_id
),
refunds AS (
    SELECT p.period_name, o.merchant_assignment_id,
           SUM(a.allocated_item_amount) AS amount
    FROM periods AS p
    JOIN commerce_refund AS r
      ON r.succeeded_at >= p.period_start AND r.succeeded_at < p.period_end
     AND r.status = 'succeeded'
    JOIN orders AS o ON o.commerce_order_id = r.commerce_order_id
    JOIN refund_item_allocation AS a ON a.commerce_refund_id = r.commerce_refund_id
    JOIN commerce_order_item AS i
      ON i.commerce_order_item_id = a.commerce_order_item_id
    JOIN product AS product ON product.product_id = i.product_id
    WHERE r.recorded_at <= :snapshot_cutoff_utc
      AND r.is_test = 0 AND a.is_test = 0 AND i.is_test = 0 AND product.is_test = 0
    GROUP BY p.period_name, o.merchant_assignment_id
),
visible_spend AS (
    SELECT
        s.marketing_campaign_id,
        s.business_date,
        s.spend_amount,
        ROW_NUMBER() OVER (
            PARTITION BY s.marketing_campaign_id, s.business_date
            ORDER BY s.version_number DESC
        ) AS revision_rank
    FROM campaign_daily_spend AS s
    WHERE s.recorded_at <= :snapshot_cutoff_utc AND s.is_test = 0
),
spend AS (
    SELECT p.period_name, c.merchant_assignment_id, SUM(s.spend_amount) AS amount
    FROM periods AS p
    JOIN visible_spend AS s
      ON s.business_date >= p.spend_start AND s.business_date < p.spend_end
     AND s.revision_rank = 1
    JOIN marketing_campaign AS c
      ON c.marketing_campaign_id = s.marketing_campaign_id
     AND c.business_scope = 'commerce'
    JOIN marketing_channel AS ch ON ch.marketing_channel_id = c.primary_channel_id
    WHERE c.is_test = 0 AND ch.is_test = 0
    GROUP BY p.period_name, c.merchant_assignment_id
),
pivoted AS (
    SELECT
        m.merchant_id,
        m.merchant_name,
        SUM(CASE WHEN p.period_name = 'q1' THEN COALESCE(g.amount, 0) ELSE 0 END) AS q1_gmv,
        SUM(CASE WHEN p.period_name = 'q2' THEN COALESCE(g.amount, 0) ELSE 0 END) AS q2_gmv,
        SUM(CASE WHEN p.period_name = 'q1' THEN COALESCE(r.amount, 0) ELSE 0 END) AS q1_refunds,
        SUM(CASE WHEN p.period_name = 'q2' THEN COALESCE(r.amount, 0) ELSE 0 END) AS q2_refunds,
        SUM(CASE WHEN p.period_name = 'q1' THEN COALESCE(s.amount, 0) ELSE 0 END) AS q1_spend,
        SUM(CASE WHEN p.period_name = 'q2' THEN COALESCE(s.amount, 0) ELSE 0 END) AS q2_spend
    FROM merchants AS m
    CROSS JOIN periods AS p
    LEFT JOIN gmv AS g
      ON g.period_name = p.period_name
     AND g.merchant_assignment_id = m.merchant_assignment_id
    LEFT JOIN refunds AS r
      ON r.period_name = p.period_name
     AND r.merchant_assignment_id = m.merchant_assignment_id
    LEFT JOIN spend AS s
      ON s.period_name = p.period_name
     AND s.merchant_assignment_id = m.merchant_assignment_id
    GROUP BY m.merchant_id, m.merchant_name
)
SELECT
    merchant_id,
    merchant_name,
    CAST(q1_gmv AS DECIMAL(19,4)) AS q1_gmv,
    CAST(q2_gmv AS DECIMAL(19,4)) AS q2_gmv,
    CAST(q2_gmv - q1_gmv AS DECIMAL(19,4)) AS gmv_change,
    CAST(q1_refunds AS DECIMAL(19,4)) AS q1_refund_amount,
    CAST(q2_refunds AS DECIMAL(19,4)) AS q2_refund_amount,
    CAST(q2_refunds - q1_refunds AS DECIMAL(19,4)) AS refund_change,
    CAST(q1_spend AS DECIMAL(19,4)) AS q1_marketing_spend,
    CAST(q2_spend AS DECIMAL(19,4)) AS q2_marketing_spend,
    CAST(q2_spend - q1_spend AS DECIMAL(19,4)) AS marketing_spend_change,
    CASE WHEN q2_gmv > q1_gmv AND q2_refunds > q1_refunds AND q2_spend > q1_spend
         THEN 'yes' ELSE 'no' END AS all_three_increased
FROM pivoted
WHERE q1_gmv <> 0 OR q2_gmv <> 0 OR q1_spend <> 0 OR q2_spend <> 0
ORDER BY gmv_change DESC, merchant_id
