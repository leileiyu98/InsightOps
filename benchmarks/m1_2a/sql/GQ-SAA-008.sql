WITH periods AS (
    SELECT 'Q1 baseline' AS comparison_period, 1 AS sort_order,
           :jan_start AS period_start, :apr_start AS period_end
    UNION ALL SELECT '2025-05', 2, :may_start, :jun_start
    UNION ALL SELECT '2025-06', 3, :jun_start, :jul_start
),
ranked_open AS (
    SELECT
        p.comparison_period,
        p.sort_order,
        e.subscription_id,
        s.organization_id,
        e.status_after,
        e.plan_version_after_id,
        e.normalized_mrr_after,
        ROW_NUMBER() OVER (
            PARTITION BY p.comparison_period, e.subscription_id
            ORDER BY e.effective_at DESC, e.subscription_state_event_id DESC
        ) AS rn
    FROM periods AS p
    JOIN subscription_state_event AS e ON e.effective_at < p.period_start
    JOIN subscription AS s ON s.subscription_id = e.subscription_id
    JOIN organization AS o ON o.organization_id = s.organization_id
    WHERE e.recorded_at <= :snapshot_cutoff_utc
      AND e.is_test = 0 AND s.is_test = 0 AND o.is_test = 0
),
enterprise_open AS (
    SELECT
        r.comparison_period,
        r.sort_order,
        r.organization_id,
        r.normalized_mrr_after
    FROM ranked_open AS r
    JOIN saas_plan_version AS plan
      ON plan.saas_plan_version_id = r.plan_version_after_id
    WHERE r.rn = 1
      AND r.status_after IN ('active', 'cancel_scheduled')
      AND r.normalized_mrr_after > 0
      AND plan.tier_code = 'enterprise'
      AND plan.is_test = 0
),
ranked_close AS (
    SELECT
        p.comparison_period,
        e.subscription_id,
        s.organization_id,
        e.status_after,
        e.normalized_mrr_after,
        ROW_NUMBER() OVER (
            PARTITION BY p.comparison_period, e.subscription_id
            ORDER BY e.effective_at DESC, e.subscription_state_event_id DESC
        ) AS rn
    FROM periods AS p
    JOIN subscription_state_event AS e ON e.effective_at < p.period_end
    JOIN subscription AS s ON s.subscription_id = e.subscription_id
    JOIN organization AS o ON o.organization_id = s.organization_id
    WHERE e.recorded_at <= :snapshot_cutoff_utc
      AND e.is_test = 0 AND s.is_test = 0 AND o.is_test = 0
),
active_end AS (
    SELECT DISTINCT comparison_period, organization_id
    FROM ranked_close
    WHERE rn = 1
      AND status_after IN ('active', 'cancel_scheduled')
      AND normalized_mrr_after > 0
),
churn AS (
    SELECT
        p.comparison_period,
        SUM(e.normalized_mrr_before) AS churned_mrr
    FROM periods AS p
    LEFT JOIN subscription_state_event AS e
      ON e.effective_at >= p.period_start AND e.effective_at < p.period_end
     AND e.event_type = 'cancellation_effective'
     AND e.recorded_at <= :snapshot_cutoff_utc
     AND e.is_test = 0
    LEFT JOIN subscription AS s ON s.subscription_id = e.subscription_id
    LEFT JOIN organization AS o ON o.organization_id = s.organization_id
    LEFT JOIN saas_plan_version AS plan
      ON plan.saas_plan_version_id = e.plan_version_before_id
    WHERE e.subscription_state_event_id IS NULL
       OR (s.is_test = 0 AND o.is_test = 0 AND plan.is_test = 0
           AND plan.tier_code = 'enterprise')
    GROUP BY p.comparison_period
)
SELECT
    eo.comparison_period,
    COUNT(DISTINCT eo.organization_id) AS opening_logos,
    COUNT(DISTINCT CASE WHEN ae.organization_id IS NULL THEN eo.organization_id END)
        AS churned_logos,
    CAST(COUNT(DISTINCT CASE WHEN ae.organization_id IS NULL THEN eo.organization_id END)
         / NULLIF(COUNT(DISTINCT eo.organization_id), 0) AS DECIMAL(19,4))
        AS logo_churn_rate,
    CAST(SUM(eo.normalized_mrr_after) AS DECIMAL(19,4)) AS opening_mrr,
    CAST(COALESCE(c.churned_mrr, 0) AS DECIMAL(19,4)) AS churned_mrr,
    CAST(COALESCE(c.churned_mrr, 0) / NULLIF(SUM(eo.normalized_mrr_after), 0)
        AS DECIMAL(19,4)) AS revenue_churn_rate
FROM enterprise_open AS eo
LEFT JOIN active_end AS ae
  ON ae.comparison_period = eo.comparison_period
 AND ae.organization_id = eo.organization_id
LEFT JOIN churn AS c ON c.comparison_period = eo.comparison_period
GROUP BY eo.comparison_period, eo.sort_order, c.churned_mrr
ORDER BY eo.sort_order
