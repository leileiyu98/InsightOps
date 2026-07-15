WITH periods AS (
    SELECT '2025-01' AS report_month, :feb_start AS as_of_utc
    UNION ALL SELECT '2025-02', :mar_start
    UNION ALL SELECT '2025-03', :apr_start
    UNION ALL SELECT '2025-04', :may_start
    UNION ALL SELECT '2025-05', :jun_start
    UNION ALL SELECT '2025-06', :jul_start
),
ranked AS (
    SELECT
        p.report_month,
        e.subscription_id,
        e.status_after,
        e.plan_version_after_id,
        e.normalized_mrr_after,
        ROW_NUMBER() OVER (
            PARTITION BY p.report_month, e.subscription_id
            ORDER BY e.effective_at DESC, e.subscription_state_event_id DESC
        ) AS rn
    FROM periods AS p
    JOIN subscription_state_event AS e ON e.effective_at < p.as_of_utc
    JOIN subscription AS s ON s.subscription_id = e.subscription_id
    JOIN organization AS o ON o.organization_id = s.organization_id
    WHERE e.recorded_at <= :snapshot_cutoff_utc
      AND e.is_test = 0
      AND s.is_test = 0
      AND o.is_test = 0
)
SELECT
    r.report_month,
    plan.plan_name,
    CAST(SUM(r.normalized_mrr_after) AS DECIMAL(19,4)) AS mrr,
    CAST(SUM(r.normalized_mrr_after) * 12 AS DECIMAL(19,4)) AS arr
FROM ranked AS r
JOIN saas_plan_version AS plan
  ON plan.saas_plan_version_id = r.plan_version_after_id
WHERE r.rn = 1
  AND r.status_after IN ('active', 'cancel_scheduled')
  AND r.normalized_mrr_after > 0
  AND plan.is_test = 0
GROUP BY r.report_month, plan.plan_name
ORDER BY r.report_month, plan.plan_name
