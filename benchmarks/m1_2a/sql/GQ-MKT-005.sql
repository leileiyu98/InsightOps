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
    SELECT
        CAST(c.business_scope AS CHAR CHARACTER SET utf8mb4) AS business_scope,
        CAST(ch.channel_code AS CHAR CHARACTER SET utf8mb4) AS channel_code,
        SUM(CASE WHEN s.business_date >= :may_start_date
                  AND s.business_date < :jun_start_date THEN s.spend_amount ELSE 0 END)
            AS may_spend,
        SUM(CASE WHEN s.business_date >= :jun_start_date
                  AND s.business_date < :jul_start_date THEN s.spend_amount ELSE 0 END)
            AS jun_spend
    FROM visible_spend AS s
    JOIN marketing_campaign AS c
      ON c.marketing_campaign_id = s.marketing_campaign_id
    JOIN marketing_channel AS ch ON ch.marketing_channel_id = c.primary_channel_id
    WHERE s.revision_rank = 1
      AND s.business_date >= :may_start_date AND s.business_date < :jul_start_date
      AND c.is_test = 0 AND ch.is_test = 0
    GROUP BY c.business_scope, ch.channel_code
),
ranked_conversions AS (
    SELECT
        ac.attributed_conversion_id,
        ac.conversion_type,
        ac.invoice_payment_attempt_id,
        ac.commerce_order_id,
        ac.organization_id,
        ac.consumer_id,
        ac.marketing_channel_id,
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
customers AS (
    SELECT
        CASE WHEN ac.conversion_type = 'saas_first_payment' THEN 'saas' ELSE 'commerce' END
            AS business_scope,
        COALESCE(
            CAST(ch.channel_code AS CHAR CHARACTER SET utf8mb4),
            'unknown_unattributed'
        ) AS channel_code,
        COUNT(DISTINCT CASE WHEN ac.conversion_at >= :may_start AND ac.conversion_at < :jun_start
            THEN CASE WHEN ac.conversion_type = 'saas_first_payment'
                THEN ac.organization_id ELSE ac.consumer_id END END) AS may_customers,
        COUNT(DISTINCT CASE WHEN ac.conversion_at >= :jun_start AND ac.conversion_at < :jul_start
            THEN CASE WHEN ac.conversion_type = 'saas_first_payment'
                THEN ac.organization_id ELSE ac.consumer_id END END) AS jun_customers
    FROM ranked_conversions AS ac
    LEFT JOIN marketing_channel AS ch ON ch.marketing_channel_id = ac.marketing_channel_id
    WHERE ac.result_rank = 1
      AND ac.conversion_at >= :may_start AND ac.conversion_at < :jul_start
    GROUP BY
        CASE WHEN ac.conversion_type = 'saas_first_payment' THEN 'saas' ELSE 'commerce' END,
        COALESCE(
            CAST(ch.channel_code AS CHAR CHARACTER SET utf8mb4),
            'unknown_unattributed'
        )
),
result_keys AS (
    SELECT business_scope, channel_code FROM spend
    UNION
    SELECT business_scope, channel_code FROM customers
)
SELECT
    k.business_scope,
    k.channel_code,
    CAST(COALESCE(s.may_spend, 0) AS DECIMAL(19,4)) AS may_spend,
    CAST(COALESCE(s.jun_spend, 0) AS DECIMAL(19,4)) AS jun_spend,
    COALESCE(c.may_customers, 0) AS may_customers,
    COALESCE(c.jun_customers, 0) AS jun_customers,
    CASE WHEN COALESCE(s.jun_spend, 0) > COALESCE(s.may_spend, 0)
              AND COALESCE(c.jun_customers, 0) < COALESCE(c.may_customers, 0)
         THEN 'yes' ELSE 'no' END AS spend_up_customers_down
FROM result_keys AS k
LEFT JOIN spend AS s
  ON s.business_scope = k.business_scope AND s.channel_code = k.channel_code
LEFT JOIN customers AS c
  ON c.business_scope = k.business_scope AND c.channel_code = k.channel_code
ORDER BY k.business_scope, k.channel_code
