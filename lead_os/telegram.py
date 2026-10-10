"""Allowlisted Telegram chat/channel search using operator-authorized Telethon.

No global Telegram search; no joining/discovery/DMs. Telegram message text is
ingested as evidence for HUMAN review, never treated as contact permission.
"""
from __future__ import annotations
import asyncio
import os
import re
from typing import Any
from .core import LeadStore

PUBLIC_USERNAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def validate_channels(channels: list[str]) -> list[str]:
    if not channels or len(channels)>30: raise ValueError("provide 1..30 explicitly authorized channels")
    valid=[]
    for raw in channels:
        value=str(raw).strip().removeprefix("@")
        if not PUBLIC_USERNAME.fullmatch(value):raise ValueError("only public Telegram usernames allowed")
        if value.lower() not in [x.lower() for x in valid]:valid.append(value)
    return valid


def message_permalink(username: str, message_id: int) -> str:
    return f"https://t.me/{username}/{int(message_id)}"


def normalize_message(username: str, message: Any, keywords:list[str] | None=None,
                      domain:str="property") -> dict | None:
    text=str(getattr(message,"message","") or "")
    mid=int(getattr(message,"id",0) or 0)
    if not text.strip() or mid<=0:return None
    if keywords and not any(k.casefold() in text.casefold() for k in keywords):return None
    if domain not in {"property","residency"}:raise ValueError("invalid domain")
    return {"source":"telegram-public-allowlist","external_id":f"{username.lower()}:{mid}",
            "source_url":message_permalink(username,mid),"text":text[:20000],
            "domain":domain,"doc_type":"message","lawful_basis":"none",
            "contact_opt_in":False,
            "source_at":getattr(message,"date",None).timestamp()
                if getattr(message,"date",None) is not None else None}


async def scan_allowed_channels(
    channels: list[str], store: LeadStore, *,
    keywords:list[str] | None=None, domain:str="property",
    max_messages_per_channel:int=150, delay_seconds:float=1.0,
    client:Any=None
) -> dict:
    channels=validate_channels(channels)
    if max_messages_per_channel<1 or max_messages_per_channel>500:
        raise ValueError("max_messages_per_channel must be 1..500")
    if delay_seconds<1:raise ValueError("delay_seconds must be >=1")
    if keywords is not None and (len(keywords)>30 or any(not isinstance(k,str) or len(k)>100 for k in keywords)):
        raise ValueError("invalid keywords")
    owned=False
    if client is None:
        try:from telethon import TelegramClient
        except ImportError as e:raise RuntimeError("Install pip install telethon") from e
        api_id=int(os.environ["TELEGRAM_API_ID"])
        api_hash=os.environ["TELEGRAM_API_HASH"]
        session=os.environ.get("TELEGRAM_SESSION","runtime/lead_os_telegram")
        client=TelegramClient(session,api_id,api_hash)
        await client.start();owned=True
    stats={"sources":[],"created":0,"duplicates":0,"matched":0,"errors":[],
           "scope":"explicit-public-allowlist","sent_messages":0}
    try:
        for i,channel in enumerate(channels):
            fetched=0;matched=0
            try:
                entity=await client.get_entity(channel)
                # Read from explicitly supplied accessible public sources.
                async for msg in client.iter_messages(entity,limit=max_messages_per_channel):
                    fetched+=1
                    row=normalize_message(channel,msg,keywords,domain)
                    if row is None:continue
                    matched+=1
                    ingested=store.ingest(row)
                    stats["created" if ingested["created"] else "duplicates"]+=1
                stats["sources"].append({"channel":channel,"fetched":fetched,"matched":matched})
                stats["matched"]+=matched
            except Exception as exc:
                name=type(exc).__name__
                stats["errors"].append({"channel":channel,"type":name,"detail":str(exc)[:160]})
                if name in ("FloodWaitError","AuthKeyError","AuthKeyUnregisteredError","SessionRevokedError",
                            "UserDeactivatedError","ChatAdminRequiredError","ChannelPrivateError"):
                    break
            if i+1<len(channels):await asyncio.sleep(delay_seconds)
    finally:
        if owned:await client.disconnect()
    return stats
