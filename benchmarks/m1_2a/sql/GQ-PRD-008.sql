WITH cohort AS (
    SELECT
        org.organization_id,
        org.registered_at,
        org.registered_at + INTERVAL 14 DAY AS window_ends_at
    FROM organization AS org
    WHERE org.registered_at >= :apr_start AND org.registered_at < :jul_start
      AND org.registered_at + INTERVAL 14 DAY <= :activation_observation_as_of_utc
      AND org.recorded_at <= :snapshot_cutoff_utc
      AND org.is_test = 0
),
condition_events AS (
    SELECT DISTINCT c.organization_id, 'member_invite' AS condition_name
    FROM cohort AS c
    JOIN organization_member AS m ON m.organization_id = c.organization_id
    WHERE m.first_invited_at >= c.registered_at
      AND m.first_invited_at < c.window_ends_at
      AND m.first_invited_at < :activation_observation_as_of_utc
      AND m.recorded_at <= :snapshot_cutoff_utc AND m.is_test = 0
    UNION
    SELECT DISTINCT c.organization_id, 'campaign_created'
    FROM cohort AS c
    JOIN marketing_campaign AS campaign ON campaign.organization_id = c.organization_id
    WHERE campaign.created_at >= c.registered_at
      AND campaign.created_at < c.window_ends_at
      AND campaign.created_at < :activation_observation_as_of_utc
      AND campaign.recorded_at <= :snapshot_cutoff_utc AND campaign.is_test = 0
    UNION
    SELECT DISTINCT c.organization_id, 'completed_order'
    FROM cohort AS c
    JOIN merchant AS m ON m.organization_id = c.organization_id
    JOIN commerce_order AS o ON o.merchant_assignment_id = m.merchant_assignment_id
    JOIN consumer AS consumer ON consumer.consumer_id = o.consumer_id
    WHERE o.status = 'completed'
      AND o.completed_at >= c.registered_at AND o.completed_at < c.window_ends_at
      AND o.completed_at < :activation_observation_as_of_utc
      AND o.recorded_at <= :snapshot_cutoff_utc
      AND m.is_test = 0 AND o.is_test = 0 AND consumer.is_test = 0
),
activation AS (
    SELECT c.organization_id, COUNT(e.condition_name) AS condition_count
    FROM cohort AS c
    LEFT JOIN condition_events AS e ON e.organization_id = c.organization_id
    GROUP BY c.organization_id
),
ranked_first_payments AS (
    SELECT
        ac.attributed_conversion_id,
        ac.invoice_payment_attempt_id,
        ac.organization_id,
        ac.marketing_channel_id,
        ac.conversion_at,
        ac.source_data_cutoff_at,
        ac.recorded_at,
        ROW_NUMBER() OVER (
            PARTITION BY ac.invoice_payment_attempt_id
            ORDER BY ac.source_data_cutoff_at DESC, ac.recorded_at DESC,
                     ac.attributed_conversion_id DESC
        ) AS result_rank
    FROM attributed_conversion AS ac
    WHERE ac.conversion_type = 'saas_first_payment'
      AND ac.source_data_cutoff_at <= :snapshot_cutoff_utc
      AND ac.recorded_at <= :snapshot_cutoff_utc
      AND ac.is_test = 0
),
first_payments AS (
    SELECT
        ac.organization_id,
        COALESCE(ch.channel_code, 'unknown_unattributed') AS channel_code
    FROM ranked_first_payments AS ac
    JOIN invoice_payment_attempt AS p
      ON p.invoice_payment_attempt_id = ac.invoice_payment_attempt_id
    JOIN subscription_invoice AS i ON i.subscription_invoice_id = p.subscription_invoice_id
    JOIN subscription AS sub ON sub.subscription_id = i.subscription_id
    LEFT JOIN marketing_channel AS ch ON ch.marketing_channel_id = ac.marketing_channel_id
    WHERE ac.result_rank = 1
      AND ac.conversion_at >= :apr_start AND ac.conversion_at < :jul_start
      AND p.status = 'succeeded'
      AND p.is_test = 0 AND i.is_test = 0 AND sub.is_test = 0
)
SELECT
    fp.channel_code,
    COUNT(DISTINCT fp.organization_id) AS new_paying_organization_count,
    COUNT(DISTINCT c.organization_id) AS mature_organization_count,
    COUNT(DISTINCT CASE WHEN a.condition_count >= 2 THEN c.organization_id END)
        AS activated_organization_count,
    CASE WHEN COUNT(DISTINCT c.organization_id) = 0 THEN NULL
         ELSE CAST(
             COUNT(DISTINCT CASE WHEN a.condition_count >= 2 THEN c.organization_id END)
             / COUNT(DISTINCT c.organization_id) AS DECIMAL(19,4)
         )
    END AS activation_rate
FROM first_payments AS fp
JOIN cohort AS c ON c.organization_id = fp.organization_id
JOIN activation AS a ON a.organization_id = c.organization_id
GROUP BY fp.channel_code
ORDER BY fp.channel_code
