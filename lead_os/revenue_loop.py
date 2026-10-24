"""Evidence-gated Lead OS -> AI Sales -> CRM -> payment -> capital integration.

No provider writes or financial recognition are performed here.
All externally trusted actions require injected production adapters.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Callable, Any
from .core import LeadStore


@dataclass(frozen=True)
class Order:
    order_id: str
    document_id: int
    crm_outbox_id: int
    amount: str
    currency: str


def prepare_sales(store: LeadStore, document_id: int, *, product: str,
                  proposition: str, sales_agent: Any) -> dict:
    """Prepare a draft only. Never send automatically."""
    doc = store.get(document_id)
    if not doc:
        raise KeyError(document_id)
    if doc["reviewer_label"] != "VERIFIED_BUYER":
        raise PermissionError("human buyer review required")
    if doc["lawful_basis"] not in ("inbound", "consent") or not doc["contact_opt_in"]:
        raise PermissionError("explicit inbound/consent and opt-in required")
    result = sales_agent.compose({"product": product, "value": proposition}, "next_step")
    if result.get("delivery_authority") != "NONE" or not result.get("message"):
        raise ValueError("sales agent must return an unsent draft")
    return {"lead_id": document_id, "status": "DRAFT_ONLY",
            "message": result["message"], "external_effects": False}


def payment_to_ledger(order: Order, store: LeadStore, *,
                      verify_payment: Callable[[str], dict],
                      ledger_import: Callable[[dict], dict],
                      booking_date: str) -> dict:
    """Requires a *real* trusted payment adapter which fetches an external payment
    by its order reference using server-held credentials. No user-supplied 'paid'
    flag is accepted. The ledger must be an independently implemented service.
    """
    if not order.order_id or not isinstance(order.document_id, int):
        raise ValueError("invalid order identity")
    try:
        money = Decimal(order.amount)
    except (InvalidOperation, TypeError):
        raise ValueError("invalid amount") from None
    if not money.is_finite() or money <= 0 or money != money.quantize(Decimal(".01")):
        raise ValueError("invalid amount")
    if len(order.currency) != 3 or not order.currency.isalpha() or order.currency.upper() != order.currency:
        raise ValueError("invalid currency")
    lead = store.get(order.document_id)
    outbox = store.outbox(order.crm_outbox_id)
    if not lead or not outbox or outbox["document_id"] != order.document_id:
        raise PermissionError("CRM provenance mismatch")
    if outbox["state"] != "EXECUTED":
        raise PermissionError("CRM provider acknowledgment required")
    payment = verify_payment(order.order_id)
    if payment.get("provider_verified") is not True or payment.get("status") != "settled":
        raise PermissionError("trusted externally verified settlement required")
    if str(payment.get("order_id")) != order.order_id:
        raise PermissionError("payment order mismatch")
    if payment.get("currency") != order.currency:
        raise PermissionError("payment currency mismatch")
    try:
        paid = Decimal(str(payment["amount"]))
    except (KeyError, InvalidOperation, TypeError):
        raise PermissionError("invalid payment amount") from None
    if paid != money:
        raise PermissionError("payment amount mismatch")
    receipt = str(payment.get("receipt_id") or "")
    if not receipt or len(receipt) > 160:
        raise PermissionError("provider receipt required")
    # Separate source identity and entry id make replays idempotent in Capital Ledger.
    source_id = "payment:" + sha256((str(payment.get("provider"))+":"+receipt).encode()).hexdigest()
    batch = {
        "source_id": source_id,
        "currency": order.currency,
        "period_start": booking_date,
        "period_end": booking_date,
        "entries": [{
            "entry_id": "order-" + sha256(order.order_id.encode()).hexdigest()[:32],
            "date": booking_date, "currency": order.currency,
            "kind": "income", "amount": str(money),
            "memo": "External paid order "+order.order_id[:80],
        }],
    }
    result = ledger_import(batch)
    return {"order_id": order.order_id, "lead_id": order.document_id,
            "crm_outbox_id": order.crm_outbox_id, "receipt_id": receipt,
            "source_id": source_id, "ledger_status": result.get("status"),
            "verification": "INJECTED_VERIFIER", "production_verified": False,
            "note": "Tests use fake adapters. Production proof requires bank/provider reconciliation and deployment evidence."}
