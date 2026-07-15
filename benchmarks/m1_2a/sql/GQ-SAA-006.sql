WITH params AS (
    SELECT :apr_start AS period_start, :jul_start AS period_end
),
ranked_open AS (
    SELECT
        e.subscription_id,
        s.organization_id,
        e.status_after,
        e.plan_version_after_id,
        e.normalized_mrr_after,
        ROW_NUMBER() OVER (
            PARTITION BY e.subscription_id
            ORDER BY e.effective_at DESC, e.subscription_state_event_id DESC
        ) AS rn
    FROM subscription_state_event AS e
    JOIN subscription AS s ON s.subscription_id = e.subscription_id
    JOIN organization AS o ON o.organization_id = s.organization_id
    CROSS JOIN params AS p
    WHERE e.effective_at < p.period_start
      AND e.recorded_at <= :snapshot_cutoff_utc
      AND e.is_test = 0 AND s.is_test = 0 AND o.is_test = 0
),
opening AS (
    SELECT
        r.organization_id,
        plan.plan_name,
        r.normalized_mrr_after
    FROM ranked_open AS r
    JOIN saas_plan_version AS plan
      ON plan.saas_plan_version_id = r.plan_version_after_id
    WHERE r.rn = 1
      AND r.status_after IN ('active', 'cancel_scheduled')
      AND r.normalized_mrr_after > 0
      AND plan.is_test = 0
),
ranked_close AS (
    SELECT
        e.subscription_id,
        s.organization_id,
        e.status_after,
        e.normalized_mrr_after,
        ROW_NUMBER() OVER (
            PARTITION BY e.subscription_id
            ORDER BY e.effective_at DESC, e.subscription_state_event_id DESC
        ) AS rn
    FROM subscription_state_event AS e
    JOIN subscription AS s ON s.subscription_id = e.subscription_id
    JOIN organization AS o ON o.organization_id = s.organization_id
    CROSS JOIN params AS p
    WHERE e.effective_at < p.period_end
      AND e.recorded_at <= :snapshot_cutoff_utc
      AND e.is_test = 0 AND s.is_test = 0 AND o.is_test = 0
),
active_orgs_end AS (
    SELECT DISTINCT organization_id
    FROM ranked_close
    WHERE rn = 1
      AND status_after IN ('active', 'cancel_scheduled')
      AND normalized_mrr_after > 0
),
opening_by_plan AS (
    SELECT
        plan_name,
        COUNT(DISTINCT organization_id) AS opening_logos,
        SUM(normalized_mrr_after) AS opening_mrr
    FROM opening
    GROUP BY plan_name
),
logo_churn AS (
    SELECT
        o.plan_name,
        COUNT(DISTINCT CASE WHEN a.organization_id IS NULL THEN o.organization_id END)
            AS churned_logos
    FROM opening AS o
    LEFT JOIN active_orgs_end AS a ON a.organization_id = o.organization_id
    GROUP BY o.plan_name
),
revenue_churn AS (
    SELECT
        plan.plan_name,
        SUM(e.normalized_mrr_before) AS churned_mrr
    FROM subscription_state_event AS e
    JOIN subscription AS s ON s.subscription_id = e.subscription_id
    JOIN organization AS o ON o.organization_id = s.organization_id
    JOIN saas_plan_version AS plan
      ON plan.saas_plan_version_id = e.plan_version_before_id
    CROSS JOIN params AS p
    WHERE e.event_type = 'cancellation_effective'
      AND e.effective_at >= p.period_start
      AND e.effective_at < p.period_end
      AND e.recorded_at <= :snapshot_cutoff_utc
      AND e.is_test = 0 AND s.is_test = 0 AND o.is_test = 0 AND plan.is_test = 0
    GROUP BY plan.plan_name
)
SELECT
    op.plan_name,
    op.opening_logos,
    COALESCE(lc.churned_logos, 0) AS churned_logos,
    CAST(COALESCE(lc.churned_logos, 0) / NULLIF(op.opening_logos, 0)
        AS DECIMAL(19,4)) AS logo_churn_rate,
    CAST(op.opening_mrr AS DECIMAL(19,4)) AS opening_mrr,
    CAST(COALESCE(rc.churned_mrr, 0) AS DECIMAL(19,4)) AS churned_mrr,
    CAST(COALESCE(rc.churned_mrr, 0) / NULLIF(op.opening_mrr, 0)
        AS DECIMAL(19,4)) AS revenue_churn_rate
FROM opening_by_plan AS op
LEFT JOIN logo_churn AS lc ON lc.plan_name = op.plan_name
LEFT JOIN revenue_churn AS rc ON rc.plan_name = op.plan_name
ORDER BY op.plan_name
