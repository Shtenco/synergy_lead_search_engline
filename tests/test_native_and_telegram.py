from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from lead_os.telegram import validate_channels, normalize_message, scan_allowed_channels
from lead_os.native_v7 import legacy_to_v8, resolve_native_root
from lead_os.core import LeadStore

def test_channels():
    assert validate_channels(["@SpainHomes", "SpainHomes", "@SpainVisaInfo"]) == ["SpainHomes","SpainVisaInfo"]
    for value in ([], ["https://t.me/+private"], ["joinchat/private"], ["ab"]):
        with pytest.raises(ValueError): validate_channels(value)

def test_normalize():
    message=SimpleNamespace(id=13,message="Хочу купить квартиру в Испании",date=datetime(2026,10,10,tzinfo=timezone.utc))
    doc=normalize_message("SpainHomes",message,["квартиру"])
    assert doc["source_url"]=="https://t.me/SpainHomes/13"
    assert doc["contact_opt_in"] is False and doc["lawful_basis"]=="none"
    assert normalize_message("SpainHomes",message,["нигде"]) is None

@pytest.mark.asyncio
async def test_scan(tmp_path):
    class Client:
        async def get_entity(self,handle): return handle
        async def iter_messages(self,entity,limit):
            for i in (1,2):yield SimpleNamespace(id=i,message="Хочу купить квартиру в Испании",date=None)
    store=LeadStore(tmp_path/"store.db")
    first=await scan_allowed_channels(["SpainHomes"],store,keywords=["купить"],client=Client())
    assert first["created"]==2
    again=await scan_allowed_channels(["SpainHomes"],store,keywords=["купить"],client=Client())
    assert again["duplicates"]==2

def test_v7_not_human_verified():
    record=legacy_to_v8({"owner_id":-12,"post_id":48,"id":48,"text":"Хочу купить квартиру"},"post","vk:post:-12:48",{"v7_tier":"VERIFIED_BUYER"})
    assert record["lawful_basis"]=="none"
    assert record["source_url"]=="https://vk.com/wall-12_48"
    with pytest.raises(ValueError):resolve_native_root("/tmp/missing")
