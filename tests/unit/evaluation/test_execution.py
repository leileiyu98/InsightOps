"""Unit tests for readonly execution boundary helpers."""

from insightops.evaluation.execution import _grants_are_readonly_for_database


def test_readonly_grants_require_exact_target_database_scope() -> None:
    target = (
        "GRANT USAGE ON *.* TO `insightops_readonly`@`%`",
        "GRANT SELECT ON `INSIGHTOPS`.* TO `insightops_readonly`@`%`",
    )
    global_select = (
        "GRANT USAGE ON *.* TO `insightops_readonly`@`%`",
        "GRANT SELECT ON *.* TO `insightops_readonly`@`%`",
    )
    other_database = (
        "GRANT USAGE ON *.* TO `insightops_readonly`@`%`",
        "GRANT SELECT ON `OTHER`.* TO `insightops_readonly`@`%`",
    )
    extra_privilege = target + ("GRANT INSERT ON `INSIGHTOPS`.* TO `insightops_readonly`@`%`",)

    assert _grants_are_readonly_for_database(target, "insightops")
    assert not _grants_are_readonly_for_database(global_select, "insightops")
    assert not _grants_are_readonly_for_database(other_database, "insightops")
    assert not _grants_are_readonly_for_database(extra_privilege, "insightops")
