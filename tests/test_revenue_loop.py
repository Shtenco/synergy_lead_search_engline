"""Simulated evidence chain; no real payment or API credentials."""
from decimal import Decimal
import pytest
from lead_os.core import LeadStore
from lead_os.revenue_loop import Order, prepare_sales, payment_to_ledger

def fixture(tmp_path, opt_in=True):
    store=LeadStore(tmp_path/"leads.db")
    lead=store.ingest({"source":"inbound-test","external_id":"123",
        "source_url":"https://example.org/inbound/123",
        "text":"Хочу купить квартиру. Бюджет 100000 евро",
        "domain":"property","lawful_basis":"inbound","contact_opt_in":opt_in})
    return store, lead["id"]

class Sales:
    def compose(self, profile, kind):
        return {"message":"Здравствуйте! Подготовим коммерческое предложение.",
                "delivery_authority":"NONE"}

def confirmed(store, lid):
    store.review(lid,"operator","VERIFIED_BUYER","inbound checked")
    item=store.prepare_crm(lid,"bitrix24","Interested buyer")
    store.approve_outbox(item["id"],"operator")
    # Test-only provider response. This does NOT contact Bitrix24.
    store.complete_outbox(item["id"],{"crm_id":"FAKE-CRM-TEST"})
    return item["id"]

def receipt(order_id="order-001", amount="4990.00", currency="KZT", status="settled"):
    return {"provider_verified":True,"provider":"FAKE_TEST_PROVIDER",
            "status":status,"order_id":order_id,"amount":amount,"currency":currency,
            "receipt_id":"test-receipt-001"}

def test_end_to_end_simulated(tmp_path):
    store,lid=fixture(tmp_path)
    with pytest.raises(PermissionError):
        prepare_sales(store,lid,product="SYNERGY",proposition="больше лидов",sales_agent=Sales())
    oid=confirmed(store,lid)
    draft=prepare_sales(store,lid,product="SYNERGY",proposition="больше лидов",sales_agent=Sales())
    assert draft["status"]=="DRAFT_ONLY" and draft["external_effects"] is False
    batches=[]
    def write(batch):
        batches.append(batch)
        return {"status":"imported_source_unverified"}
    order=Order("order-001",lid,oid,"4990.00","KZT")
    r=payment_to_ledger(order,store,verify_payment=lambda _:receipt(),
                        ledger_import=write,booking_date="2026-10-24")
    assert r["production_verified"] is False
    assert batches[0]["entries"][0]["amount"]=="4990.00"
    assert batches[0]["entries"][0]["kind"]=="income"
    assert batches[0]["currency"]=="KZT"
    assert batches[0]["source_id"].startswith("payment:")

@pytest.mark.parametrize("bad",[
    {"provider_verified":False}, {"status":"pending"},
    {"order_id":"wrong"}, {"amount":"4991.00"}, {"currency":"USD"},
    {"receipt_id":""}
])
def test_invalid_payment_rejected(tmp_path,bad):
    store,lid=fixture(tmp_path)
    oid=confirmed(store,lid)
    p=receipt();p.update(bad)
    writes=[]
    with pytest.raises(PermissionError):
        payment_to_ledger(Order("order-001",lid,oid,"4990.00","KZT"),store,
                          verify_payment=lambda _:p,ledger_import=writes.append,
                          booking_date="2026-10-24")
    assert writes==[]

def test_crm_must_be_acked(tmp_path):
    store,lid=fixture(tmp_path)
    store.review(lid,"operator","VERIFIED_BUYER")
    item=store.prepare_crm(lid,"bitrix24","Buyer")
    store.approve_outbox(item["id"],"operator")
    writes=[]
    with pytest.raises(PermissionError):
        payment_to_ledger(Order("order-001",lid,item["id"],"4990.00","KZT"),store,
                          verify_payment=lambda _:receipt(),ledger_import=writes.append,
                          booking_date="2026-10-24")
    assert writes==[]

def test_no_contact_without_consent(tmp_path):
    store,lid=fixture(tmp_path,opt_in=False)
    store.review(lid,"operator","VERIFIED_BUYER")
    with pytest.raises(PermissionError):
        prepare_sales(store,lid,product="SYNERGY",proposition="аналитика",
                      sales_agent=Sales())

def test_invalid_amount(tmp_path):
    store,lid=fixture(tmp_path)
    oid=confirmed(store,lid)
    for value in ("0","-1","NaN","Infinity","100.001"):
        with pytest.raises(ValueError):
            payment_to_ledger(Order("order-001",lid,oid,value,"KZT"),store,
                              verify_payment=lambda _:receipt(),ledger_import=lambda _:None,
                              booking_date="2026-10-24")
