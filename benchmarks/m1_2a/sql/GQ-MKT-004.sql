WITH qualifying_touches AS (
    SELECT
        CASE WHEN t.organization_id IS NOT NULL THEN 'saas' ELSE 'commerce' END
            AS business_scope,
        COALESCE(t.organization_id, t.consumer_id) AS subject_id,
        t.occurred_at
    FROM marketing_touch AS t
    JOIN marketing_channel AS ch ON ch.marketing_channel_id = t.marketing_channel_id
    LEFT JOIN marketing_campaign AS campaign
      ON campaign.marketing_campaign_id = t.marketing_campaign_id
    LEFT JOIN organization AS org ON org.organization_id = t.organization_id
    LEFT JOIN consumer AS consumer ON consumer.consumer_id = t.consumer_id
    WHERE t.occurred_at >= :apr_start AND t.occurred_at < :jul_start
      AND t.quality_status = 'accepted'
      AND t.processed_at IS NOT NULL
      AND t.processed_at <= :snapshot_cutoff_utc
      AND t.recorded_at <= :snapshot_cutoff_utc
      AND t.is_test = 0 AND ch.is_test = 0
      AND (campaign.marketing_campaign_id IS NULL OR campaign.is_test = 0)
      AND (org.organization_id IS NULL OR org.is_test = 0)
      AND (consumer.consumer_id IS NULL OR consumer.is_test = 0)
      AND ch.effective_from <= t.occurred_at
      AND (ch.effective_to IS NULL OR t.occurred_at < ch.effective_to)
),
touched_cohort AS (
    SELECT DISTINCT business_scope, subject_id
    FROM qualifying_touches
),
touch_counts AS (
    SELECT business_scope, COUNT(*) AS touched_subject_count
    FROM touched_cohort
    GROUP BY business_scope
),
ranked_first_payments AS (
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
qualified_first_payments AS (
    SELECT 'saas' AS business_scope, ac.organization_id AS subject_id
    FROM ranked_first_payments AS ac
    JOIN invoice_payment_attempt AS p
      ON p.invoice_payment_attempt_id = ac.invoice_payment_attempt_id
    JOIN subscription_invoice AS i ON i.subscription_invoice_id = p.subscription_invoice_id
    JOIN subscription AS sub ON sub.subscription_id = i.subscription_id
    JOIN organization AS org ON org.organization_id = ac.organization_id
    JOIN qualifying_touches AS t
      ON t.business_scope = 'saas'
     AND t.subject_id = ac.organization_id
     AND t.occurred_at <= ac.conversion_at
    WHERE ac.result_rank = 1
      AND ac.conversion_type = 'saas_first_payment'
      AND ac.conversion_at >= :apr_start AND ac.conversion_at < :jul_start
      AND p.status = 'succeeded'
      AND p.is_test = 0 AND i.is_test = 0 AND sub.is_test = 0 AND org.is_test = 0
    UNION ALL
    SELECT 'commerce', ac.consumer_id
    FROM ranked_first_payments AS ac
    JOIN commerce_order AS o ON o.commerce_order_id = ac.commerce_order_id
    JOIN consumer AS consumer ON consumer.consumer_id = ac.consumer_id
    JOIN merchant AS m ON m.merchant_assignment_id = o.merchant_assignment_id
    JOIN organization AS org ON org.organization_id = m.organization_id
    JOIN qualifying_touches AS t
      ON t.business_scope = 'commerce'
     AND t.subject_id = ac.consumer_id
     AND t.occurred_at <= ac.conversion_at
    WHERE ac.result_rank = 1
      AND ac.conversion_type = 'commerce_first_payment'
      AND ac.conversion_at >= :apr_start AND ac.conversion_at < :jul_start
      AND o.status = 'completed'
      AND o.is_test = 0 AND consumer.is_test = 0 AND m.is_test = 0 AND org.is_test = 0
),
first_payment_counts AS (
    SELECT business_scope, COUNT(DISTINCT subject_id) AS first_payment_subject_count
    FROM qualified_first_payments
    GROUP BY business_scope
)
SELECT
    t.business_scope,
    t.touched_subject_count,
    COALESCE(p.first_payment_subject_count, 0) AS first_payment_subject_count
FROM touch_counts AS t
LEFT JOIN first_payment_counts AS p ON p.business_scope = t.business_scope
ORDER BY t.business_scope
