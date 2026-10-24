"""V8 API. All read/write endpoints require an explicit configured bearer token."""
from __future__ import annotations
import hmac
import os
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from .core import LeadStore

app = FastAPI(title="SYNERGY Real Estate Lead OS V8", version="0.8.0")

def auth(authorization: str | None = Header(default=None)) -> str:
    token = os.getenv("LEAD_OS_API_TOKEN", "")
    if len(token) < 24:
        raise HTTPException(503, "LEAD_OS_API_TOKEN must be configured (24+ characters)")
    candidate = (authorization or "").removeprefix("Bearer ")
    if not hmac.compare_digest(candidate, token):
        raise HTTPException(401, "unauthorized")
    return "operator"

def store() -> LeadStore:
    return LeadStore(os.getenv("LEAD_OS_DB", "runtime/lead_os.sqlite3"))

class DocumentIn(BaseModel):
    source: str
    external_id: str
    source_url: str
    text: str = Field(min_length=1, max_length=20000)
    domain: str = "property"
    doc_type: str = "post"
    source_at: float | None = None
    lawful_basis: str = "none"
    contact_opt_in: bool = False

class ReviewIn(BaseModel):
    label: str
    note: str = ""

class CRMIn(BaseModel):
    title: str = "Real Estate Buyer"
    provider: str = "bitrix24"

@app.get("/health")
def health():
    return {"service": "synergy-real-estate-lead-os", "ok": True, "version": "0.8.0"}

@app.post("/v1/documents")
def ingest(p: DocumentIn, operator: str = Depends(auth)):
    try: return store().ingest(p.model_dump())
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@app.get("/v1/documents/{document_id}")
def document_detail(document_id: int, operator: str = Depends(auth)):
    doc = store().get(document_id)
    if doc is None:
        raise HTTPException(404, "document not found")
    return {key: doc[key] for key in (
        "id", "source", "source_url", "domain", "text", "score", "bucket",
        "reviewer_label", "lawful_basis", "contact_opt_in"
    )}

@app.get("/v1/outbox/{item_id}")
def outbox_detail(item_id: int, operator: str = Depends(auth)):
    item = store().outbox(item_id)
    if item is None:
        raise HTTPException(404, "outbox item not found")
    return {key:item[key] for key in (
        "id","document_id","provider","state","approved_by","approved_at",
        "executed_at","response_json"
    )}

@app.get("/v1/search")
def search(q: str = "", domain: str | None = None, min_score: int = 0,
           limit: int = 30, operator: str = Depends(auth)):
    try: return {"items": store().search(q, domain, limit, min_score)}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@app.get("/v1/metrics")
def metrics(operator: str = Depends(auth)):
    return store().metrics()

@app.post("/v1/documents/{document_id}/review")
def review(document_id: int, p: ReviewIn, operator: str = Depends(auth)):
    try: return store().review(document_id, operator, p.label, p.note)
    except KeyError: raise HTTPException(404, "document not found")
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@app.post("/v1/documents/{document_id}/crm/prepare")
def prepare(document_id: int, p: CRMIn, operator: str = Depends(auth)):
    try: return store().prepare_crm(document_id,p.provider,p.title)
    except KeyError: raise HTTPException(404, "document not found")
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@app.post("/v1/outbox/{item_id}/approve")
def approve(item_id: int, operator: str = Depends(auth)):
    try: return store().approve_outbox(item_id,operator)
    except KeyError: raise HTTPException(404, "outbox item not found")
    except ValueError as exc: raise HTTPException(409, str(exc)) from exc
