# Revenue Loop V0.1 — evidence-gated integration

## Technical proof

```
LeadStore.ingest (authorized inbound)
  -> LeadStore.review (human VERIFIED_BUYER)
  -> prepare_sales (draft only; original SalesAgent compatible)
  -> LeadStore.prepare_crm + approve_outbox
  -> dispatch_bitrix24 (real CRM API after operator approval)
  -> Bitrix24 provider ACK / outbox EXECUTED
  -> external order in payment provider
  -> payment_to_ledger (trusted provider verifier injected)
  -> Workspace capital_engine.import_entries (trusted server-side adapter)
  -> Capital Ledger income / immutable source
```

Implemented now: `lead_os/revenue_loop.py` and `tests/test_revenue_loop.py` give an isolated, auditable, **synthetic E2E contract**, including denial tests. The default implementation performs **no external action**, does not scrape contacts, send messages, charge money, or book revenue without injected dependencies.

The SalesAgent adapter can be backed by original `Shtenco/synergy_agi_autopilot` branch `feat/capability-runtime-v1`, class `agi_autopilot.agents.sales.SalesAgent`, but its availability is a *deployment dependency*. The test stub is not the original LLM or proof of AI performance.

The Capital Ledger adapter can be backed by `Shtenco/synergy_ai_workspace`, branch `release/v1.0-desktop-rc`, `workspace.capital_engine.import_entries`. **Never send the Workspace token to the browser**. Use an authenticated server-to-server integration with organization binding and scoped service credentials, not direct import of arbitrary JSON.

## Live production blockers

- Real CRM: configure an authorized Bitrix24 webhook for `dispatch_bitrix24`, demonstrate provider acknowledgment and keep per-tenant secrets server-side.
- Real payment: implement a provider-specific server-to-server `verify_payment(order_id)` adapter that queries settled payment facts via provider-held credentials, confirms merchant/tenant, immutable provider receipt id, amount, currency, refundable/chargeback state, and reconciles to the invoice. **Never treat UI or customer supplied `provider_verified=true` as evidence**.
- Trusted ledger: implement authenticated, tenant-scoped import with durable receipt idempotency and reconciliation. Current `source_id` is an idempotency key, **not evidence**.
- Live E2E with actual authorized provider credentials, real small test charge/refund, CI plus staging, observability, and data protection review. No actual customer payment or production revenue has been verified.
- Treat synthetic test result `production_verified:false` as non-production. Do not publicly claim an end-to-end commercial sale until all preceding proofs exist.

## Run

```bash
python -m pip install -e ".[test]"
python -m pytest -vv tests/test_revenue_loop.py
python -m pytest -q
```

The integration intentionally **does not** add HTTP endpoints for order capture. Only trusted server-side, authenticated entry points should be added after a provider-specific security review.

## Data policy

External contact requires evidence of lawful origin plus operator review and opt-in (when applicable). Never mass message, harvest private profiles, publish credentials, or make automatic payments.
