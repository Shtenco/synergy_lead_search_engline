"""Explicit CRM dispatch after human review and approval.

No automatic cold outreach, private message sending or background sends.
"""
from __future__ import annotations
import json
import os
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from .core import LeadStore

def dispatch_bitrix24(store: LeadStore, outbox_id: int) -> dict:
    item=store.outbox(outbox_id)
    if not item: raise KeyError(outbox_id)
    if item["state"]!="APPROVED": raise PermissionError("explicit operator approval required")
    if item["provider"]!="bitrix24": raise ValueError("unsupported CRM")
    webhook=os.getenv("LEAD_OS_BITRIX24_WEBHOOK","")
    u=urlparse(webhook)
    if u.scheme!="https" or not u.hostname or not u.path.endswith("/"):
        raise RuntimeError("configure an HTTPS Bitrix24 webhook base URL")
    endpoint=webhook.rstrip("/") + "/crm.lead.add.json"
    payload=json.loads(item["payload_json"])
    req=Request(endpoint, json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
    with urlopen(req,timeout=20) as r:
        response=json.loads(r.read().decode())
    if "error" in response or not response.get("result"):
        raise RuntimeError("CRM did not acknowledge lead creation")
    store.complete_outbox(outbox_id, {"crm_id":response["result"]})
    return {"state":"EXECUTED","crm_id":response["result"]}
