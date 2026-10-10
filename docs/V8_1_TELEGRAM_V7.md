# V8.1: original VK V7 engine + Telegram

The user's original V7 project remains LOCAL. This GitHub repository contains an adapter, not a replacement for its collector and hybrid engine. The operator must pass a trusted local SMM_PROGRAM_LEADS root with core/ to lead_os.native_v7.

Native integration functions:
- collect_with_native_v7(root, vk_api, profile_path, v7_sqlite, target_records=3000, max_api_calls=100, interval=1.2): original VKV7Collector with checkpointed messages and comments.
- import_v7_sqlite(v7_sqlite, LeadStore(db)): lossless native items access with adapted evidence-only documents. Existing local database is read-only.
- build_native_index(root, v7_sqlite, index_db): original VKIndexEngine, BM25+TF-IDF/LSA and optional CatBoostRanker.
- native_hybrid_search(root, index_db, query), native_feedback(root, index_db, key, query, grade), native_train(root, index_db): original search/learning-to-rank functions.

Telegram: lead_os.telegram.scan_allowed_channels explicitly reads public username allowlist and filters observed messages by keywords; it is NOT global Telegram search, is NOT a direct-message sender, never joins unknown groups, and does not bypass FloodWait or access errors. It requires Telethon and operator-authorized TELEGRAM_API_ID and TELEGRAM_API_HASH, kept outside GitHub.

Example:
```python
import asyncio
from lead_os.telegram import scan_allowed_channels
from lead_os.core import LeadStore
asyncio.run(scan_allowed_channels(
    ["SomePublicChannel"], LeadStore("runtime/leads.db"),
    keywords=["купить квартиру", "ВНЖ Испании"],
    max_messages_per_channel=100))
```

A public expression of interest is NOT a confirmed buyer, and does NOT grant permission to send promotional messages. Human review and a lawful outreach basis remain required.

Use `pip install -e ".[test,native,telegram]"` locally. Run `pytest -q`. Telegram credential setup and live VK API source permissions remain separate operational prerequisites.

No original raw user-message exports, authentication sessions, or credential material are copied here. Native engine equivalence and live delivery must be validated against the owner's existing data; adding an adapter is not proof of production readiness.
