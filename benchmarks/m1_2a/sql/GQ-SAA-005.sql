WITH periods AS (
    SELECT '2025-05' AS report_month, :may_start AS period_start, :jun_start AS period_end
    UNION ALL SELECT '2025-06', :jun_start, :jul_start
),
ranked_open AS (
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
    JOIN subscription_state_event AS e ON e.effective_at < p.period_start
    JOIN subscription AS s ON s.subscription_id = e.subscription_id
    JOIN organization AS o ON o.organization_id = s.organization_id
    WHERE e.recorded_at <= :snapshot_cutoff_utc
      AND e.is_test = 0 AND s.is_test = 0 AND o.is_test = 0
),
ranked_close AS (
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
opening AS (
    SELECT report_month, SUM(normalized_mrr_after) AS opening_mrr
    FROM ranked_open
    WHERE rn = 1
      AND status_after IN ('active', 'cancel_scheduled')
      AND normalized_mrr_after > 0
    GROUP BY report_month
),
closing AS (
    SELECT report_month, SUM(normalized_mrr_after) AS closing_mrr
    FROM ranked_close
    WHERE rn = 1
      AND status_after IN ('active', 'cancel_scheduled')
      AND normalized_mrr_after > 0
    GROUP BY report_month
),
movements AS (
    SELECT
        p.report_month,
        SUM(CASE WHEN e.event_type = 'first_activation'
            THEN e.normalized_mrr_after ELSE 0 END) AS new_mrr,
        SUM(CASE WHEN e.event_type = 'expansion'
            THEN e.normalized_mrr_after - e.normalized_mrr_before ELSE 0 END) AS expansion_mrr,
        SUM(CASE WHEN e.event_type = 'contraction'
            THEN e.normalized_mrr_before - e.normalized_mrr_after ELSE 0 END) AS contraction_mrr,
        SUM(CASE WHEN e.event_type = 'cancellation_effective'
            THEN e.normalized_mrr_before ELSE 0 END) AS churned_mrr
    FROM periods AS p
    LEFT JOIN subscription_state_event AS e
      ON e.effective_at >= p.period_start AND e.effective_at < p.period_end
     AND e.recorded_at <= :snapshot_cutoff_utc
     AND e.is_test = 0
    LEFT JOIN subscription AS s ON s.subscription_id = e.subscription_id
    LEFT JOIN organization AS o ON o.organization_id = s.organization_id
    WHERE e.subscription_state_event_id IS NULL OR (s.is_test = 0 AND o.is_test = 0)
    GROUP BY p.report_month
)
SELECT
    p.report_month,
    CAST(COALESCE(o.opening_mrr, 0) AS DECIMAL(19,4)) AS opening_mrr,
    CAST(COALESCE(m.new_mrr, 0) AS DECIMAL(19,4)) AS new_mrr,
    CAST(COALESCE(m.expansion_mrr, 0) AS DECIMAL(19,4)) AS expansion_mrr,
    CAST(COALESCE(m.contraction_mrr, 0) AS DECIMAL(19,4)) AS contraction_mrr,
    CAST(COALESCE(m.churned_mrr, 0) AS DECIMAL(19,4)) AS churned_mrr,
    CAST(COALESCE(c.closing_mrr, 0) AS DECIMAL(19,4)) AS closing_mrr
FROM periods AS p
LEFT JOIN opening AS o ON o.report_month = p.report_month
LEFT JOIN closing AS c ON c.report_month = p.report_month
LEFT JOIN movements AS m ON m.report_month = p.report_month
ORDER BY p.report_month
