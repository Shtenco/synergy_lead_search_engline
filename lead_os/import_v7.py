"""Offline importer for existing authorized V7 JSONL archives.

Does NOT download or scrape any content. Never upload personal exports to GitHub.
Use local encrypted storage and comply with platform/data-protection rules.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .core import LeadStore

def normalize_v7(row: dict) -> dict | None:
    text = str(row.get("text") or "").strip()
    url = str(row.get("url") or row.get("post_url") or "").strip()
    if not text or not url.startswith(("http://","https://")): return None
    document_id = str(row.get("source_message_id") or row.get("id") or row.get("comment_id") or "").strip()
    if not document_id: return None
    domain = "residency" if str(row.get("profile_id", "")).lower().startswith(("visa","residency")) else "property"
    return {"source":"vk-v7", "external_id": document_id, "source_url":url,
            "text":text,"domain":domain,"doc_type":str(row.get("content_type") or row.get("type") or "post")}

def import_file(path: str, db_path: str, max_records: int = 0) -> dict:
    store=LeadStore(db_path)
    counts={"read":0,"created":0,"duplicate":0,"skipped":0,"errors":0}
    with Path(path).open("r",encoding="utf8") as f:
        for line in f:
            if not line.strip():continue
            if max_records and counts["read"]>=max_records: break
            counts["read"]+=1
            try:
                record=normalize_v7(json.loads(line))
                if not record:counts["skipped"]+=1;continue
                result=store.ingest(record)
                counts["created" if result["created"] else "duplicate"]+=1
            except (ValueError, TypeError, json.JSONDecodeError, OverflowError):
                counts["errors"]+=1
    return counts

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--jsonl",required=True)
    parser.add_argument("--db",default="runtime/lead_os.sqlite3")
    parser.add_argument("--max-records",type=int,default=0)
    args=parser.parse_args()
    print(json.dumps(import_file(args.jsonl,args.db,args.max_records),ensure_ascii=False,indent=2))
if __name__=="__main__":main()
