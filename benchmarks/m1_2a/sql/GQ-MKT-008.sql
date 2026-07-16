WITH ranked AS (
    SELECT
        ac.attributed_conversion_id,
        ac.conversion_type,
        ac.invoice_payment_attempt_id,
        ac.commerce_order_id,
        ac.platform_fee_charge_id,
        ac.organization_id,
        ac.selected_marketing_touch_id,
        ac.marketing_channel_id,
        ac.conversion_at,
        ac.attribution_result,
        ac.reason_code,
        ac.source_data_cutoff_at,
        ac.recorded_at,
        ROW_NUMBER() OVER (
            PARTITION BY ac.conversion_type,
                         COALESCE(ac.invoice_payment_attempt_id,
                                  ac.commerce_order_id,
                                  ac.platform_fee_charge_id)
            ORDER BY ac.source_data_cutoff_at DESC, ac.recorded_at DESC,
                     ac.attributed_conversion_id DESC
        ) AS result_rank
    FROM attributed_conversion AS ac
    WHERE ac.source_data_cutoff_at <= :snapshot_cutoff_utc
      AND ac.recorded_at <= :snapshot_cutoff_utc
      AND ac.is_test = 0
)
SELECT
    CASE WHEN ac.organization_id IS NOT NULL THEN 'saas' ELSE 'commerce' END
        AS business_scope,
    ac.conversion_type,
    COALESCE(p.external_payment_attempt_id, o.external_order_id, f.external_fee_charge_id)
        AS authoritative_external_id,
    ac.conversion_at,
    ac.attribution_result,
    ac.reason_code,
    t.source_event_id AS selected_touch_source_event_id,
    ch.channel_code,
    ac.source_data_cutoff_at
FROM ranked AS ac
LEFT JOIN invoice_payment_attempt AS p
  ON p.invoice_payment_attempt_id = ac.invoice_payment_attempt_id
LEFT JOIN commerce_order AS o ON o.commerce_order_id = ac.commerce_order_id
LEFT JOIN platform_fee_charge AS f
  ON f.platform_fee_charge_id = ac.platform_fee_charge_id
LEFT JOIN marketing_touch AS t
  ON t.marketing_touch_id = ac.selected_marketing_touch_id
LEFT JOIN marketing_channel AS ch ON ch.marketing_channel_id = ac.marketing_channel_id
WHERE ac.result_rank = 1
  AND ac.conversion_at >= :jun_start AND ac.conversion_at < :jul_start
  AND ac.attribution_result IN ('direct', 'unknown_unattributed')
ORDER BY business_scope, ac.conversion_type, authoritative_external_id
