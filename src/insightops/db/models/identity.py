"""Enterprise and identity SQLAlchemy mappings for M1.1B."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from insightops.db.base import Base
from insightops.db.models.sql_types import (
    ascii_binary_varchar,
    datetime_6,
    unsigned_bigint,
)

CURRENT_TIMESTAMP_6 = text("CURRENT_TIMESTAMP(6)")


class Organization(Base):
    """A stable enterprise identity."""

    __tablename__ = "organization"
    __table_args__ = (
        UniqueConstraint("external_organization_id", name="uq_organization__external_id"),
        CheckConstraint(
            "status IN ('registered', 'active', 'suspended', 'closed')",
            name="ck_organization__status",
        ),
        CheckConstraint(
            "closed_at IS NULL OR closed_at >= registered_at",
            name="ck_organization__closed_time",
        ),
        CheckConstraint(
            "status <> 'closed' OR closed_at IS NOT NULL",
            name="ck_organization__closed_status_time",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_organization__is_test"),
        Index("ix_organization__test_registered", "is_test", "registered_at"),
        Index("ix_organization__status", "status"),
    )

    organization_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    external_organization_id: Mapped[str] = mapped_column(ascii_binary_varchar(128), nullable=False)
    organization_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    recorded_at: Mapped[datetime] = mapped_column(
        datetime_6(), nullable=False, server_default=CURRENT_TIMESTAMP_6
    )
    updated_at: Mapped[datetime] = mapped_column(
        datetime_6(),
        nullable=False,
        server_default=CURRENT_TIMESTAMP_6,
        server_onupdate=CURRENT_TIMESTAMP_6,
    )


class OrganizationMember(Base):
    """One membership relationship lifecycle within an organization."""

    __tablename__ = "organization_member"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organization.organization_id"],
            name="fk_org_member__organization",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("external_membership_id", name="uq_org_member__external_id"),
        CheckConstraint(
            "status IN ('invited', 'active', 'removed', 'expired')",
            name="ck_org_member__status",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_org_member__effective_range",
        ),
        CheckConstraint(
            "accepted_at IS NULL OR "
            "(first_invited_at IS NOT NULL AND accepted_at >= first_invited_at)",
            name="ck_org_member__invite_order",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_org_member__is_test"),
        Index(
            "ix_org_member__org_effective",
            "organization_id",
            "effective_from",
            "effective_to",
        ),
        Index("ix_org_member__org_invited", "organization_id", "first_invited_at", "is_test"),
    )

    organization_member_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    external_membership_id: Mapped[str] = mapped_column(ascii_binary_varchar(128), nullable=False)
    organization_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    external_account_id: Mapped[str | None] = mapped_column(
        ascii_binary_varchar(128), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    first_invited_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    effective_from: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    recorded_at: Mapped[datetime] = mapped_column(
        datetime_6(), nullable=False, server_default=CURRENT_TIMESTAMP_6
    )
    updated_at: Mapped[datetime] = mapped_column(
        datetime_6(),
        nullable=False,
        server_default=CURRENT_TIMESTAMP_6,
        server_onupdate=CURRENT_TIMESTAMP_6,
    )


class Consumer(Base):
    """A stable commerce consumer identity, separate from organization membership."""

    __tablename__ = "consumer"
    __table_args__ = (
        UniqueConstraint("external_consumer_id", name="uq_consumer__external_id"),
        CheckConstraint(
            "status IN ('active', 'blocked', 'closed')",
            name="ck_consumer__status",
        ),
        CheckConstraint(
            "first_identified_at >= created_at AND (closed_at IS NULL OR closed_at >= created_at)",
            name="ck_consumer__time_order",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_consumer__is_test"),
        Index("ix_consumer__test_created", "is_test", "created_at"),
        Index("ix_consumer__status", "status"),
    )

    consumer_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    external_consumer_id: Mapped[str] = mapped_column(ascii_binary_varchar(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    first_identified_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    recorded_at: Mapped[datetime] = mapped_column(
        datetime_6(), nullable=False, server_default=CURRENT_TIMESTAMP_6
    )
    updated_at: Mapped[datetime] = mapped_column(
        datetime_6(),
        nullable=False,
        server_default=CURRENT_TIMESTAMP_6,
        server_onupdate=CURRENT_TIMESTAMP_6,
    )


class Merchant(Base):
    """A stable merchant identity assigned to an organization for one valid interval."""

    __tablename__ = "merchant"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organization.organization_id"],
            name="fk_merchant__organization",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint(
            "merchant_id", "assignment_valid_from", name="uq_merchant__identity_start"
        ),
        UniqueConstraint(
            "external_merchant_id",
            "assignment_valid_from",
            name="uq_merchant__external_start",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'active', 'suspended', 'closed')",
            name="ck_merchant__status",
        ),
        CheckConstraint(
            "assignment_valid_to IS NULL OR assignment_valid_to > assignment_valid_from",
            name="ck_merchant__assignment_range",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_merchant__is_test"),
        Index(
            "ix_merchant__identity_range",
            "merchant_id",
            "assignment_valid_from",
            "assignment_valid_to",
        ),
        Index(
            "ix_merchant__org_range",
            "organization_id",
            "assignment_valid_from",
            "assignment_valid_to",
        ),
    )

    merchant_assignment_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    merchant_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    external_merchant_id: Mapped[str] = mapped_column(ascii_binary_varchar(128), nullable=False)
    organization_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    merchant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    assignment_valid_from: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    assignment_valid_to: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    recorded_at: Mapped[datetime] = mapped_column(
        datetime_6(), nullable=False, server_default=CURRENT_TIMESTAMP_6
    )
    updated_at: Mapped[datetime] = mapped_column(
        datetime_6(),
        nullable=False,
        server_default=CURRENT_TIMESTAMP_6,
        server_onupdate=CURRENT_TIMESTAMP_6,
    )
