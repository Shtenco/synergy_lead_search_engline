"""Actual SMM_PROGRAM_LEADS V7 engine bridge.

Uses the original user's V7 Python source at runtime, not a reconstructed
heuristic. Keeps original algorithm and CatBoost model under a local path.
Never packages the operator's sessions, CRM data, or raw message exports.
"""
from __future__ import annotations

import importlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any
from .core import LeadStore, classify

REQUIRED = ("v7_mass_engine.py","vk_index_engine.py","vk_news_engine.py",
            "vk_audience_search.py","lead_profile_engine.py",
            "buyer_intelligence_v6.py","buyer_verification_v5.py")


def resolve_native_root(root: str | Path) -> Path:
    """Path must point to SMM_PROGRAM_LEADS with a complete core/ folder."""
    path = Path(root).expanduser().resolve()
    if path.name != "SMM_PROGRAM_LEADS" or not (path/"core"/"__init__.py").is_file():
        raise ValueError("root must be the local SMM_PROGRAM_LEADS directory")
    missing = [name for name in REQUIRED if not (path/"core"/name).is_file()]
    if missing: raise ValueError("Original V7 modules absent: " + ", ".join(missing))
    return path


def native_modules(root: str | Path) -> dict[str, Any]:
    """Only use a trusted operator-provided local archive; import executes Python."""
    path = resolve_native_root(root)
    existing = sys.modules.get("core")
    if existing and Path(getattr(existing, "__file__", "")).resolve().parent != path/"core":
        raise RuntimeError("Python module name 'core' already bound to a different package")
    if str(path) not in sys.path: sys.path.insert(0,str(path))
    names = ("core.v7_mass_engine","core.vk_index_engine","core.lead_profile_engine")
    return {name.split(".")[-1]:importlib.import_module(name) for name in names}


def vk_url(row: dict, kind: str = "post") -> str:
    url = row.get("url") or row.get("post_url")
    if isinstance(url,str) and url.startswith("https://vk.com/"): return url
    try:
        owner=int(row.get("owner_id",0))
        post=int(row.get("post_id") or row.get("id") or 0)
        comment=int(row.get("id",0))
        if not owner or not post:return ""
        base=f"https://vk.com/wall{owner}_{post}"
        return base+f"?reply={comment}" if kind in ("comment","board_comment") and comment else base
    except (TypeError,ValueError):return ""


def legacy_to_v8(row: dict, kind: str, key: str, verdict: dict | None = None) -> dict | None:
    url=vk_url(row,kind)
    text=str(row.get("text") or "").strip()
    if not url or not text or not key: return None
    # V7 VERIFIED_BUYER means model verification, not confirmed human intent.
    return {"source":"vk-v7-native","external_id":key,"source_url":url,
            "domain":"residency" if row.get("domain")=="residency" else "property",
            "doc_type":kind,"text":text[:20000],"source_at":row.get("date"),
            "lawful_basis":"none","contact_opt_in":False}


def import_v7_sqlite(v7_sqlite: str | Path, v8_store: LeadStore, limit: int = 0) -> dict[str,int]:
    """Read original V7Store items/raw_json, not just lossy JSONL export."""
    path=Path(v7_sqlite).resolve()
    if not path.is_file():raise FileNotFoundError(path)
    stats={"read":0,"created":0,"duplicate":0,"skipped":0,"errors":0}
    # Open read-only. Don't modify a collector's live database.
    uri=path.as_uri()+"?mode=ro"
    with sqlite3.connect(uri,uri=True,timeout=30) as db:
        cursor=db.execute("SELECT key,kind,raw_json,verdict_json FROM items ORDER BY key")
        for key,kind,raw,verdict in cursor:
            if limit and stats["read"]>=limit:break
            stats["read"]+=1
            try:
                item=json.loads(raw)
                parsed=json.loads(verdict) if verdict else None
                candidate=legacy_to_v8(item,str(kind),str(key),parsed)
                if candidate is None:stats["skipped"]+=1;continue
                r=v8_store.ingest(candidate)
                stats["created" if r["created"] else "duplicate"]+=1
            except (ValueError,TypeError,OverflowError,sqlite3.Error):
                stats["errors"]+=1
    return stats


def build_native_index(root: str | Path, v7_sqlite: str | Path,
                       index_db: str | Path, limit: int = 0) -> dict:
    """Feed unmodified V7 index implementation: BM25 + TF-IDF/LSA + CatBoost LTR."""
    mods=native_modules(root)
    index=mods["vk_index_engine"].VKIndexEngine(str(index_db))
    total=0
    try:
        with sqlite3.connect(Path(v7_sqlite).resolve().as_uri()+"?mode=ro",uri=True) as db:
            cur=db.execute("SELECT key,kind,raw_json,verdict_json,score,tier FROM items ORDER BY key")
            batch=[]
            for key,kind,raw,verdict,score,tier in cur:
                if limit and total>=limit:break
                try:
                    row=json.loads(raw)
                    if not row.get("text"): continue
                    row["content_type"]="comment" if kind!="post" else "post"
                    row["url"]=vk_url(row,kind)
                    row["lead_score"]=int(score or 0) if tier in ("POTENTIAL_REVIEW","VERIFIED_BUYER") else 0
                    row["seller_score"]=100 if tier=="ARCHIVE_OTHER" and row.get("author_id",0)<0 else 0
                    batch.append(row)
                    total+=1
                    if len(batch)>=250:index.upsert_rows(batch);batch=[]
                except (ValueError,TypeError,OverflowError):continue
            if batch:index.upsert_rows(batch)
        return {"indexed_v7_records":total,"index_documents":index.document_count(),
                "engine":"original VKIndexEngine","bm25":True,
                "tfidf_lsa_available":bool(getattr(mods["vk_index_engine"],"_HAS_SKLEARN",False)),
                "catboost_available":bool(getattr(mods["vk_index_engine"],"_HAS_CATBOOST",False))}
    finally:index.close()


def native_hybrid_search(root: str | Path, index_db: str | Path,
                         query: str, limit: int = 50) -> list[dict]:
    """Rank using the exact original VKIndexEngine.search implementation."""
    mods=native_modules(root)
    engine=mods["vk_index_engine"].VKIndexEngine(str(index_db))
    try:
        ranked=engine.search(query,limit=max(1,min(200,int(limit))))
        return [{**r,"human_verified":False,"requires_review":True,
                 "note":"V7 model score is NOT human proof"} for r in ranked]
    finally:engine.close()


def native_feedback(root: str | Path,index_db: str | Path,
                    doc_key: str, query: str, grade:int) -> None:
    """Record explicit human relevance grades; no automatic retraining."""
    if grade not in (0,1,2,3):raise ValueError("grade 0..3 required")
    mods=native_modules(root)
    engine=mods["vk_index_engine"].VKIndexEngine(str(index_db))
    try:engine.record_feedback(doc_key,query,grade)
    finally:engine.close()


def native_train(root: str | Path,index_db: str | Path, min_feedback:int = 20) -> dict:
    """Operator-triggered native CatBoostRanker training, with native gates."""
    mods=native_modules(root)
    engine=mods["vk_index_engine"].VKIndexEngine(str(index_db))
    try:return engine.train_ranker(min_feedback=max(20,int(min_feedback)))
    finally:engine.close()


def collect_with_native_v7(root: str | Path, vk_api: object, profile_path: str | Path,
                           v7_sqlite: str | Path, *, target_records: int = 3000,
                           max_api_calls: int = 100, interval: float = 1.2) -> dict:
    """Real original V7 collector with already-authorized VK client injected.

    Network I/O occurs ONLY when caller explicitly invokes this function.
    The original collector handles checkpoint/resume, comments, API errors.
    """
    mods=native_modules(root)
    mass=mods["v7_mass_engine"]
    profile=mods["lead_profile_engine"].load_profile(profile_path)
    cfg=mass.V7Config(target_records=target_records,max_api_calls=max_api_calls,
                      api_interval_seconds=interval).validate()
    v7store=mass.V7Store(v7_sqlite)
    try:
        return mass.VKV7Collector(vk_api,v7store,profile,cfg).collect()
    finally:v7store.close()
