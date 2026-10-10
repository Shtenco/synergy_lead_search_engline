# SYNERGY REAL ESTATE LEAD OS — V8

**State: technical foundation / offline candidate — NOT a deployed lead discovery service.**

This repository is the canonical home of the future real estate and Spain residency lead-search system. It links the user's already-built \`SMM_PROGRAM_LEADS\` V7 collector, VK News/VK Index V2 hybrid search, Buyer Verification V5/V6 and AI Lead Radar with future AI Sales, human CRM verification and privacy safeguards.

## What is working in this baseline
- SQLite WAL document store and document-ID deduplication
- Local FTS5 keyword search (no external crawling on startup)
- Conservative property/residency intent **candidate** scoring
- Human-review audit events; no automatic "verified buyers"
- CRM outbox creation after human verification + documented lawful basis
- Explicit approval required before CRM dispatch
- Safe offline JSONL import of existing V7 authorized exports
- Token-protected FastAPI endpoints that fail closed when misconfigured
- Unit tests, default secrets/data exclusions

## What remains to integrate
The attached desktop SMM project is **not pushed wholesale**, because its 25MB archive expands to >100MB, includes raw personal-content exports, local SQLite databases, caches and authentication-related files. The actual reusable engines are preserved locally and can be wired through a narrowly scoped local adapter. They are not represented as migrated or production tested.

### Source lineage
- Local archive: \`SMM_PROGRAM_LEADS(1).zip\` (user-supplied; NOT included)
- \`core/v7_mass_engine.py\`: VK collector, checkpoint/resume
- \`core/vk_news_engine.py\`: VK news search
- \`core/vk_index_engine.py\`: FTS5/BM25 + TF-IDF/LSA; optional CatBoost LTR
- \`core/buyer_verification_v5.py\` and \`core/buyer_intelligence_v6.py\`: evidence gates
- \`core/lead_profile_engine.py\`: profile interpretation
- \`core/lead_radar.py\`: heuristic hot/warm cues
- \`Shtenco/synergy_agi_autopilot\`, branch \`feat/capability-runtime-v1\`: sales/SMM/revenue agents, CRM integration, task approval

V8 baseline scoring is an interpretable fallback, **not an upgraded CatBoost model**. The original V7 index and calibrated learning-to-rank are not yet deployed inside this repository.

## Installation
\`\`\`sh
python -m pip install -e ".[test]"
python -m pytest -q
export LEAD_OS_API_TOKEN="replace-with-random-token-at-least-24-characters"
export LEAD_OS_DB="runtime/lead_os.sqlite3"
uvicorn lead_os.api:app --host 127.0.0.1 --port 8128
\`\`\`

For Windows PowerShell:
\`\`\`powershell
$env:LEAD_OS_API_TOKEN="replace-with-a-random-strong-secret-at-least-24-characters"
python -m uvicorn lead_os.api:app --host 127.0.0.1 --port 8128
\`\`\`

### Offline import of existing local V7 export
\`\`\`sh
python -m lead_os.import_v7 --jsonl "/path/to/SMM_PROGRAM_LEADS/reports/v7_mass/raw_source_records.jsonl"
\`\`\`
This command reads a **local** archive, uses only documented source URLs and does not contact VK. Verify that the records are lawfully retained and remove records that must not be processed.

### API routes
\`GET /health\`, \`POST /v1/documents\`, \`GET /v1/search\`, \`GET /v1/metrics\`, \`POST /v1/documents/{id}/review\`, \`POST /v1/documents/{id}/crm/prepare\`, \`POST /v1/outbox/{id}/approve\`.
All except health require \`Authorization: Bearer <LEAD_OS_API_TOKEN>\`.

## Non-negotiable trust boundaries
1. Source mention != purchase intent; intent score != confirmed buyer.
2. Human review != lawful permission to contact; use CRM compliance workflow.
3. No scraping private content, no mass direct messages, no anti-rate-limit bypass.
4. No API tokens, database files, or social-media raw exports in GitHub.
5. Production requires role-based auth, CSRF/SSRF review, retention/deletion, encrypted DB or managed DB, HTTPS termination, data protection assessment, integration tests and calibrated real-data benchmarks.
6. Separate operator approval required for each external write.
7. Current CRM adapter code is opt-in and **not exposed as an unattended sending endpoint**.

### Performance acceptance
Score Precision@20, recall on independently labelled examples, useful leads per 1000 source records and per API call, provenance coverage, percentage duplicate documents, and booked consultation conversion. No guaranteed 50k/100k volume or positive buyer yield is claimed.
