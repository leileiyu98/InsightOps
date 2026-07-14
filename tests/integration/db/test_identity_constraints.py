"""Real MySQL constraint tests for enterprise and identity tables."""

from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError
from sqlalchemy.orm import Session

from insightops.db.models import Consumer, Merchant, Organization, OrganizationMember

START = datetime(2025, 1, 1)
LATER = datetime(2025, 2, 1)


def test_valid_organizations_accept_case_distinct_external_ids(db_session: Session) -> None:
    db_session.add_all(
        [
            _organization("Org-Case"),
            _organization("org-case"),
        ]
    )
    db_session.flush()


def test_duplicate_organization_external_id_is_rejected(db_session: Session) -> None:
    db_session.add_all([_organization("org-duplicate"), _organization("org-duplicate")])
    _assert_constraint_rejection_and_rollback(db_session)


def test_invalid_organization_status_is_rejected(db_session: Session) -> None:
    organization = _organization("org-invalid-status")
    organization.status = "unknown"
    db_session.add(organization)
    _assert_constraint_rejection_and_rollback(db_session)


def test_invalid_organization_closed_time_is_rejected(db_session: Session) -> None:
    organization = _organization("org-invalid-close")
    organization.status = "closed"
    organization.closed_at = datetime(2024, 12, 31)
    db_session.add(organization)
    _assert_constraint_rejection_and_rollback(db_session)


def test_closed_organization_requires_closed_at(db_session: Session) -> None:
    organization = _organization("org-missing-close")
    organization.status = "closed"
    db_session.add(organization)
    _assert_constraint_rejection_and_rollback(db_session)


def test_boolean_check_rejects_non_boolean_integer(db_session: Session) -> None:
    with pytest.raises((IntegrityError, OperationalError)) as error_info:
        db_session.execute(
            text(
                "INSERT INTO organization "
                "(external_organization_id, organization_name, status, registered_at, is_test) "
                "VALUES ('org-invalid-boolean', 'Invalid Boolean', 'active', :registered_at, 2)"
            ),
            {"registered_at": START},
        )
    db_session.rollback()
    _assert_expected_constraint_exception(error_info.value)


def test_member_requires_existing_organization(db_session: Session) -> None:
    db_session.add(_member(organization_id=18_446_744_073_709_551_614))
    _assert_constraint_rejection_and_rollback(db_session)


def test_duplicate_membership_id_is_rejected(
    db_session: Session,
    organization: Organization,
) -> None:
    db_session.add_all(
        [
            _member(organization.organization_id, external_id="membership-duplicate"),
            _member(organization.organization_id, external_id="membership-duplicate"),
        ]
    )
    _assert_constraint_rejection_and_rollback(db_session)


def test_member_effective_range_requires_strictly_later_end(
    db_session: Session,
    organization: Organization,
) -> None:
    member = _member(organization.organization_id)
    member.effective_to = member.effective_from
    db_session.add(member)
    _assert_constraint_rejection_and_rollback(db_session)


def test_member_acceptance_cannot_precede_invitation(
    db_session: Session,
    organization: Organization,
) -> None:
    member = _member(organization.organization_id)
    member.first_invited_at = LATER
    member.accepted_at = START
    db_session.add(member)
    _assert_constraint_rejection_and_rollback(db_session)


def test_duplicate_consumer_external_id_is_rejected(db_session: Session) -> None:
    db_session.add_all([_consumer("consumer-duplicate"), _consumer("consumer-duplicate")])
    _assert_constraint_rejection_and_rollback(db_session)


def test_invalid_consumer_status_is_rejected(db_session: Session) -> None:
    consumer = _consumer("consumer-invalid-status")
    consumer.status = "unknown"
    db_session.add(consumer)
    _assert_constraint_rejection_and_rollback(db_session)


def test_invalid_consumer_time_order_is_rejected(db_session: Session) -> None:
    consumer = _consumer("consumer-invalid-time")
    consumer.first_identified_at = datetime(2024, 12, 31)
    db_session.add(consumer)
    _assert_constraint_rejection_and_rollback(db_session)


def test_merchant_allows_two_historical_intervals(
    db_session: Session,
    organization: Organization,
) -> None:
    first = _merchant(organization.organization_id, valid_from=START)
    first.assignment_valid_to = LATER
    second = _merchant(organization.organization_id, valid_from=LATER)
    db_session.add_all([first, second])
    db_session.flush()


def test_merchant_rejects_duplicate_identity_interval_start(
    db_session: Session,
    organization: Organization,
) -> None:
    db_session.add_all(
        [
            _merchant(organization.organization_id, valid_from=START),
            _merchant(
                organization.organization_id,
                valid_from=START,
                external_id="merchant-other-external",
            ),
        ]
    )
    _assert_constraint_rejection_and_rollback(db_session)


def test_merchant_requires_existing_organization(db_session: Session) -> None:
    db_session.add(_merchant(18_446_744_073_709_551_614, valid_from=START))
    _assert_constraint_rejection_and_rollback(db_session)


def test_merchant_rejects_invalid_assignment_range(
    db_session: Session,
    organization: Organization,
) -> None:
    merchant = _merchant(organization.organization_id, valid_from=START)
    merchant.assignment_valid_to = START
    db_session.add(merchant)
    _assert_constraint_rejection_and_rollback(db_session)


def _organization(external_id: str) -> Organization:
    return Organization(
        external_organization_id=external_id,
        organization_name="Test Organization",
        status="active",
        registered_at=START,
    )


def _member(
    organization_id: int,
    *,
    external_id: str = "membership-test",
) -> OrganizationMember:
    return OrganizationMember(
        external_membership_id=external_id,
        organization_id=organization_id,
        status="active",
        first_invited_at=START,
        accepted_at=START,
        effective_from=START,
    )


def _consumer(external_id: str) -> Consumer:
    return Consumer(
        external_consumer_id=external_id,
        status="active",
        first_identified_at=START,
        created_at=START,
    )


def _merchant(
    organization_id: int,
    *,
    valid_from: datetime,
    external_id: str = "merchant-test",
) -> Merchant:
    return Merchant(
        merchant_id=1001,
        external_merchant_id=external_id,
        organization_id=organization_id,
        merchant_name="Test Merchant",
        status="active",
        assignment_valid_from=valid_from,
    )


def _assert_constraint_rejection_and_rollback(db_session: Session) -> None:
    with pytest.raises((IntegrityError, OperationalError)) as error_info:
        db_session.flush()
    db_session.rollback()
    _assert_expected_constraint_exception(error_info.value)


def _assert_expected_constraint_exception(
    error: DatabaseError,
) -> None:
    """Accept integrity errors or MySQL's narrowly identified CHECK violation."""
    assert isinstance(error, (IntegrityError, OperationalError))
    if isinstance(error, OperationalError):
        assert error.orig is not None
        assert error.orig.args[0] == 3819
