WITH visible_touches AS (
    SELECT t.organization_id, t.consumer_id
    FROM marketing_touch AS t
    JOIN marketing_channel AS ch ON ch.marketing_channel_id = t.marketing_channel_id
    WHERE t.occurred_at >= :apr_start AND t.occurred_at < :jul_start
      AND t.quality_status = 'accepted'
      AND t.processed_at IS NOT NULL
      AND t.processed_at <= :snapshot_cutoff_utc
      AND t.recorded_at <= :snapshot_cutoff_utc
      AND t.is_test = 0 AND ch.is_test = 0
      AND ch.effective_from <= t.occurred_at
      AND (ch.effective_to IS NULL OR t.occurred_at < ch.effective_to)
),
touch_counts AS (
    SELECT 'saas' AS business_scope, COUNT(DISTINCT t.organization_id) AS touched_subjects
    FROM visible_touches AS t
    JOIN organization AS org ON org.organization_id = t.organization_id
    WHERE t.organization_id IS NOT NULL AND org.is_test = 0
    UNION ALL
    SELECT 'commerce', COUNT(DISTINCT t.consumer_id)
    FROM visible_touches AS t
    JOIN consumer AS consumer ON consumer.consumer_id = t.consumer_id
    WHERE t.consumer_id IS NOT NULL AND consumer.is_test = 0
),
ranked_conversions AS (
    SELECT
        ac.attributed_conversion_id,
        ac.conversion_type,
        ac.invoice_payment_attempt_id,
        ac.commerce_order_id,
        ac.organization_id,
        ac.consumer_id,
        ac.conversion_at,
        ac.source_data_cutoff_at,
        ac.recorded_at,
        ROW_NUMBER() OVER (
            PARTITION BY ac.conversion_type,
                         COALESCE(ac.invoice_payment_attempt_id, ac.commerce_order_id)
            ORDER BY ac.source_data_cutoff_at DESC, ac.recorded_at DESC,
                     ac.attributed_conversion_id DESC
        ) AS result_rank
    FROM attributed_conversion AS ac
    WHERE ac.conversion_type IN ('saas_first_payment', 'commerce_first_payment')
      AND ac.source_data_cutoff_at <= :snapshot_cutoff_utc
      AND ac.recorded_at <= :snapshot_cutoff_utc
      AND ac.is_test = 0
),
conversion_counts AS (
    SELECT
        CASE WHEN conversion_type = 'saas_first_payment' THEN 'saas' ELSE 'commerce' END
            AS business_scope,
        COUNT(DISTINCT CASE WHEN conversion_type = 'saas_first_payment'
            THEN organization_id ELSE consumer_id END) AS new_paying_customers
    FROM ranked_conversions
    WHERE result_rank = 1
      AND conversion_at >= :apr_start AND conversion_at < :jul_start
    GROUP BY CASE WHEN conversion_type = 'saas_first_payment' THEN 'saas' ELSE 'commerce' END
)
SELECT
    t.business_scope,
    t.touched_subjects,
    COALESCE(c.new_paying_customers, 0) AS new_paying_customers
FROM touch_counts AS t
LEFT JOIN conversion_counts AS c ON c.business_scope = t.business_scope
ORDER BY t.business_scope
