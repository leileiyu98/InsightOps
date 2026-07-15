WITH periods AS (
    SELECT '2025-04' AS report_month, :apr_start AS period_start, :may_start AS period_end
    UNION ALL SELECT '2025-05', :may_start, :jun_start
    UNION ALL SELECT '2025-06', :jun_start, :jul_start
)
SELECT
    p.report_month,
    CAST(COALESCE(SUM(a.subscription_fee_amount), 0) AS DECIMAL(19,4)) AS saas_revenue
FROM periods AS p
LEFT JOIN (
    SELECT pa.succeeded_at, pa.subscription_fee_amount
    FROM invoice_payment_attempt AS pa
    JOIN subscription_invoice AS i
      ON i.subscription_invoice_id = pa.subscription_invoice_id
    JOIN subscription AS s ON s.subscription_id = i.subscription_id
    JOIN organization AS o ON o.organization_id = s.organization_id
    WHERE pa.status = 'succeeded'
      AND pa.recorded_at <= :snapshot_cutoff_utc
      AND pa.is_test = 0
      AND i.is_test = 0
      AND s.is_test = 0
      AND o.is_test = 0
) AS a
  ON a.succeeded_at >= p.period_start AND a.succeeded_at < p.period_end
GROUP BY p.report_month
ORDER BY p.report_month
