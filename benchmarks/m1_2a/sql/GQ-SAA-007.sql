WITH periods AS (
    SELECT '2025-04' AS report_month, :apr_start AS period_start, :may_start AS period_end
    UNION ALL SELECT '2025-05', :may_start, :jun_start
    UNION ALL SELECT '2025-06', :jun_start, :jul_start
),
revenue AS (
    SELECT
        p.report_month,
        SUM(pa.subscription_fee_amount) AS saas_revenue
    FROM periods AS p
    LEFT JOIN invoice_payment_attempt AS pa
      ON pa.succeeded_at >= p.period_start AND pa.succeeded_at < p.period_end
     AND pa.status = 'succeeded' AND pa.is_test = 0
     AND pa.recorded_at <= :snapshot_cutoff_utc
    LEFT JOIN subscription_invoice AS i
      ON i.subscription_invoice_id = pa.subscription_invoice_id AND i.is_test = 0
    LEFT JOIN subscription AS s ON s.subscription_id = i.subscription_id AND s.is_test = 0
    LEFT JOIN organization AS o ON o.organization_id = s.organization_id AND o.is_test = 0
    WHERE pa.invoice_payment_attempt_id IS NULL OR o.organization_id IS NOT NULL
    GROUP BY p.report_month
),
ranked AS (
    SELECT
        p.report_month,
        e.subscription_id,
        e.status_after,
        e.normalized_mrr_after,
        ROW_NUMBER() OVER (
            PARTITION BY p.report_month, e.subscription_id
            ORDER BY e.effective_at DESC, e.subscription_state_event_id DESC
        ) AS rn
    FROM periods AS p
    JOIN subscription_state_event AS e ON e.effective_at < p.period_end
    JOIN subscription AS s ON s.subscription_id = e.subscription_id
    JOIN organization AS o ON o.organization_id = s.organization_id
    WHERE e.recorded_at <= :snapshot_cutoff_utc
      AND e.is_test = 0 AND s.is_test = 0 AND o.is_test = 0
),
mrr AS (
    SELECT report_month, SUM(normalized_mrr_after) AS month_end_mrr
    FROM ranked
    WHERE rn = 1
      AND status_after IN ('active', 'cancel_scheduled')
      AND normalized_mrr_after > 0
    GROUP BY report_month
)
SELECT
    p.report_month,
    CAST(COALESCE(r.saas_revenue, 0) AS DECIMAL(19,4)) AS saas_revenue,
    CAST(COALESCE(m.month_end_mrr, 0) AS DECIMAL(19,4)) AS month_end_mrr
FROM periods AS p
LEFT JOIN revenue AS r ON r.report_month = p.report_month
LEFT JOIN mrr AS m ON m.report_month = p.report_month
ORDER BY p.report_month
