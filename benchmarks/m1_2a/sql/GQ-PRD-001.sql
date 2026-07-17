WITH cohort AS (
    SELECT
        org.organization_id,
        org.registered_at,
        org.registered_at + INTERVAL 14 DAY AS window_ends_at,
        CASE WHEN org.registered_at + INTERVAL 14 DAY <= :activation_observation_as_of_utc
             THEN 1 ELSE 0 END AS is_mature
    FROM organization AS org
    WHERE org.registered_at >= :apr_start AND org.registered_at < :jul_start
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
condition_counts AS (
    SELECT c.organization_id, c.is_mature, COUNT(e.condition_name) AS condition_count
    FROM cohort AS c
    LEFT JOIN condition_events AS e ON e.organization_id = c.organization_id
    GROUP BY c.organization_id, c.is_mature
)
SELECT
    SUM(is_mature) AS mature_organization_count,
    SUM(CASE WHEN is_mature = 1 AND condition_count >= 2 THEN 1 ELSE 0 END)
        AS activated_organization_count,
    SUM(CASE WHEN is_mature = 0 THEN 1 ELSE 0 END) AS pending_organization_count,
    CASE WHEN SUM(is_mature) = 0 THEN NULL
         ELSE CAST(
             SUM(CASE WHEN is_mature = 1 AND condition_count >= 2 THEN 1 ELSE 0 END)
             / SUM(is_mature) AS DECIMAL(19,4)
         )
    END AS activation_rate
FROM condition_counts
