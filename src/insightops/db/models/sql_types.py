"""Reusable MySQL types for the M1 physical schema."""

from sqlalchemy.dialects import mysql


def unsigned_bigint() -> mysql.BIGINT:
    """Return the canonical internal identifier type."""
    return mysql.BIGINT(unsigned=True)


def unsigned_smallint() -> mysql.SMALLINT:
    """Return the canonical positive small integer type."""
    return mysql.SMALLINT(unsigned=True)


def money_decimal() -> mysql.DECIMAL:
    """Return the exact monetary type used by persisted business facts."""
    return mysql.DECIMAL(precision=19, scale=4, asdecimal=True)


def datetime_6() -> mysql.DATETIME:
    """Return the UTC business timestamp storage type with microsecond precision."""
    return mysql.DATETIME(fsp=6)


def ascii_binary_varchar(length: int) -> mysql.VARCHAR:
    """Return a case-sensitive ASCII identifier or deterministic code type."""
    return mysql.VARCHAR(length=length, charset="ascii", collation="ascii_bin")


def currency_code_type() -> mysql.CHAR:
    """Return the fixed-width, case-sensitive currency code type."""
    return mysql.CHAR(length=3, charset="ascii", collation="ascii_bin")
