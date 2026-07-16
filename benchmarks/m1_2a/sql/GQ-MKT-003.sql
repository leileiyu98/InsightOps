WITH ranked_saas AS (
    SELECT
        ac.attributed_conversion_id,
        ac.invoice_payment_attempt_id,
        ac.organization_id,
        ac.marketing_channel_id,
        ac.attribution_result,
        ac.conversion_at,
        ac.source_data_cutoff_at,
        ac.recorded_at,
        ROW_NUMBER() OVER (
            PARTITION BY ac.invoice_payment_attempt_id
            ORDER BY ac.source_data_cutoff_at DESC, ac.recorded_at DESC,
                     ac.attributed_conversion_id DESC
        ) AS result_rank
    FROM attributed_conversion AS ac
    WHERE ac.conversion_type = 'saas_revenue'
      AND ac.source_data_cutoff_at <= :snapshot_cutoff_utc
      AND ac.recorded_at <= :snapshot_cutoff_utc
      AND ac.is_test = 0
),
ranked_commerce AS (
    SELECT
        ac.attributed_conversion_id,
        ac.platform_fee_charge_id,
        ac.consumer_id,
        ac.marketing_channel_id,
        ac.attribution_result,
        ac.conversion_at,
        ac.source_data_cutoff_at,
        ac.recorded_at,
        ROW_NUMBER() OVER (
            PARTITION BY ac.platform_fee_charge_id
            ORDER BY ac.source_data_cutoff_at DESC, ac.recorded_at DESC,
                     ac.attributed_conversion_id DESC
        ) AS result_rank
    FROM attributed_conversion AS ac
    WHERE ac.conversion_type = 'commerce_revenue'
      AND ac.source_data_cutoff_at <= :snapshot_cutoff_utc
      AND ac.recorded_at <= :snapshot_cutoff_utc
      AND ac.is_test = 0
),
base AS (
    SELECT
        'saas' AS business_scope,
        COALESCE(
            CAST(ch.channel_code AS CHAR CHARACTER SET utf8mb4),
            'unknown_unattributed'
        ) AS channel_code,
        ac.attribution_result,
        p.subscription_fee_amount AS revenue_amount
    FROM ranked_saas AS ac
    JOIN invoice_payment_attempt AS p
      ON p.invoice_payment_attempt_id = ac.invoice_payment_attempt_id
    JOIN subscription_invoice AS i ON i.subscription_invoice_id = p.subscription_invoice_id
    JOIN subscription AS sub ON sub.subscription_id = i.subscription_id
    JOIN organization AS org ON org.organization_id = ac.organization_id
    LEFT JOIN marketing_channel AS ch ON ch.marketing_channel_id = ac.marketing_channel_id
    WHERE ac.result_rank = 1
      AND ac.conversion_at >= :jun_start AND ac.conversion_at < :jul_start
      AND p.status = 'succeeded'
      AND p.is_test = 0 AND i.is_test = 0 AND sub.is_test = 0 AND org.is_test = 0
      AND (ch.marketing_channel_id IS NULL OR ch.is_test = 0)
    UNION ALL
    SELECT
        'commerce',
        COALESCE(
            CAST(ch.channel_code AS CHAR CHARACTER SET utf8mb4),
            'unknown_unattributed'
        ),
        ac.attribution_result,
        f.fee_amount
    FROM ranked_commerce AS ac
    JOIN platform_fee_charge AS f
      ON f.platform_fee_charge_id = ac.platform_fee_charge_id
    JOIN commerce_order AS o ON o.commerce_order_id = f.commerce_order_id
    JOIN consumer AS consumer ON consumer.consumer_id = ac.consumer_id
    JOIN merchant AS m ON m.merchant_assignment_id = o.merchant_assignment_id
    JOIN organization AS org ON org.organization_id = m.organization_id
    LEFT JOIN marketing_channel AS ch ON ch.marketing_channel_id = ac.marketing_channel_id
    WHERE ac.result_rank = 1
      AND ac.conversion_at >= :jun_start AND ac.conversion_at < :jul_start
      AND f.status = 'succeeded'
      AND f.is_test = 0 AND o.is_test = 0 AND consumer.is_test = 0
      AND m.is_test = 0 AND org.is_test = 0
      AND (ch.marketing_channel_id IS NULL OR ch.is_test = 0)
),
aggregated AS (
    SELECT business_scope, channel_code, attribution_result, SUM(revenue_amount) AS revenue
    FROM base
    GROUP BY business_scope, channel_code, attribution_result
),
required_rows AS (
    SELECT 'saas' AS business_scope, 'direct' AS channel_code, 'direct' AS attribution_result
    UNION ALL SELECT 'saas', 'unknown_unattributed', 'unknown_unattributed'
    UNION ALL SELECT 'commerce', 'direct', 'direct'
    UNION ALL SELECT 'commerce', 'unknown_unattributed', 'unknown_unattributed'
),
complete AS (
    SELECT business_scope, channel_code, attribution_result, revenue FROM aggregated
    UNION ALL
    SELECT r.business_scope, r.channel_code, r.attribution_result, 0
    FROM required_rows AS r
    WHERE NOT EXISTS (
        SELECT 1 FROM aggregated AS a
        WHERE a.business_scope = r.business_scope
          AND a.channel_code = r.channel_code
          AND a.attribution_result = r.attribution_result
    )
),
totals AS (
    SELECT business_scope, SUM(revenue_amount) AS total_revenue
    FROM base
    GROUP BY business_scope
)
SELECT
    c.business_scope,
    c.channel_code,
    c.attribution_result,
    CAST(c.revenue AS DECIMAL(19,4)) AS attributed_revenue,
    CASE WHEN COALESCE(t.total_revenue, 0) = 0 THEN NULL
         ELSE CAST(c.revenue / t.total_revenue AS DECIMAL(19,4))
    END AS revenue_share
FROM complete AS c
LEFT JOIN totals AS t ON t.business_scope = c.business_scope
ORDER BY c.business_scope, c.attribution_result, c.channel_code
