"""Real MySQL constraint tests for M1.1C commerce tables."""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError
from sqlalchemy.orm import Session

from insightops.db.models import (
    CommerceOrder,
    CommerceOrderItem,
    CommerceRefund,
    Consumer,
    Merchant,
    PlatformFeeCharge,
    Product,
    RefundItemAllocation,
)

START = datetime(2025, 1, 1)
PAID = datetime(2025, 1, 2)
FULFILLED = datetime(2025, 1, 3)
COMPLETED = datetime(2025, 1, 4)
ZERO = Decimal("0.0000")
TEN = Decimal("10.0000")


@pytest.fixture
def order_item(
    db_session: Session,
    commerce_order: CommerceOrder,
    product: Product,
) -> CommerceOrderItem:
    """Insert a deterministic order item for refund allocation tests."""
    order_item = _order_item(commerce_order, product)
    db_session.add(order_item)
    db_session.flush()
    return order_item


@pytest.fixture
def refund(db_session: Session, commerce_order: CommerceOrder) -> CommerceRefund:
    """Insert a deterministic requested refund."""
    refund = _refund(commerce_order)
    db_session.add(refund)
    db_session.flush()
    return refund


def test_products_accept_case_distinct_external_ids_and_category_codes(
    db_session: Session,
    merchant: Merchant,
) -> None:
    upper = _product(merchant, external_id="Product-Case", category_code="Books")
    lower = _product(merchant, external_id="product-case", category_code="books")
    db_session.add_all([upper, lower])
    db_session.flush()

    upper_count = db_session.scalar(
        select(func.count()).select_from(Product).where(Product.category_code == "Books")
    )
    lower_count = db_session.scalar(
        select(func.count()).select_from(Product).where(Product.category_code == "books")
    )
    assert upper_count == 1
    assert lower_count == 1


def test_duplicate_product_external_id_is_rejected(
    db_session: Session,
    merchant: Merchant,
) -> None:
    db_session.add_all([_product(merchant), _product(merchant)])
    _assert_constraint_rejection_and_rollback(db_session)


def test_product_requires_existing_merchant(db_session: Session) -> None:
    product = Product(
        external_product_id="product-missing-merchant",
        merchant_assignment_id=18_446_744_073_709_551_614,
        product_title="Missing Merchant",
        category_code="software",
        status="active",
        created_at=START,
    )
    db_session.add(product)
    _assert_constraint_rejection_and_rollback(db_session)


def test_product_rejects_invalid_status_and_time(
    db_session: Session,
    merchant: Merchant,
) -> None:
    product = _product(merchant)
    product.status = "unknown"
    product.first_published_at = datetime(2024, 12, 31)
    db_session.add(product)
    _assert_constraint_rejection_and_rollback(db_session)


def test_archived_product_requires_archived_time(
    db_session: Session,
    merchant: Merchant,
) -> None:
    product = _product(merchant)
    product.status = "archived"
    db_session.add(product)
    _assert_constraint_rejection_and_rollback(db_session)


def test_valid_order_lifecycle_states_are_accepted(
    db_session: Session,
    consumer: Consumer,
    merchant: Merchant,
) -> None:
    paid = _order(consumer, merchant, external_id="order-paid", status="paid")
    paid.first_paid_at = PAID

    fulfilled = _order(consumer, merchant, external_id="order-fulfilled", status="fulfilled")
    fulfilled.first_paid_at = PAID
    fulfilled.fulfilled_at = FULFILLED

    completed = _order(consumer, merchant, external_id="order-completed", status="completed")
    completed.first_paid_at = PAID
    completed.completed_at = COMPLETED

    cancelled = _order(consumer, merchant, external_id="order-cancelled", status="cancelled")
    cancelled.first_paid_at = PAID
    cancelled.cancelled_at = COMPLETED

    db_session.add_all([paid, fulfilled, completed, cancelled])
    db_session.flush()


@pytest.mark.parametrize("status", ["paid", "fulfilled", "completed"])
def test_paid_lifecycle_states_require_first_paid_time(
    db_session: Session,
    consumer: Consumer,
    merchant: Merchant,
    status: str,
) -> None:
    order = _order(consumer, merchant, status=status)
    if status == "fulfilled":
        order.fulfilled_at = FULFILLED
    if status == "completed":
        order.completed_at = COMPLETED
    db_session.add(order)
    _assert_constraint_rejection_and_rollback(db_session)


def test_fulfilled_order_requires_fulfilled_time(
    db_session: Session,
    consumer: Consumer,
    merchant: Merchant,
) -> None:
    order = _order(consumer, merchant, status="fulfilled")
    order.first_paid_at = PAID
    db_session.add(order)
    _assert_constraint_rejection_and_rollback(db_session)


def test_completed_order_requires_completed_time(
    db_session: Session,
    consumer: Consumer,
    merchant: Merchant,
) -> None:
    order = _order(consumer, merchant, status="completed")
    order.first_paid_at = PAID
    db_session.add(order)
    _assert_constraint_rejection_and_rollback(db_session)


def test_cancelled_order_requires_cancelled_time(
    db_session: Session,
    consumer: Consumer,
    merchant: Merchant,
) -> None:
    db_session.add(_order(consumer, merchant, status="cancelled"))
    _assert_constraint_rejection_and_rollback(db_session)


def test_order_rejects_invalid_lifecycle_order(
    db_session: Session,
    consumer: Consumer,
    merchant: Merchant,
) -> None:
    order = _order(consumer, merchant, status="completed")
    order.first_paid_at = PAID
    order.fulfilled_at = COMPLETED
    order.completed_at = FULFILLED
    db_session.add(order)
    _assert_constraint_rejection_and_rollback(db_session)


def test_order_rejects_invalid_status_and_currency(
    db_session: Session,
    consumer: Consumer,
    merchant: Merchant,
) -> None:
    order = _order(consumer, merchant)
    order.status = "unknown"
    order.currency_code = "EUR"
    db_session.add(order)
    _assert_constraint_rejection_and_rollback(db_session)


def test_order_requires_existing_consumer_and_merchant(db_session: Session) -> None:
    order = CommerceOrder(
        external_order_id="order-missing-parents",
        consumer_id=18_446_744_073_709_551_614,
        merchant_assignment_id=18_446_744_073_709_551_613,
        status="created",
        currency_code="USD",
        created_at=START,
    )
    db_session.add(order)
    _assert_constraint_rejection_and_rollback(db_session)


def test_duplicate_order_external_id_is_rejected(
    db_session: Session,
    consumer: Consumer,
    merchant: Merchant,
) -> None:
    db_session.add_all([_order(consumer, merchant), _order(consumer, merchant)])
    _assert_constraint_rejection_and_rollback(db_session)


def test_order_business_time_cannot_precede_creation(
    db_session: Session,
    consumer: Consumer,
    merchant: Merchant,
) -> None:
    order = _order(consumer, merchant, status="paid")
    order.first_paid_at = datetime(2024, 12, 31)
    db_session.add(order)
    _assert_constraint_rejection_and_rollback(db_session)


def test_order_item_accepts_zero_amount_and_case_distinct_external_ids(
    db_session: Session,
    commerce_order: CommerceOrder,
    product: Product,
) -> None:
    upper = _order_item(commerce_order, product, external_id="Item-Case")
    upper.discounted_item_amount = ZERO
    lower = _order_item(commerce_order, product, external_id="item-case")
    db_session.add_all([upper, lower])
    db_session.flush()


def test_duplicate_order_item_business_key_is_rejected(
    db_session: Session,
    commerce_order: CommerceOrder,
    product: Product,
) -> None:
    db_session.add_all([_order_item(commerce_order, product), _order_item(commerce_order, product)])
    _assert_constraint_rejection_and_rollback(db_session)


def test_order_item_rejects_zero_quantity(
    db_session: Session,
    commerce_order: CommerceOrder,
    product: Product,
) -> None:
    item = _order_item(commerce_order, product)
    item.quantity = 0
    db_session.add(item)
    _assert_constraint_rejection_and_rollback(db_session)


def test_order_item_rejects_negative_amount(
    db_session: Session,
    commerce_order: CommerceOrder,
    product: Product,
) -> None:
    item = _order_item(commerce_order, product)
    item.discounted_item_amount = Decimal("-0.0001")
    db_session.add(item)
    _assert_constraint_rejection_and_rollback(db_session)


def test_order_item_rejects_non_usd_and_empty_category(
    db_session: Session,
    commerce_order: CommerceOrder,
    product: Product,
) -> None:
    item = _order_item(commerce_order, product)
    item.currency_code = "EUR"
    item.product_category_code = ""
    db_session.add(item)
    _assert_constraint_rejection_and_rollback(db_session)


def test_order_item_requires_existing_order_and_product(db_session: Session) -> None:
    item = CommerceOrderItem(
        external_order_item_id="item-missing-parents",
        commerce_order_id=18_446_744_073_709_551_614,
        product_id=18_446_744_073_709_551_613,
        product_category_code="software",
        quantity=1,
        discounted_item_amount=TEN,
        currency_code="USD",
        created_at=START,
    )
    db_session.add(item)
    _assert_constraint_rejection_and_rollback(db_session)


def test_refund_accepts_valid_states_and_zero_amounts(
    db_session: Session,
    commerce_order: CommerceOrder,
) -> None:
    requested = _refund(commerce_order, external_id="refund-requested")
    pending = _refund(commerce_order, external_id="refund-pending", status="pending")
    succeeded = _refund(commerce_order, external_id="refund-succeeded", status="succeeded")
    succeeded.succeeded_at = PAID
    failed = _refund(commerce_order, external_id="refund-failed", status="failed")
    failed.failed_at = PAID
    cancelled = _refund(commerce_order, external_id="refund-cancelled", status="cancelled")
    cancelled.cancelled_at = PAID
    db_session.add_all([requested, pending, succeeded, failed, cancelled])
    db_session.flush()


@pytest.mark.parametrize("status", ["succeeded", "failed", "cancelled"])
def test_refund_terminal_status_requires_matching_time(
    db_session: Session,
    commerce_order: CommerceOrder,
    status: str,
) -> None:
    db_session.add(_refund(commerce_order, status=status))
    _assert_constraint_rejection_and_rollback(db_session)


def test_refund_rejects_conflicting_terminal_times(
    db_session: Session,
    commerce_order: CommerceOrder,
) -> None:
    refund = _refund(commerce_order, status="succeeded")
    refund.succeeded_at = PAID
    refund.failed_at = PAID
    db_session.add(refund)
    _assert_constraint_rejection_and_rollback(db_session)


def test_pending_refund_cannot_have_terminal_time(
    db_session: Session,
    commerce_order: CommerceOrder,
) -> None:
    refund = _refund(commerce_order, status="pending")
    refund.succeeded_at = PAID
    db_session.add(refund)
    _assert_constraint_rejection_and_rollback(db_session)


def test_refund_rejects_invalid_status(
    db_session: Session,
    commerce_order: CommerceOrder,
) -> None:
    refund = _refund(commerce_order)
    refund.status = "unknown"
    db_session.add(refund)
    _assert_constraint_rejection_and_rollback(db_session)


def test_refund_rejects_invalid_time_order(
    db_session: Session,
    commerce_order: CommerceOrder,
) -> None:
    refund = _refund(commerce_order)
    refund.processed_at = datetime(2024, 12, 31)
    db_session.add(refund)
    _assert_constraint_rejection_and_rollback(db_session)


def test_refund_rejects_negative_or_mismatched_amount(
    db_session: Session,
    commerce_order: CommerceOrder,
) -> None:
    refund = _refund(commerce_order)
    refund.item_refund_amount = Decimal("-0.0001")
    refund.total_refund_amount = Decimal("1.0000")
    db_session.add(refund)
    _assert_constraint_rejection_and_rollback(db_session)


def test_refund_total_must_match_components(
    db_session: Session,
    commerce_order: CommerceOrder,
) -> None:
    refund = _refund(commerce_order)
    refund.item_refund_amount = TEN
    refund.total_refund_amount = Decimal("9.0000")
    db_session.add(refund)
    _assert_constraint_rejection_and_rollback(db_session)


def test_refund_rejects_non_usd(db_session: Session, commerce_order: CommerceOrder) -> None:
    refund = _refund(commerce_order)
    refund.currency_code = "EUR"
    db_session.add(refund)
    _assert_constraint_rejection_and_rollback(db_session)


def test_refund_requires_existing_order(db_session: Session) -> None:
    refund = _refund_for_order_id(18_446_744_073_709_551_614)
    db_session.add(refund)
    _assert_constraint_rejection_and_rollback(db_session)


def test_duplicate_refund_external_id_is_rejected(
    db_session: Session,
    commerce_order: CommerceOrder,
) -> None:
    db_session.add_all([_refund(commerce_order), _refund(commerce_order)])
    _assert_constraint_rejection_and_rollback(db_session)


def test_allocation_accepts_zero_amount(
    db_session: Session,
    refund: CommerceRefund,
    order_item: CommerceOrderItem,
) -> None:
    allocation = _allocation(refund, order_item)
    allocation.allocated_item_amount = ZERO
    db_session.add(allocation)
    db_session.flush()


def test_duplicate_refund_item_allocation_is_rejected(
    db_session: Session,
    refund: CommerceRefund,
    order_item: CommerceOrderItem,
) -> None:
    db_session.add_all(
        [
            _allocation(refund, order_item, external_id="allocation-one"),
            _allocation(refund, order_item, external_id="allocation-two"),
        ]
    )
    _assert_constraint_rejection_and_rollback(db_session)


def test_duplicate_allocation_external_id_is_rejected(
    db_session: Session,
    commerce_order: CommerceOrder,
    product: Product,
    refund: CommerceRefund,
    order_item: CommerceOrderItem,
) -> None:
    second_item = _order_item(commerce_order, product, external_id="order-item-two")
    db_session.add(second_item)
    db_session.flush()
    db_session.add_all(
        [
            _allocation(refund, order_item, external_id="allocation-duplicate"),
            _allocation(refund, second_item, external_id="allocation-duplicate"),
        ]
    )
    _assert_constraint_rejection_and_rollback(db_session)


def test_allocation_rejects_negative_amount_and_non_usd(
    db_session: Session,
    refund: CommerceRefund,
    order_item: CommerceOrderItem,
) -> None:
    allocation = _allocation(refund, order_item)
    allocation.allocated_item_amount = Decimal("-0.0001")
    allocation.currency_code = "EUR"
    db_session.add(allocation)
    _assert_constraint_rejection_and_rollback(db_session)


def test_allocation_rejects_correction_before_creation(
    db_session: Session,
    refund: CommerceRefund,
    order_item: CommerceOrderItem,
) -> None:
    allocation = _allocation(refund, order_item)
    allocation.corrected_at = datetime(2024, 12, 31)
    db_session.add(allocation)
    _assert_constraint_rejection_and_rollback(db_session)


def test_allocation_requires_existing_refund_and_order_item(db_session: Session) -> None:
    allocation = RefundItemAllocation(
        external_refund_allocation_id="allocation-missing-parents",
        commerce_refund_id=18_446_744_073_709_551_614,
        commerce_order_item_id=18_446_744_073_709_551_613,
        allocated_item_amount=ZERO,
        currency_code="USD",
        created_at=START,
    )
    db_session.add(allocation)
    _assert_constraint_rejection_and_rollback(db_session)


def test_platform_fee_accepts_valid_states_zero_and_multiple_null_provider_ids(
    db_session: Session,
    commerce_order: CommerceOrder,
) -> None:
    pending = _fee(commerce_order, external_id="fee-pending")
    succeeded = _fee(commerce_order, external_id="fee-succeeded", status="succeeded")
    succeeded.succeeded_at = PAID
    failed = _fee(commerce_order, external_id="fee-failed", status="failed")
    failed.failed_at = PAID
    cancelled = _fee(commerce_order, external_id="fee-cancelled", status="cancelled")
    cancelled.cancelled_at = PAID
    db_session.add_all([pending, succeeded, failed, cancelled])
    db_session.flush()


def test_platform_fee_provider_charge_id_is_unique_when_present(
    db_session: Session,
    commerce_order: CommerceOrder,
) -> None:
    first = _fee(commerce_order, external_id="fee-one")
    first.provider_charge_id = "provider-charge"
    second = _fee(commerce_order, external_id="fee-two")
    second.provider_charge_id = "provider-charge"
    db_session.add_all([first, second])
    _assert_constraint_rejection_and_rollback(db_session)


def test_duplicate_platform_fee_external_id_is_rejected(
    db_session: Session,
    commerce_order: CommerceOrder,
) -> None:
    db_session.add_all([_fee(commerce_order), _fee(commerce_order)])
    _assert_constraint_rejection_and_rollback(db_session)


@pytest.mark.parametrize("status", ["succeeded", "failed", "cancelled"])
def test_platform_fee_terminal_status_requires_matching_time(
    db_session: Session,
    commerce_order: CommerceOrder,
    status: str,
) -> None:
    db_session.add(_fee(commerce_order, status=status))
    _assert_constraint_rejection_and_rollback(db_session)


def test_platform_fee_rejects_terminal_time_before_attempt(
    db_session: Session,
    commerce_order: CommerceOrder,
) -> None:
    fee = _fee(commerce_order, status="succeeded")
    fee.succeeded_at = datetime(2024, 12, 31)
    db_session.add(fee)
    _assert_constraint_rejection_and_rollback(db_session)


def test_pending_platform_fee_cannot_have_terminal_time(
    db_session: Session,
    commerce_order: CommerceOrder,
) -> None:
    fee = _fee(commerce_order)
    fee.failed_at = PAID
    db_session.add(fee)
    _assert_constraint_rejection_and_rollback(db_session)


def test_platform_fee_rejects_invalid_status(
    db_session: Session,
    commerce_order: CommerceOrder,
) -> None:
    fee = _fee(commerce_order)
    fee.status = "unknown"
    db_session.add(fee)
    _assert_constraint_rejection_and_rollback(db_session)


def test_platform_fee_rejects_negative_amount_and_non_usd(
    db_session: Session,
    commerce_order: CommerceOrder,
) -> None:
    fee = _fee(commerce_order)
    fee.fee_amount = Decimal("-0.0001")
    fee.currency_code = "EUR"
    db_session.add(fee)
    _assert_constraint_rejection_and_rollback(db_session)


def test_platform_fee_requires_existing_order(db_session: Session) -> None:
    fee = PlatformFeeCharge(
        external_fee_charge_id="fee-missing-order",
        commerce_order_id=18_446_744_073_709_551_614,
        status="pending",
        fee_amount=ZERO,
        currency_code="USD",
        attempted_at=START,
    )
    db_session.add(fee)
    _assert_constraint_rejection_and_rollback(db_session)


def test_commerce_boolean_check_rejects_non_boolean_integer(
    db_session: Session,
    merchant: Merchant,
) -> None:
    with pytest.raises((IntegrityError, OperationalError)) as error_info:
        db_session.execute(
            text(
                "INSERT INTO product "
                "(external_product_id, merchant_assignment_id, product_title, category_code, "
                "status, created_at, is_test) "
                "VALUES ('product-invalid-boolean', :merchant_id, 'Invalid', 'software', "
                "'active', :created_at, 2)"
            ),
            {"merchant_id": merchant.merchant_assignment_id, "created_at": START},
        )
    db_session.rollback()
    _assert_expected_constraint_exception(error_info.value)


def test_restrict_prevents_deleting_referenced_product(
    db_session: Session,
    product: Product,
    order_item: CommerceOrderItem,
) -> None:
    assert order_item.product_id == product.product_id
    db_session.delete(product)
    _assert_constraint_rejection_and_rollback(db_session)


def _product(
    merchant: Merchant,
    *,
    external_id: str = "product-test",
    category_code: str = "software",
) -> Product:
    return Product(
        external_product_id=external_id,
        merchant_assignment_id=merchant.merchant_assignment_id,
        product_title="Test Product",
        category_code=category_code,
        status="active",
        created_at=START,
        first_published_at=PAID,
    )


def _order(
    consumer: Consumer,
    merchant: Merchant,
    *,
    external_id: str = "order-test",
    status: str = "created",
) -> CommerceOrder:
    return CommerceOrder(
        external_order_id=external_id,
        consumer_id=consumer.consumer_id,
        merchant_assignment_id=merchant.merchant_assignment_id,
        status=status,
        currency_code="USD",
        created_at=START,
    )


def _order_item(
    order: CommerceOrder,
    product: Product,
    *,
    external_id: str = "order-item-test",
) -> CommerceOrderItem:
    return CommerceOrderItem(
        external_order_item_id=external_id,
        commerce_order_id=order.commerce_order_id,
        product_id=product.product_id,
        product_category_code="software",
        quantity=1,
        discounted_item_amount=TEN,
        currency_code="USD",
        created_at=START,
    )


def _refund(
    order: CommerceOrder,
    *,
    external_id: str = "refund-test",
    status: str = "requested",
) -> CommerceRefund:
    return _refund_for_order_id(order.commerce_order_id, external_id=external_id, status=status)


def _refund_for_order_id(
    order_id: int,
    *,
    external_id: str = "refund-test",
    status: str = "requested",
) -> CommerceRefund:
    return CommerceRefund(
        external_refund_id=external_id,
        commerce_order_id=order_id,
        status=status,
        item_refund_amount=ZERO,
        tax_refund_amount=ZERO,
        shipping_refund_amount=ZERO,
        total_refund_amount=ZERO,
        currency_code="USD",
        requested_at=START,
    )


def _allocation(
    refund: CommerceRefund,
    order_item: CommerceOrderItem,
    *,
    external_id: str = "allocation-test",
) -> RefundItemAllocation:
    return RefundItemAllocation(
        external_refund_allocation_id=external_id,
        commerce_refund_id=refund.commerce_refund_id,
        commerce_order_item_id=order_item.commerce_order_item_id,
        allocated_item_amount=ZERO,
        currency_code="USD",
        created_at=START,
    )


def _fee(
    order: CommerceOrder,
    *,
    external_id: str = "fee-test",
    status: str = "pending",
) -> PlatformFeeCharge:
    return PlatformFeeCharge(
        external_fee_charge_id=external_id,
        commerce_order_id=order.commerce_order_id,
        status=status,
        fee_amount=ZERO,
        currency_code="USD",
        attempted_at=START,
    )


def _assert_constraint_rejection_and_rollback(db_session: Session) -> None:
    with pytest.raises((IntegrityError, OperationalError)) as error_info:
        db_session.flush()
    db_session.rollback()
    _assert_expected_constraint_exception(error_info.value)


def _assert_expected_constraint_exception(error: DatabaseError) -> None:
    """Accept integrity errors or MySQL's narrowly identified CHECK violation."""
    assert isinstance(error, (IntegrityError, OperationalError))
    if isinstance(error, OperationalError):
        assert error.orig is not None
        assert error.orig.args[0] == 3819
