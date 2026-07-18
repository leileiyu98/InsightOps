"""Deterministic offline provider for tests and the five-minute demo."""

from collections.abc import Mapping

from insightops.query.context import QueryContext
from insightops.query.contracts import ProviderOutput, StructuredCandidate
from insightops.query.providers.base import ProviderError

_SAA_002_SQL = """WITH periods AS (
    SELECT '2025-04' AS report_month, :apr_start AS period_start, :may_start AS period_end
    UNION ALL SELECT '2025-05', :may_start, :jun_start
    UNION ALL SELECT '2025-06', :jun_start, :jul_start
)
SELECT
    p.report_month,
    CAST(COALESCE(SUM(a.subscription_fee_amount), 0) AS DECIMAL(19,4)) AS saas_revenue
FROM periods AS p
LEFT JOIN (
    SELECT pa.succeeded_at, pa.subscription_fee_amount
    FROM invoice_payment_attempt AS pa
    JOIN subscription_invoice AS i
      ON i.subscription_invoice_id = pa.subscription_invoice_id
    JOIN subscription AS s ON s.subscription_id = i.subscription_id
    JOIN organization AS o ON o.organization_id = s.organization_id
    WHERE pa.status = 'succeeded'
      AND pa.recorded_at <= :snapshot_cutoff_utc
      AND pa.is_test = 0 AND i.is_test = 0 AND s.is_test = 0 AND o.is_test = 0
) AS a ON a.succeeded_at >= p.period_start AND a.succeeded_at < p.period_end
GROUP BY p.report_month
ORDER BY p.report_month"""

_COM_001_SQL = """WITH eligible_orders AS (
    SELECT o.commerce_order_id
    FROM commerce_order AS o
    JOIN consumer AS c ON c.consumer_id = o.consumer_id
    JOIN merchant AS m ON m.merchant_assignment_id = o.merchant_assignment_id
    JOIN organization AS org ON org.organization_id = m.organization_id
    WHERE o.first_paid_at >= :jun_start AND o.first_paid_at < :jul_start
      AND o.status <> 'cancelled' AND o.recorded_at <= :snapshot_cutoff_utc
      AND o.is_test = 0 AND c.is_test = 0 AND m.is_test = 0 AND org.is_test = 0
),
gmv AS (
    SELECT SUM(i.discounted_item_amount) AS amount
    FROM commerce_order_item AS i
    JOIN eligible_orders AS o ON o.commerce_order_id = i.commerce_order_id
    JOIN product AS p ON p.product_id = i.product_id
    WHERE i.is_test = 0 AND p.is_test = 0
),
orders AS (
    SELECT COUNT(DISTINCT commerce_order_id) AS order_count FROM eligible_orders
)
SELECT CAST(COALESCE(g.amount, 0) AS DECIMAL(19,4)) AS gmv,
       o.order_count,
       CAST(COALESCE(g.amount, 0) / NULLIF(o.order_count, 0) AS DECIMAL(19,4)) AS aov
FROM orders AS o CROSS JOIN gmv AS g"""

_DEFAULT_CANDIDATES: dict[str | None, StructuredCandidate] = {
    None: StructuredCandidate(
        action="execute_sql",
        sql=(
            "SELECT organization_name FROM organization "
            "WHERE is_test = 0 ORDER BY organization_name LIMIT 1"
        ),
    ),
    "GQ-SAA-002": StructuredCandidate(action="execute_sql", sql=_SAA_002_SQL),
    "GQ-COM-001": StructuredCandidate(action="execute_sql", sql=_COM_001_SQL),
    "GQ-MKT-006": StructuredCandidate(
        action="request_clarification",
        clarification_code="attributed_revenue_type_required",
        clarification_question="请明确 ROAS 使用 SaaS Revenue 还是 Commerce Revenue？",
    ),
}


class FakeQueryProvider:
    """Return reviewed deterministic candidates without reading benchmark oracles."""

    def __init__(
        self,
        candidates: Mapping[str | None, StructuredCandidate] | None = None,
        *,
        fail: bool = False,
    ) -> None:
        self._candidates = dict(_DEFAULT_CANDIDATES if candidates is None else candidates)
        self._fail = fail

    @property
    def name(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return "deterministic-v1"

    def generate(self, context: QueryContext) -> ProviderOutput:
        if self._fail:
            raise ProviderError()
        case_id = context.case.case_id if context.case is not None else None
        candidate = self._candidates.get(case_id)
        if candidate is None:
            raise ProviderError("fake_candidate_not_configured")
        return ProviderOutput(candidate=candidate, provider=self.name, model=self.model)

    def close(self) -> None:
        """Match the provider lifecycle without owning external resources."""
