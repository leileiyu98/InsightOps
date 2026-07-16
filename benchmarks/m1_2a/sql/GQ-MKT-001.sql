WITH visible_spend AS (
    SELECT
        s.marketing_campaign_id,
        s.business_date,
        s.spend_amount,
        ROW_NUMBER() OVER (
            PARTITION BY s.marketing_campaign_id, s.business_date
            ORDER BY s.version_number DESC
        ) AS revision_rank
    FROM campaign_daily_spend AS s
    WHERE s.recorded_at <= :snapshot_cutoff_utc AND s.is_test = 0
),
spend_by_channel AS (
    SELECT ch.channel_code, SUM(s.spend_amount) AS spend_amount
    FROM visible_spend AS s
    JOIN marketing_campaign AS c
      ON c.marketing_campaign_id = s.marketing_campaign_id
    JOIN marketing_channel AS ch ON ch.marketing_channel_id = c.primary_channel_id
    JOIN organization AS org ON org.organization_id = c.organization_id
    WHERE s.revision_rank = 1
      AND s.business_date >= :q2_start_date AND s.business_date < :q3_start_date
      AND c.business_scope = 'saas'
      AND c.is_test = 0 AND ch.is_test = 0 AND org.is_test = 0
    GROUP BY ch.channel_code
),
ranked_conversions AS (
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
customers_by_channel AS (
    SELECT
        COALESCE(ch.channel_code, 'unknown_unattributed') AS channel_code,
        COUNT(DISTINCT ac.organization_id) AS new_customers
    FROM ranked_conversions AS ac
    JOIN invoice_payment_attempt AS p
      ON p.invoice_payment_attempt_id = ac.invoice_payment_attempt_id
    JOIN subscription_invoice AS i ON i.subscription_invoice_id = p.subscription_invoice_id
    JOIN subscription AS sub ON sub.subscription_id = i.subscription_id
    JOIN organization AS org ON org.organization_id = ac.organization_id
    LEFT JOIN marketing_channel AS ch ON ch.marketing_channel_id = ac.marketing_channel_id
    WHERE ac.result_rank = 1
      AND ac.conversion_at >= :apr_start AND ac.conversion_at < :jul_start
      AND p.status = 'succeeded'
      AND p.is_test = 0 AND i.is_test = 0 AND sub.is_test = 0 AND org.is_test = 0
      AND (ch.marketing_channel_id IS NULL OR ch.is_test = 0)
    GROUP BY COALESCE(ch.channel_code, 'unknown_unattributed')
),
channel_keys AS (
    SELECT channel_code FROM spend_by_channel
    UNION
    SELECT channel_code FROM customers_by_channel
)
SELECT
    k.channel_code,
    CAST(COALESCE(s.spend_amount, 0) AS DECIMAL(19,4)) AS spend_amount,
    COALESCE(c.new_customers, 0) AS new_customers,
    CASE WHEN COALESCE(c.new_customers, 0) = 0 OR COALESCE(s.spend_amount, 0) = 0 THEN NULL
         ELSE CAST(COALESCE(s.spend_amount, 0) / c.new_customers AS DECIMAL(19,4))
    END AS saas_cac
FROM channel_keys AS k
LEFT JOIN spend_by_channel AS s ON s.channel_code = k.channel_code
LEFT JOIN customers_by_channel AS c ON c.channel_code = k.channel_code
ORDER BY k.channel_code
