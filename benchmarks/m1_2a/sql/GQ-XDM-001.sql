WITH periods AS (
    SELECT '2025-04' AS report_month, :apr_start AS period_start, :may_start AS period_end
    UNION ALL SELECT '2025-05', :may_start, :jun_start
    UNION ALL SELECT '2025-06', :jun_start, :jul_start
),
saas AS (
    SELECT p.report_month, SUM(pa.subscription_fee_amount) AS amount
    FROM periods AS p
    LEFT JOIN invoice_payment_attempt AS pa
      ON pa.succeeded_at >= p.period_start AND pa.succeeded_at < p.period_end
     AND pa.status = 'succeeded' AND pa.is_test = 0
     AND pa.recorded_at <= :snapshot_cutoff_utc
    LEFT JOIN subscription_invoice AS i
      ON i.subscription_invoice_id = pa.subscription_invoice_id AND i.is_test = 0
    LEFT JOIN subscription AS s ON s.subscription_id = i.subscription_id AND s.is_test = 0
    LEFT JOIN organization AS org
      ON org.organization_id = s.organization_id AND org.is_test = 0
    WHERE pa.invoice_payment_attempt_id IS NULL OR org.organization_id IS NOT NULL
    GROUP BY p.report_month
),
commerce AS (
    SELECT p.report_month, SUM(f.fee_amount) AS amount
    FROM periods AS p
    LEFT JOIN platform_fee_charge AS f
      ON f.succeeded_at >= p.period_start AND f.succeeded_at < p.period_end
     AND f.status = 'succeeded' AND f.is_test = 0
     AND f.recorded_at <= :snapshot_cutoff_utc
    LEFT JOIN commerce_order AS o
      ON o.commerce_order_id = f.commerce_order_id
     AND o.status <> 'cancelled' AND o.is_test = 0
    LEFT JOIN consumer AS c ON c.consumer_id = o.consumer_id AND c.is_test = 0
    LEFT JOIN merchant AS m
      ON m.merchant_assignment_id = o.merchant_assignment_id AND m.is_test = 0
    LEFT JOIN organization AS org
      ON org.organization_id = m.organization_id AND org.is_test = 0
    WHERE f.platform_fee_charge_id IS NULL OR org.organization_id IS NOT NULL
    GROUP BY p.report_month
)
SELECT
    p.report_month,
    CAST(COALESCE(s.amount, 0) AS DECIMAL(19,4)) AS saas_revenue,
    CAST(COALESCE(c.amount, 0) AS DECIMAL(19,4)) AS commerce_revenue
FROM periods AS p
LEFT JOIN saas AS s ON s.report_month = p.report_month
LEFT JOIN commerce AS c ON c.report_month = p.report_month
ORDER BY p.report_month
