WITH ranked AS (
    SELECT
        ac.attributed_conversion_id,
        ac.conversion_type,
        ac.invoice_payment_attempt_id,
        ac.commerce_order_id,
        ac.platform_fee_charge_id,
        ac.organization_id,
        ac.consumer_id,
        ac.selected_marketing_touch_id,
        ac.marketing_channel_id,
        ac.marketing_campaign_id,
        ac.conversion_at,
        ac.window_started_at,
        ac.history_complete,
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
        ) AS result_rank,
        COUNT(*) OVER (
            PARTITION BY ac.conversion_type,
                         COALESCE(ac.invoice_payment_attempt_id,
                                  ac.commerce_order_id,
                                  ac.platform_fee_charge_id)
        ) AS revision_count
    FROM attributed_conversion AS ac
    WHERE ac.source_data_cutoff_at <= :snapshot_cutoff_utc
      AND ac.recorded_at <= :snapshot_cutoff_utc
      AND ac.is_test = 0
      AND ac.conversion_at >= :apr_start AND ac.conversion_at < :jul_start
),
classified AS (
    SELECT
        CASE WHEN ac.organization_id IS NOT NULL THEN 'saas' ELSE 'commerce' END
            AS business_scope,
        ac.conversion_type,
        COALESCE(p.external_payment_attempt_id, o.external_order_id, f.external_fee_charge_id)
            AS authoritative_external_id,
        ac.conversion_at,
        CASE
            WHEN ac.history_complete = 0 THEN 'history_incomplete_unknown'
            WHEN ac.revision_count > 1 THEN 'late_arriving_re_attribution'
            WHEN ac.window_started_at = :marketing_history_started_at
                THEN 'history_coverage_equality'
            WHEN ac.attribution_result = 'non_direct' AND ch.status = 'inactive'
                THEN 'inactive_historical_channel_selected'
            WHEN ac.attribution_result = 'direct' THEN 'direct_no_eligible_touch'
            ELSE 'other_materialized_result'
        END AS boundary_case,
        ac.attribution_result,
        ac.reason_code AS attribution_reason_code,
        t.source_event_id AS selected_touch_source_event_id,
        ch.channel_code AS selected_channel_code,
        ch.status AS selected_channel_current_status,
        campaign.external_campaign_id AS selected_campaign_external_id,
        ac.source_data_cutoff_at,
        CASE WHEN ac.result_rank = 1 THEN 1 ELSE 0 END AS is_latest_revision
    FROM ranked AS ac
    LEFT JOIN invoice_payment_attempt AS p
      ON p.invoice_payment_attempt_id = ac.invoice_payment_attempt_id
    LEFT JOIN commerce_order AS o ON o.commerce_order_id = ac.commerce_order_id
    LEFT JOIN platform_fee_charge AS f
      ON f.platform_fee_charge_id = ac.platform_fee_charge_id
    LEFT JOIN marketing_touch AS t
      ON t.marketing_touch_id = ac.selected_marketing_touch_id
    LEFT JOIN marketing_channel AS ch ON ch.marketing_channel_id = ac.marketing_channel_id
    LEFT JOIN marketing_campaign AS campaign
      ON campaign.marketing_campaign_id = ac.marketing_campaign_id
),
boundary_ranked AS (
    SELECT
        business_scope,
        conversion_type,
        authoritative_external_id,
        conversion_at,
        boundary_case,
        attribution_result,
        attribution_reason_code,
        selected_touch_source_event_id,
        selected_channel_code,
        selected_channel_current_status,
        selected_campaign_external_id,
        source_data_cutoff_at,
        is_latest_revision,
        ROW_NUMBER() OVER (
            PARTITION BY boundary_case, business_scope
            ORDER BY conversion_type, authoritative_external_id, source_data_cutoff_at
        ) AS boundary_rank
    FROM classified
)
SELECT
    business_scope,
    conversion_type,
    authoritative_external_id,
    conversion_at,
    boundary_case,
    attribution_result,
    attribution_reason_code,
    selected_touch_source_event_id,
    selected_channel_code,
    selected_channel_current_status,
    selected_campaign_external_id,
    source_data_cutoff_at,
    is_latest_revision
FROM boundary_ranked
WHERE boundary_case <> 'other_materialized_result'
  AND (boundary_case = 'late_arriving_re_attribution' OR boundary_rank = 1)
ORDER BY boundary_case, business_scope, conversion_type, authoritative_external_id,
         source_data_cutoff_at
