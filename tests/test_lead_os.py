import json
from pathlib import Path
import pytest
from lead_os.core import classify, LeadStore
from lead_os.import_v7 import normalize_v7, import_file

def doc(**kwargs):
    p=dict(source="vk-v7",external_id="42",source_url="https://vk.com/wall-1_42",
           text="Хочу купить квартиру в Аликанте, бюджет 250000 евро, срочно",domain="property")
    p.update(kwargs);return p

def test_hot_is_only_candidate():
    r=classify(doc()["text"])
    assert r["bucket"]=="POTENTIAL_REVIEW"
    assert r["verified"] is False and r["score"]>=50

@pytest.mark.parametrize("text",[
    "Не хочу купить квартиру в Испании, не пишите",
    "Продаю квартиру в Аликанте. Наше агентство предлагает скидку",
    "Квартира в продаже, услуги риелтора",
])
def test_negative_or_seller_not_verified(text):
    assert classify(text)["bucket"]!="POTENTIAL_REVIEW"

def test_residency():
    r=classify("Хочу оформить ВНЖ Испании. Сколько стоит консультация?","residency")
    assert r["bucket"]=="POTENTIAL_REVIEW"

def test_ingest_dedup_and_review(tmp_path):
    db=LeadStore(tmp_path/"store.db")
    first=db.ingest(doc()); second=db.ingest(doc(text="changed"))
    assert first["created"] is True and second["created"] is False
    assert db.metrics()["documents"]==1
    assert len(db.search("Аликанте"))==1
    with pytest.raises(ValueError): db.prepare_crm(first["id"],"bitrix24","X")
    db.review(first["id"],"human-operator","VERIFIED_BUYER","Confirmed inbound request")
    with pytest.raises(ValueError): db.prepare_crm(first["id"],"bitrix24","X")
    assert len(db.search())==1

def test_outbox_requires_documented_basis_and_approval(tmp_path):
    db=LeadStore(tmp_path/"store.db")
    r=db.ingest(doc(lawful_basis="inbound",contact_opt_in=True))
    db.review(r["id"],"human","VERIFIED_BUYER")
    item=db.prepare_crm(r["id"],"bitrix24","Interested buyer")
    assert item["state"]=="PENDING_APPROVAL"
    assert db.approve_outbox(item["id"],"human")["state"]=="APPROVED"
    with pytest.raises(ValueError): db.approve_outbox(item["id"],"human")

def test_bad_opt_in_rejected(tmp_path):
    db=LeadStore(tmp_path/"store.db")
    with pytest.raises(ValueError): db.ingest(doc(contact_opt_in=True))
    with pytest.raises(ValueError): db.ingest(doc(source_url="file:///secrets"))

def test_v7_offline_import(tmp_path):
    p=tmp_path/"v7.jsonl"
    p.write_text(json.dumps({"id":42,"url":"https://vk.com/wall-1_42","text":doc()["text"]})+"\n"*0+
                 "\n"+json.dumps({"id":42,"url":"https://vk.com/wall-1_42","text":doc()["text"]})+"\n",encoding="utf8")
    result=import_file(str(p),str(tmp_path/"store.db"))
    assert result["created"]==1 and result["duplicate"]==1

def test_api_fail_closed(monkeypatch,tmp_path):
    from fastapi.testclient import TestClient
    from lead_os.api import app
    monkeypatch.delenv("LEAD_OS_API_TOKEN",raising=False)
    c=TestClient(app)
    assert c.get("/health").status_code==200
    assert c.get("/v1/search").status_code==503
    monkeypatch.setenv("LEAD_OS_API_TOKEN","testing-token-with-more-than-24-characters")
    monkeypatch.setenv("LEAD_OS_DB",str(tmp_path/"api.db"))
    assert c.get("/v1/search").status_code==401
    assert c.get("/v1/search",headers={"Authorization":"Bearer testing-token-with-more-than-24-characters"}).status_code==200
