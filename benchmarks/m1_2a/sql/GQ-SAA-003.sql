WITH periods AS (
    SELECT '2025-04' AS report_month, :apr_start AS period_start, :may_start AS period_end
    UNION ALL SELECT '2025-05', :may_start, :jun_start
    UNION ALL SELECT '2025-06', :jun_start, :jul_start
)
SELECT
    p.report_month,
    CAST(COALESCE(SUM(e.normalized_mrr_before), 0) AS DECIMAL(19,4)) AS churned_mrr
FROM periods AS p
LEFT JOIN (
    SELECT e.effective_at, e.normalized_mrr_before
    FROM subscription_state_event AS e
    JOIN subscription AS s ON s.subscription_id = e.subscription_id
    JOIN organization AS o ON o.organization_id = s.organization_id
    JOIN saas_plan_version AS plan
      ON plan.saas_plan_version_id = e.plan_version_before_id
    WHERE e.event_type = 'cancellation_effective'
      AND e.recorded_at <= :snapshot_cutoff_utc
      AND e.is_test = 0
      AND s.is_test = 0
      AND o.is_test = 0
      AND plan.is_test = 0
) AS e
  ON e.effective_at >= p.period_start AND e.effective_at < p.period_end
GROUP BY p.report_month
ORDER BY p.report_month
