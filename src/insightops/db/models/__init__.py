"""Deterministic registration entry point for all implemented database models."""

from insightops.db.base import Base
from insightops.db.models.commerce import (
    CommerceOrder,
    CommerceOrderItem,
    CommerceRefund,
    PlatformFeeCharge,
    Product,
    RefundItemAllocation,
)
from insightops.db.models.identity import Consumer, Merchant, Organization, OrganizationMember
from insightops.db.models.marketing import (
    AttributedConversion,
    CampaignDailySpend,
    MarketingCampaign,
    MarketingChannel,
    MarketingTouch,
)
from insightops.db.models.saas import (
    InvoicePaymentAttempt,
    SaasPlanVersion,
    Subscription,
    SubscriptionInvoice,
    SubscriptionStateEvent,
)

__all__ = [
    "AttributedConversion",
    "Base",
    "CampaignDailySpend",
    "CommerceOrder",
    "CommerceOrderItem",
    "CommerceRefund",
    "Consumer",
    "InvoicePaymentAttempt",
    "Merchant",
    "MarketingCampaign",
    "MarketingChannel",
    "MarketingTouch",
    "Organization",
    "OrganizationMember",
    "PlatformFeeCharge",
    "Product",
    "RefundItemAllocation",
    "SaasPlanVersion",
    "Subscription",
    "SubscriptionInvoice",
    "SubscriptionStateEvent",
]
