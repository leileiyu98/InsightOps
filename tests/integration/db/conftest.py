"""Shared fixtures for real MySQL schema and constraint tests."""

import fcntl
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from alembic import command
from insightops.core.config import load_settings
from insightops.db.models import (
    Organization,
    SaasPlanVersion,
    Subscription,
    SubscriptionInvoice,
)
from insightops.db.session import create_database_engine

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATABASE_TEST_LOCK = Path("/tmp/insightops-m1-1b-database-tests.lock")


@pytest.fixture(scope="session", autouse=True)
def serialize_shared_schema_tests() -> Generator[None]:
    """Prevent migration and constraint tests from sharing one schema concurrently."""
    with DATABASE_TEST_LOCK.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    """Return an Alembic configuration with absolute project paths."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    return config


@pytest.fixture(scope="session")
def database_engine(alembic_config: Config) -> Generator[Engine]:
    """Provide an engine against a schema guaranteed to be at migration head."""
    command.upgrade(alembic_config, "head")
    engine = create_database_engine(load_settings())
    try:
        yield engine
    finally:
        engine.dispose()
        command.upgrade(alembic_config, "head")


@pytest.fixture
def db_session(database_engine: Engine) -> Generator[Session]:
    """Provide a transaction-isolated session for one constraint test."""
    connection = database_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def organization(db_session: Session) -> Organization:
    """Insert a deterministic organization valid for dependent fixtures."""
    organization = Organization(
        external_organization_id="org-fixture",
        organization_name="Fixture Organization",
        status="active",
        registered_at="2025-01-01 00:00:00.000000",
    )
    db_session.add(organization)
    db_session.flush()
    return organization


@pytest.fixture
def plan(db_session: Session) -> SaasPlanVersion:
    """Insert a deterministic active monthly plan."""
    plan = SaasPlanVersion(
        plan_code="growth",
        version_number=1,
        plan_name="Growth",
        tier_code="growth",
        billing_interval="monthly",
        recurring_amount="100.0000",
        status="active",
        effective_from="2025-01-01 00:00:00.000000",
        created_at="2024-12-01 00:00:00.000000",
    )
    db_session.add(plan)
    db_session.flush()
    return plan


@pytest.fixture
def subscription(
    db_session: Session,
    organization: Organization,
    plan: SaasPlanVersion,
) -> Subscription:
    """Insert a deterministic active subscription."""
    subscription = Subscription(
        external_subscription_id="sub-fixture",
        organization_id=organization.organization_id,
        current_plan_version_id=plan.saas_plan_version_id,
        current_status="active",
        created_at="2025-01-01 00:00:00.000000",
        first_activated_at="2025-01-02 00:00:00.000000",
        current_period_started_at="2025-02-01 00:00:00.000000",
        current_period_ends_at="2025-03-01 00:00:00.000000",
    )
    db_session.add(subscription)
    db_session.flush()
    return subscription


@pytest.fixture
def invoice(db_session: Session, subscription: Subscription) -> SubscriptionInvoice:
    """Insert a deterministic open subscription invoice."""
    invoice = SubscriptionInvoice(
        external_invoice_id="invoice-fixture",
        subscription_id=subscription.subscription_id,
        status="open",
        subscription_fee_amount="100.0000",
        tax_amount="10.0000",
        one_time_amount="0.0000",
        total_amount="110.0000",
        issued_at="2025-02-01 00:00:00.000000",
        due_at="2025-02-15 00:00:00.000000",
        created_at="2025-02-01 00:00:00.000000",
    )
    db_session.add(invoice)
    db_session.flush()
    return invoice
