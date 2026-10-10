"""Auditable, local-first V8 lead store and conservative rule baseline.

Not a trained model or permission to contact anyone.
All documents remain POTENTIAL until an operator verifies them.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

_NEGATION = re.compile(r"(?:не\s+(?:хочу|собираюсь|планирую|буду|нужно)|не\s+интересует|передумал[аи]?\s+).{0,25}(?:куп|покуп|приобрет|внж|переез)", re.I)
_SELLER = re.compile(r"\b(?:продаю|продам|предлагаем|наша\s+компания|застройщик|услуги\s+риелтора|в\s+продаже|скидка\s+от\s+застройщика|агентство\s+предлагает)\b", re.I)
_PROPERTY = re.compile(r"(?:квартир|апартамент|недвижим|дом\b|вилл|таунхаус|новостро|жиль[еёя]|property|flat|house|apartment)", re.I)
_RESIDENCY = re.compile(r"(?:внж|пмж|резиденц|вид\s+на\s+жительство|visa|residenc|relocat|виз[ауые]|переезд)", re.I)
_FIRST_PERSON = re.compile(r"(?:\bхочу\b|\bхотим\b|\bпланирую\b|\bпланируем\b|\bищу\b|\bищем\b|\bнужн[аоы]\b|\bподскажите\b|\bпосоветуйте\b|\bинтересует\b|\bмне\b|\bнам\b|\bi want\b|\blooking for\b)", re.I)
_INTENT = re.compile(r"(?:купить|покупк|приобрест|подобрать|оформить|получить|переехать|переезд|ищу|ищем|нужна|нужен|подскажите|посоветуйте|стоимост|сколько\s+стоит|как\s+купить|looking\s+to\s+buy)", re.I)
_BUDGET = re.compile(r"(?:\bбюджет\b|\bдо\s+\d[\d\s.,]*\s*(?:€|евро|usd|\$|руб|₽)|\b\d[\d\s.,]*\s*(?:€|евро|usd|\$|руб|₽))", re.I)
_DEADLINE = re.compile(r"(?:в\s+течени[еи]\s+\d+\s*(?:дн|недел|месяц)|в\s+этом\s+месяце|в\s+ближайш|срочно|до\s+конца\s+год[аы]|within\s+\d+)", re.I)
_COUNTRY = re.compile(r"(?:испан|барселон|валенси|аликант|мадрид|марбель|малаг|spain|españa|коста[-\s]бланк|коста[-\s]дель[-\s]соль)", re.I)
_URL = re.compile(r"^https?://", re.I)
_REVIEW_LABELS = {"VERIFIED_BUYER", "NOT_BUYER", "DISCUSSION_SOURCE", "POTENTIAL_REVIEW"}
_BASES = {"none", "consent", "inbound", "legitimate_interest"}


def classify(text: str, domain: str = "property") -> dict[str, Any]:
    """Conservative signal ranking; no classifier output is a verified human buyer."""
    t = str(text or "")[:20000]
    target = _RESIDENCY if domain == "residency" else _PROPERTY
    clues: list[str] = []
    seller = bool(_SELLER.search(t))
    negated = bool(_NEGATION.search(t))
    has_target = bool(target.search(t))
    first = bool(_FIRST_PERSON.search(t))
    intent = bool(_INTENT.search(t))
    geo = bool(_COUNTRY.search(t))
    budget = bool(_BUDGET.search(t))
    deadline = bool(_DEADLINE.search(t))
    score = 0
    if has_target: score += 18; clues.append("domain_object")
    if first and intent: score += 30; clues.append("first_person_intent")
    if has_target and first and intent: score += 12; clues.append("same_text_intent_and_object")
    if geo: score += 9; clues.append("spain_context")
    if budget and has_target: score += 15; clues.append("budget")
    if deadline and has_target: score += 12; clues.append("deadline")
    if seller: score -= 65; clues.append("seller_language")
    if negated: score -= 65; clues.append("explicit_negation")
    if len(t) > 3500: score -= 10; clues.append("long_document")
    score = max(0, min(100, score))
    if seller or negated: kind = "ARCHIVE_OTHER"
    elif has_target and first and intent: kind = "POTENTIAL_REVIEW"
    elif has_target and (intent or geo): kind = "DISCUSSION_SOURCE"
    else: kind = "ARCHIVE_OTHER"
    return {"score": score, "bucket": kind, "domain": domain, "evidence": clues,
            "verified": False, "requires_human_review": kind == "POTENTIAL_REVIEW"}


def _hash_doc(source: str, external_id: str) -> str:
    return hashlib.sha256((source.strip().lower() + "\n" + external_id.strip()).encode()).hexdigest()


class LeadStore:
    def __init__(self, path: str | Path = "runtime/lead_os.sqlite3"):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
              id INTEGER PRIMARY KEY AUTOINCREMENT, dedup_key TEXT NOT NULL UNIQUE,
              source TEXT NOT NULL, external_id TEXT NOT NULL, source_url TEXT NOT NULL,
              domain TEXT NOT NULL, doc_type TEXT NOT NULL, text TEXT NOT NULL,
              observed_at REAL NOT NULL, source_at REAL, score INTEGER NOT NULL,
              bucket TEXT NOT NULL, evidence_json TEXT NOT NULL,
              reviewer_label TEXT, reviewer_note TEXT, reviewed_at REAL,
              lawful_basis TEXT NOT NULL DEFAULT 'none',
              contact_opt_in INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS review_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER NOT NULL,
              actor TEXT NOT NULL, label TEXT NOT NULL, note TEXT NOT NULL,
              at REAL NOT NULL, FOREIGN KEY(document_id) REFERENCES documents(id)
            );
            CREATE TABLE IF NOT EXISTS outbox (
              id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER NOT NULL,
              provider TEXT NOT NULL, payload_json TEXT NOT NULL,
              state TEXT NOT NULL DEFAULT 'PENDING_APPROVAL',
              approved_by TEXT, approved_at REAL, executed_at REAL,
              response_json TEXT, created_at REAL NOT NULL,
              FOREIGN KEY(document_id) REFERENCES documents(id)
            );
            CREATE INDEX IF NOT EXISTS idx_documents_bucket ON documents(bucket,score);
            CREATE INDEX IF NOT EXISTS idx_documents_label ON documents(reviewer_label);
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
            USING fts5(text, content='documents', content_rowid='id', tokenize='unicode61');
            """)
    def _db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def ingest(self, record: dict[str, Any]) -> dict[str, Any]:
        source = str(record.get("source", "")).strip().lower()
        external_id = str(record.get("external_id", "")).strip()
        text = str(record.get("text", "")).strip()
        url = str(record.get("source_url", "")).strip()
        domain = str(record.get("domain", "property")).strip().lower()
        if not source or not external_id or not text:
            raise ValueError("source, external_id and text are required")
        if not url or not _URL.match(url):
            raise ValueError("public source_url is required")
        if domain not in {"property", "residency"}:
            raise ValueError("domain must be property or residency")
        if len(source) > 80 or len(external_id) > 256 or len(url) > 2000 or len(text) > 20000:
            raise ValueError("source metadata/text too long")
        basis = str(record.get("lawful_basis", "none"))
        if basis not in _BASES: raise ValueError("invalid lawful_basis")
        opt_in = bool(record.get("contact_opt_in", False))
        if opt_in and basis not in {"consent", "inbound"}:
            raise ValueError("contact_opt_in requires consent or inbound lawful basis")
        c = classify(text, domain)
        key = _hash_doc(source, external_id)
        now = time.time()
        source_at = record.get("source_at")
        if source_at is not None: source_at = float(source_at)
        with self._db() as db:
            old = db.execute("SELECT id FROM documents WHERE dedup_key=?", (key,)).fetchone()
            if old: return {"id": old["id"], "created": False, "dedup_key": key}
            cur = db.execute("""INSERT INTO documents
              (dedup_key,source,external_id,source_url,domain,doc_type,text,observed_at,
               source_at,score,bucket,evidence_json,lawful_basis,contact_opt_in)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (key,source,external_id,url,domain,str(record.get("doc_type","post"))[:30],text,
               now,source_at,c["score"],c["bucket"],json.dumps(c["evidence"],ensure_ascii=False),
               basis,int(opt_in)))
            db.execute("INSERT INTO documents_fts(rowid,text) VALUES (?,?)",(cur.lastrowid,text))
            return {"id":cur.lastrowid,"created":True,"dedup_key":key,"classification":c}

    def get(self, document_id: int) -> dict[str, Any] | None:
        with self._db() as db:
            r = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
            return dict(r) if r else None

    def search(self, query: str = "", domain: str | None = None, limit: int = 30,
               minimum_score: int = 0) -> list[dict[str, Any]]:
        limit = min(max(1,int(limit)),200)
        sql_filter = "WHERE d.score >= ?"
        args: list[Any] = [max(0,min(100,int(minimum_score)))]
        if domain in {"property","residency"}:
            sql_filter += " AND d.domain=?"; args.append(domain)
        tokens = re.findall(r"[\w-]{2,}", query.lower())[:12]
        with self._db() as db:
            if tokens:
                expression = " OR ".join('"' + w.replace('"','') + '"' for w in tokens)
                sql = ("""SELECT d.id,d.source,d.external_id,d.source_url,d.domain,d.doc_type,
                  substr(d.text,1,1500) AS text,d.score,d.bucket,d.observed_at,
                  d.reviewer_label,d.lawful_basis,d.contact_opt_in,
                  bm25(documents_fts) AS lexical_rank
                  FROM documents_fts JOIN documents d ON d.id=documents_fts.rowid """ +
                  sql_filter + " AND documents_fts MATCH ? ORDER BY lexical_rank ASC,d.score DESC LIMIT ?")
                args.extend([expression,limit])
                rows=db.execute(sql,args).fetchall()
            else:
                sql = ("""SELECT d.id,d.source,d.external_id,d.source_url,d.domain,d.doc_type,
                  substr(d.text,1,1500) AS text,d.score,d.bucket,d.observed_at,
                  d.reviewer_label,d.lawful_basis,d.contact_opt_in
                  FROM documents d """ + sql_filter +
                  " ORDER BY CASE WHEN d.reviewer_label='VERIFIED_BUYER' THEN 1 ELSE 0 END DESC,"
                  " d.score DESC,d.observed_at DESC LIMIT ?")
                args.append(limit); rows=db.execute(sql,args).fetchall()
            return [dict(r) for r in rows]

    def review(self, document_id: int, actor: str, label: str, note: str = "") -> dict[str, Any]:
        if label not in _REVIEW_LABELS: raise ValueError("invalid review label")
        if not actor.strip() or len(actor)>128: raise ValueError("actor required")
        with self._db() as db:
            r=db.execute("SELECT id FROM documents WHERE id=?",(document_id,)).fetchone()
            if not r: raise KeyError(document_id)
            now=time.time()
            db.execute("""UPDATE documents SET reviewer_label=?,reviewer_note=?,reviewed_at=?
                          WHERE id=?""",(label,note[:4000],now,document_id))
            db.execute("""INSERT INTO review_events(document_id,actor,label,note,at)
                          VALUES(?,?,?,?,?)""",(document_id,actor,label,note[:4000],now))
        return {"id":document_id,"reviewer_label":label}

    def prepare_crm(self, document_id:int, provider:str, title:str) -> dict[str,Any]:
        if provider != "bitrix24": raise ValueError("only bitrix24 adapter implemented")
        d=self.get(document_id)
        if not d: raise KeyError(document_id)
        if d["reviewer_label"]!="VERIFIED_BUYER":
            raise ValueError("human VERIFIED_BUYER review required")
        if d["lawful_basis"]=="none":
            raise ValueError("a documented lawful_basis is required")
        payload={"fields":{"TITLE":title[:200] or "Real Estate Lead",
                "COMMENTS":"Source: "+d["source_url"]+"\nDomain: "+d["domain"]+
                           "\nHuman verified document ID: "+str(document_id)}}
        with self._db() as db:
            c=db.execute("INSERT INTO outbox(document_id,provider,payload_json,created_at) VALUES (?,?,?,?)",
                          (document_id,provider,json.dumps(payload),time.time()))
            return {"id":c.lastrowid,"state":"PENDING_APPROVAL","provider":provider,"payload":payload}

    def outbox(self, outbox_id:int)->dict[str,Any]|None:
        with self._db() as db:
            r=db.execute("SELECT * FROM outbox WHERE id=?",(outbox_id,)).fetchone()
            return dict(r) if r else None

    def approve_outbox(self,outbox_id:int,actor:str)->dict[str,Any]:
        if not actor.strip(): raise ValueError("actor required")
        with self._db() as db:
            r=db.execute("SELECT state FROM outbox WHERE id=?",(outbox_id,)).fetchone()
            if not r: raise KeyError(outbox_id)
            if r["state"]!="PENDING_APPROVAL": raise ValueError("not pending")
            db.execute("UPDATE outbox SET state='APPROVED',approved_by=?,approved_at=? WHERE id=?",
                       (actor[:128],time.time(),outbox_id))
        return {"id":outbox_id,"state":"APPROVED"}

    def complete_outbox(self,outbox_id:int,response:dict[str,Any])->None:
        with self._db() as db:
            db.execute("UPDATE outbox SET state='EXECUTED',executed_at=?,response_json=? WHERE id=? AND state='APPROVED'",
                       (time.time(),json.dumps(response)[:4000],outbox_id))

    def metrics(self)->dict[str,Any]:
        with self._db() as db:
            totals={r["bucket"]:r["n"] for r in db.execute(
                "SELECT bucket,COUNT(*) AS n FROM documents GROUP BY bucket")}
            reviewed={r["reviewer_label"]:r["n"] for r in db.execute(
                "SELECT reviewer_label,COUNT(*) AS n FROM documents WHERE reviewer_label IS NOT NULL GROUP BY reviewer_label")}
            return {"documents":sum(totals.values()),"buckets":totals,
                    "human_reviews":reviewed,
                    "crm_pending":db.execute("SELECT COUNT(*) FROM outbox WHERE state='PENDING_APPROVAL'").fetchone()[0]}
