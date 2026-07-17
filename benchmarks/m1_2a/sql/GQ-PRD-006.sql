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
counts AS (
    SELECT c.organization_id, COUNT(e.condition_name) AS condition_count
    FROM cohort AS c
    LEFT JOIN condition_events AS e ON e.organization_id = c.organization_id
    GROUP BY c.organization_id
),
stages AS (
    SELECT 0 AS condition_stage
    UNION ALL SELECT 1
    UNION ALL SELECT 2
)
SELECT
    s.condition_stage,
    COUNT(c.organization_id) AS organization_count,
    CASE WHEN (SELECT COUNT(*) FROM cohort) = 0 THEN NULL
         ELSE CAST(COUNT(c.organization_id) / (SELECT COUNT(*) FROM cohort) AS DECIMAL(19,4))
    END AS cohort_share
FROM stages AS s
LEFT JOIN counts AS c
  ON (CASE WHEN c.condition_count >= 2 THEN 2 ELSE c.condition_count END) = s.condition_stage
GROUP BY s.condition_stage
ORDER BY s.condition_stage
