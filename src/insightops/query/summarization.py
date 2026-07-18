"""Deterministic, result-grounded business summary for the MVP."""

from insightops.query.contracts import QueryScalar


class SummaryError(RuntimeError):
    """Summary rendering failed without invalidating a correct SQL result."""


class BusinessSummarizer:
    """Render only values already present in the normalized query result."""

    def summarize(
        self,
        columns: tuple[str, ...],
        rows: tuple[dict[str, QueryScalar], ...],
    ) -> str:
        if not rows:
            return "查询成功，但结果为空。"
        first_row = rows[0]
        values = "，".join(f"{column}={first_row[column]}" for column in columns)
        if len(rows) == 1:
            return f"查询返回 1 行：{values}。"
        return f"查询返回 {len(rows)} 行；首行结果为 {values}。"
