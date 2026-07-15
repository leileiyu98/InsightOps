WITH ranked AS (
    SELECT
        e.subscription_id,
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
    WHERE e.effective_at < :as_of_utc
      AND e.recorded_at <= :snapshot_cutoff_utc
      AND e.is_test = 0
      AND s.is_test = 0
      AND o.is_test = 0
),
eligible AS (
    SELECT r.normalized_mrr_after AS mrr, p.plan_name
    FROM ranked AS r
    JOIN saas_plan_version AS p
      ON p.saas_plan_version_id = r.plan_version_after_id
    WHERE r.rn = 1
      AND r.status_after IN ('active', 'cancel_scheduled')
      AND r.normalized_mrr_after > 0
      AND p.is_test = 0
),
by_plan AS (
    SELECT
        plan_name,
        CAST(SUM(mrr) AS DECIMAL(19,4)) AS mrr,
        CAST(SUM(mrr) * 12 AS DECIMAL(19,4)) AS arr,
        0 AS sort_order
    FROM eligible
    GROUP BY plan_name
)
SELECT plan_name, mrr, arr
FROM (
    SELECT plan_name, mrr, arr, sort_order FROM by_plan
    UNION ALL
    SELECT
        'TOTAL',
        CAST(COALESCE(SUM(mrr), 0) AS DECIMAL(19,4)),
        CAST(COALESCE(SUM(mrr), 0) * 12 AS DECIMAL(19,4)),
        1
    FROM eligible
) AS result
ORDER BY sort_order, plan_name
