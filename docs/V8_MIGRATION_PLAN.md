# V8 migration matrix — 2026-10-10

## SOURCE OF TRUTH
User-provided SMM_PROGRAM_LEADS(1).zip inspected locally (323 ZIP entries; >100 MB uncompressed including private message exports and SQLite files). Never upload this archive directly: it includes local databases, message extracts, caches and potential credentials.

## Current implemented baseline
- \`lead_os/core.py\`: SQLite WAL, FTS5, dedup, evidence-style conservative scoring, human review, CRM outbox.
- \`lead_os/import_v7.py\`: import existing authorized V7 JSONL exports; no VK API call or model training.
- \`lead_os/api.py\`: fail-closed bearer-protected API.
- \`lead_os/crm.py\`: opt-in Bitrix24 CRM call after separate approval; not API-routed for unattended execution.
- \`tests/test_lead_os.py\`: baseline behavioral/security regression tests.

## Exact native modules requiring separate migration
| Existing archive source | Needed behavior | Migration gate |
|---|---|---|
| core/v7_mass_engine.py | source scheduler, group discovery, parent comment queues, checkpoint/resume | fake API tests, rate limiting, manual permissions review |
| core/vk_news_engine.py | VK query windows, result extraction | live-authorized API read only, no private scraping |
| core/vk_index_engine.py | FTS5/BM25, TF-IDF+LSA, CatBoostRanker | offline retrieval parity, >=20 feedback labels and independent evaluation |
| core/buyer_verification_v5.py | seller role detection, hard negative examples | labelled golden set |
| core/buyer_intelligence_v6.py | object/role/location/budget/deadline reasoning | no automatic verified buyer status |
| core/lead_profile_engine.py | JSON lead profile compatibility | profile_version: 1 validation |
| core/lead_radar.py | HOT/WARM topic and urgency heuristic | guard against false hot candidates |
| core/platform_safety.py | platform limits/consent and stop behavior | fail closed on restrictions |
| core/vk_audience_search.py | group discovery with authorized APIs | audit scope and legal basis |
| core/geo_filter.py | geo detection | country and property context must refer to buyer need |

### Important
V8 does NOT claim that the 10 native modules above are copied, wired or tested. The current FTS5 search is a limited new baseline, not the existing V2 hybrid retriever. Do not mark native engine migration completed until tests demonstrate equivalence and independent new-data validation.

## Next production gates
1. Run CI and fix observed failures.
2. Port V7 native code into \`lead_os/legacy_v7\` after reviewing files for personal data/secrets; inspect and pin dependencies.
3. Add explicit CLI connectors from V7 collector to V8 store, preserving provenance.
4. Run deterministic offline parity on synthetic fixtures, score retrieval and buyer verification by exact source IDs.
5. Add permissions/RBAC/authenticated approval identity, retention/deletion, CRM idempotency and safe retries.
6. Run authorized VK live smoke with modest requests; report API capability limits rather than circumventing them.
7. Measure Precision@20, discovery recall, buyer-verified yield, lead-to-consult conversion.
8. No mass unsolicited messages or circumventing restrictions; source discovery only.

**Repo state:** foundational integration committed, not externally deployed, not independently validated in production.
