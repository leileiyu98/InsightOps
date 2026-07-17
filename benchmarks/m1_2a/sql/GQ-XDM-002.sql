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
spend AS (
    SELECT c.merchant_assignment_id, SUM(s.spend_amount) AS spend_amount
    FROM visible_spend AS s
    JOIN marketing_campaign AS c
      ON c.marketing_campaign_id = s.marketing_campaign_id
    JOIN marketing_channel AS ch ON ch.marketing_channel_id = c.primary_channel_id
    WHERE s.revision_rank = 1
      AND s.business_date >= :q2_start_date AND s.business_date < :q3_start_date
      AND c.business_scope = 'commerce'
      AND c.is_test = 0 AND ch.is_test = 0
    GROUP BY c.merchant_assignment_id
),
ranked_revenue AS (
    SELECT
        ac.attributed_conversion_id,
        ac.platform_fee_charge_id,
        ac.marketing_campaign_id,
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
revenue AS (
    SELECT
        o.merchant_assignment_id,
        SUM(CASE WHEN ac.attribution_result = 'non_direct'
                      AND ac.marketing_campaign_id IS NOT NULL
                 THEN f.fee_amount ELSE 0 END) AS attributed_revenue,
        SUM(CASE WHEN ac.attribution_result = 'direct' THEN f.fee_amount ELSE 0 END)
            AS direct_revenue,
        SUM(CASE WHEN ac.attribution_result = 'unknown_unattributed'
                 THEN f.fee_amount ELSE 0 END) AS unknown_revenue
    FROM ranked_revenue AS ac
    JOIN platform_fee_charge AS f
      ON f.platform_fee_charge_id = ac.platform_fee_charge_id
    JOIN commerce_order AS o ON o.commerce_order_id = f.commerce_order_id
    JOIN consumer AS consumer ON consumer.consumer_id = o.consumer_id
    WHERE ac.result_rank = 1
      AND ac.conversion_at >= :apr_start AND ac.conversion_at < :jul_start
      AND f.status = 'succeeded'
      AND f.is_test = 0 AND o.is_test = 0 AND consumer.is_test = 0
    GROUP BY o.merchant_assignment_id
),
merchant_keys AS (
    SELECT merchant_assignment_id FROM spend
    UNION
    SELECT merchant_assignment_id FROM revenue
)
SELECT
    m.merchant_id,
    m.merchant_name,
    CAST(COALESCE(s.spend_amount, 0) AS DECIMAL(19,4)) AS marketing_spend,
    CAST(COALESCE(r.attributed_revenue, 0) AS DECIMAL(19,4))
        AS attributed_commerce_revenue,
    CAST(COALESCE(r.direct_revenue, 0) AS DECIMAL(19,4)) AS direct_commerce_revenue,
    CAST(COALESCE(r.unknown_revenue, 0) AS DECIMAL(19,4)) AS unknown_commerce_revenue,
    CASE WHEN COALESCE(s.spend_amount, 0) = 0 THEN NULL
         ELSE CAST(COALESCE(r.attributed_revenue, 0) / s.spend_amount AS DECIMAL(19,4))
    END AS commerce_attributed_roas
FROM merchant_keys AS k
JOIN merchant AS m ON m.merchant_assignment_id = k.merchant_assignment_id
JOIN organization AS org ON org.organization_id = m.organization_id
LEFT JOIN spend AS s ON s.merchant_assignment_id = k.merchant_assignment_id
LEFT JOIN revenue AS r ON r.merchant_assignment_id = k.merchant_assignment_id
WHERE m.is_test = 0 AND org.is_test = 0
ORDER BY m.merchant_id
