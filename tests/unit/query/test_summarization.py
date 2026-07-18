"""Unit tests for result-grounded business summaries."""

from insightops.query.summarization import BusinessSummarizer


def test_summary_preserves_result_numbers_verbatim() -> None:
    summary = BusinessSummarizer().summarize(
        ("report_month", "saas_revenue"),
        (
            {"report_month": "2025-04", "saas_revenue": "123.4500"},
            {"report_month": "2025-05", "saas_revenue": "98.0000"},
        ),
    )

    assert "2 行" in summary
    assert "2025-04" in summary
    assert "123.4500" in summary
    assert "123.45" not in summary.replace("123.4500", "")


def test_empty_summary_is_stable_and_inputs_are_not_modified() -> None:
    columns = ("report_month", "saas_revenue")
    rows: tuple[dict[str, str | int | bool | None], ...] = ()

    summary = BusinessSummarizer().summarize(columns, rows)

    assert summary == "查询成功，但结果为空。"
    assert columns == ("report_month", "saas_revenue")
    assert rows == ()
