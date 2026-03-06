# cdrmind — SOC Copilot

Production-grade Security Operations Center (SOC) Copilot that orchestrates three
microservices to analyze AWS CloudTrail / identity logs and produce structured incident
reports with MITRE ATT&CK tactic mappings, risk scores, and evidence citations.

---

## Table of Contents

1. [Architecture](#architecture)
2. [From-scratch setup](#from-scratch-setup)
3. [Make commands](#make-commands)
4. [Main flows](#main-flows)
5. [API reference](#api-reference)
6. [Configuration](#configuration)
7. [Development](#development)
8. [Security](#security)

---

## Architecture

### Services

| Service | Port | Role |
|---------|------|------|
| **cdrmind** | 8000 | Orchestrator — FastAPI, exposes `/incidents` and `/agents/*` |
| **raggy** | 8001 | RAG backend — FastAPI + pgvector, stores MITRE ATT&CK chunks |
| **taskonaut-soc** | 8002 | LangGraph task runner — executes the `soc_pipeline` flow |
| **guardflow** | 8003 | Policy enforcement — RBAC + OPA-style JSON policy |
| **db** | 5432 | PostgreSQL (shared by cdrmind + raggy) |
| **taskonaut-db** | 5433 | PostgreSQL (dedicated to taskonaut-soc) |
| **redis** | 6379 | Rate-limit cache (slowapi) |
| **jaeger** | 16686 | Distributed tracing UI |

### Request flow

```
Client
  │
  ▼
POST /incidents          ← app/api/routes/incidents.py : create_incident() [L32]
  │
  ▼
TaskoNautClient          ← app/services/taskonaut_client.py : run_and_poll() [L65]
  │  creates + runs soc_pipeline task
  ▼
taskonaut-soc            ← LangGraph executor (sequential, 3 nodes)
  │
  ├─ Node 1: log_summarizer
  │    └─▶  POST /agents/summarize   ← app/api/routes/agents.py : summarize() [L26]
  │           └─▶ guardflow /authorize  (tool: log_read)
  │           └─▶ log_summarizer.summarize_logs()  ← app/agents/log_summarizer.py [L37]
  │                 └─▶ llm.complete_json()          ← app/services/llm.py [L78]
  │
  ├─ Node 2: threat_classifier
  │    └─▶  POST /agents/classify    ← app/api/routes/agents.py : classify() [L49]
  │           └─▶ guardflow /authorize  (tool: threat_lookup)
  │           └─▶ threat_classifier.classify_threats()  ← app/agents/threat_classifier.py [L42]
  │                 ├─▶ raggy /query   (top-5 MITRE chunks)
  │                 └─▶ llm.complete_json()
  │
  └─ Node 3: incident_reporter
       └─▶  POST /agents/report      ← app/api/routes/agents.py : report() [L73]
              └─▶ guardflow /authorize  (tool: report_generate)
              └─▶ incident_reporter.generate_report()  ← app/agents/incident_reporter.py [L68]
                    └─▶ llm.complete_json()
                    └─▶ IncidentReport validated + returned

Poll GET /tasks/{id} → COMPLETED
  │
  ▼
_extract_report()        ← app/api/routes/incidents.py [L195]
  └─▶ IncidentReport.model_validate()
  └─▶ Incident saved to DB
  └─▶ AuditEntry written
  └─▶ 201 IncidentReport returned to client
```

### Circular-dependency note

taskonaut-soc calls **back** to cdrmind's `/agents/*` endpoints during pipeline
execution. This works in Docker because both containers are on the same bridge network.
In local development you must run cdrmind before taskonaut-soc can complete any step.

### Alternative: quick path (single LLM call)

```
POST /incidents/quick    ← app/api/routes/incidents.py : create_incident_quick() [L128]
  └─▶ quick_analyst.run_quick_analysis()  ← app/agents/quick_analyst.py [L37]
        └─▶ llm.complete_json()  (one combined prompt, no guardflow, no raggy)
        └─▶ IncidentReport returned directly
```

---

## From-scratch setup

### Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- One of:
  - **Ollama** (local, free) — `brew install ollama` on macOS
  - **OpenRouter account** — get a key at <https://openrouter.ai>

---

### Option A — Local LLM with Ollama (default)

```bash
# 1. Pull the default model (run once; ~4 GB)
make ollama-pull           # equivalent: ollama pull qwen2.5:7b

# 2. Copy the environment file and keep defaults (Ollama is the default)
cp .env.example .env
#    LLM_API_KEY=ollama
#    LLM_BASE_URL=http://host.docker.internal:11434/v1
#    LLM_MODEL=qwen2.5:7b

# 3. Start the full stack
make up
#    This starts: db, taskonaut-db, redis, raggy, taskonaut-soc, guardflow, cdrmind, jaeger

# 4. Wait ~30 seconds for services to become healthy, then ingest MITRE ATT&CK data
docker-compose exec cdrmind python scripts/ingest_mitre.py
#    Ingests 30 MITRE ATT&CK techniques into raggy (pgvector)

# 5. Fire a test incident (20 CloudTrail events)
make incident
```

> **Tip — Ollama is slow on CPU.** Each LLM call can take 1–3 minutes.
> The pipeline makes 3 sequential calls; total time is typically 3–10 minutes.
> Timeout defaults are set generously (`LLM_TIMEOUT_SECS=300`).

---

### Option B — OpenRouter (cloud, fast)

```bash
# 1. Copy and edit the environment file
cp .env.example .env
# Edit .env:
#   LLM_API_KEY=your-openrouter-key
#   LLM_BASE_URL=https://openrouter.ai/api/v1
#   LLM_MODEL=meta-llama/llama-3.3-70b-instruct:free

# 2. (Optional) verify your key and model work before starting Docker
make verify-llm
# or with a specific model:
make verify-llm MODEL=google/gemma-3-12b-it:free

# 3. Start the full stack
make up

# 4. Ingest MITRE data
docker-compose exec cdrmind python scripts/ingest_mitre.py

# 5. Fire a test incident
make incident
```

---

### Health check

```bash
make status          # all containers should show "healthy" or "running"
curl http://localhost:8000/health   # → {"status":"ok"}
curl http://localhost:8001/health   # raggy
curl http://localhost:8002/health   # taskonaut-soc
curl http://localhost:8003/health   # guardflow
```

---

### Switching models at runtime

No rebuild needed — only a container restart:

```bash
# Edit .env, then:
make restart
# Changes to app/ code still require:
make rebuild
```

---

## Make commands

| Command | Description |
|---------|-------------|
| `make up` | Start the full stack (first run or after `make down`) |
| `make down` | Stop and remove all containers |
| `make rebuild` | Rebuild cdrmind image + restart (required after code changes) |
| `make restart` | Restart cdrmind only — picks up `.env` changes without rebuilding |
| `make status` | Show status of all containers |
| `make logs` | Stream cdrmind logs (Ctrl-C to stop) |
| `make logs-all` | Stream all service logs |
| `make test` | Run full test suite (49 tests: unit + integration + red-team) |
| `make incident` | POST 20-event CloudTrail log batch → full 3-step pipeline |
| `make incident-quick` | POST 3-event batch → single-call quick analyst (fast) |
| `make verify-llm [MODEL=<slug>]` | Verify LLM key + model (reads `.env`, no Docker) |
| `make ollama-pull` | Pull `qwen2.5:7b` into local Ollama |

---

## Main flows

### 1. `POST /incidents` — full pipeline

**Entry point:** `create_incident()` — `app/api/routes/incidents.py:32`

```
create_incident()                         incidents.py:32
  ├─ Serialize events to JSON strings     incidents.py:37
  ├─ TaskoNautClient.run_and_poll()       taskonaut_client.py:65
  │    ├─ create_task()                   taskonaut_client.py:22
  │    │    └─ POST /tasks (taskonaut-soc)
  │    ├─ run_task()  [retry on 409]      taskonaut_client.py:45
  │    │    └─ POST /tasks/{id}/run  ← drives 7 advance_task() calls:
  │    │         PLANNED→RUNNING, run summarize, WO→RUNNING,
  │    │         run classify, WO→RUNNING, run reporter, WO→COMPLETED
  │    └─ poll get_task() until COMPLETED taskonaut_client.py:58
  ├─ _extract_report(output_payload)      incidents.py:195
  │    └─ output_payload["incident_reporter"]["result"]
  ├─ IncidentReport.model_validate()
  ├─ Incident saved to DB                 incidents.py:94
  ├─ write_audit()                        audit.py:12
  └─ return 201 IncidentReport
```

**Taskonaut pipeline step count:** The `soc_pipeline` needs **7** `advance_task()` calls
(1 status transition + 2 per tool node + 1 final COMPLETED transition). `max_steps=12`
gives safe headroom.

---

### 2. `/agents/summarize` — log summarizer node

**Entry point:** `summarize()` — `app/api/routes/agents.py:26`

```
summarize()                               agents.py:26
  ├─ GuardflowClient.authorize()          guardflow_client.py:16
  │    └─ POST /authorize {tool: log_read}  → 403 if actor_role lacks permission
  └─ log_summarizer.summarize_logs()      log_summarizer.py:37
       ├─ wrap_logs_for_prompt()          security.py:33
       │    └─ sanitize_log_entry() ×N   security.py:20  (9 injection patterns)
       └─ llm.complete_json()             llm.py:78
            └─ complete()                llm.py:30  (@retry 3×, exponential backoff)
                 └─ AsyncOpenAI.chat.completions.create()
```

**Output schema:** `{log_summary, timeline, entities, reasoning}`

---

### 3. `/agents/classify` — threat classifier node

**Entry point:** `classify()` — `app/api/routes/agents.py:49`

```
classify()                                agents.py:49
  ├─ GuardflowClient.authorize()          guardflow_client.py:16
  │    └─ POST /authorize {tool: threat_lookup}
  └─ threat_classifier.classify_threats() threat_classifier.py:42
       ├─ RaggyClient.query()             raggy_client.py:17
       │    └─ POST /query (raggy) → top-5 MITRE ATT&CK chunks
       ├─ wrap_logs_for_prompt()          security.py:33
       └─ llm.complete_json()             llm.py:78
```

**Output schema:** `{threat_indicators, mitre_tactics, risk_score, rag_context, reasoning}`

---

### 4. `/agents/report` — incident reporter node

**Entry point:** `report()` — `app/api/routes/agents.py:73`

```
report()                                  agents.py:73
  ├─ GuardflowClient.authorize()          guardflow_client.py:16
  │    └─ POST /authorize {tool: report_generate}
  └─ incident_reporter.generate_report()  incident_reporter.py:68
       ├─ _build_citations()              incident_reporter.py:50
       └─ llm.complete_json()             llm.py:78
            └─ Builds IncidentReport with null-safe field coalescing:
                 t.get("resource") or ""  (handles LLM returning null)
```

**Output schema:** Full `IncidentReport` — timeline, risk_score, mitre_tactics, summary,
recommended_actions, reasoning_chain, evidence_citations.

---

### 5. `POST /incidents/quick` — single-pass analyst

**Entry point:** `create_incident_quick()` — `app/api/routes/incidents.py:128`

```
create_incident_quick()                   incidents.py:128
  └─ quick_analyst.run_quick_analysis()   quick_analyst.py:37
       └─ llm.complete_json()             llm.py:78
            └─ One combined prompt → full IncidentReport in one shot
               (no guardflow, no raggy, no taskonaut)
```

Best for rapid triage; lower quality than the 3-step pipeline.

---

### 6. LLM service

**File:** `app/services/llm.py`

| Function | Line | Purpose |
|----------|------|---------|
| `get_client()` | 16 | Build `AsyncOpenAI` with `api_key`, `base_url`, `timeout` |
| `complete()` | 30 | Call chat completions; `@retry` 3× with exp. backoff; handle `RateLimitError` |
| `complete_json()` | 78 | Call `complete()`, strip markdown fences, `json.loads()` |

Model is read from `settings.llm_model` on every call — change `LLM_MODEL` in `.env`
and `make restart` to switch models without rebuilding.

---

### 7. guardflow RBAC

`POST /authorize` on guardflow checks two layers:

1. **JSON policy** (`policy.json`) — tool-level allow/deny rules
2. **Casbin RBAC** (`rbac_policy.csv`) — role-to-tool permissions

Default permissions:

| Role | log_read | threat_lookup | report_generate |
|------|----------|---------------|-----------------|
| analyst | ✓ | ✓ | ✗ |
| responder | ✓ | ✓ | ✓ |
| admin | ✓ | ✓ | ✓ |

A 403 from guardflow propagates as `HTTP 403` to the caller.

---

## API reference

### cdrmind (port 8000)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `POST` | `/incidents` | Submit log batch → full 3-step pipeline → `IncidentReport` |
| `GET` | `/incidents/{id}` | Retrieve stored incident report |
| `POST` | `/incidents/quick` | Submit log batch → single-pass analysis → `IncidentReport` |
| `POST` | `/agents/summarize` | Internal: log summarization (called by taskonaut-soc) |
| `POST` | `/agents/classify` | Internal: threat classification (called by taskonaut-soc) |
| `POST` | `/agents/report` | Internal: report generation (called by taskonaut-soc) |
| `POST` | `/eval/run` | Trigger evaluation run |

### Request body for `/incidents` and `/incidents/quick`

```json
{
  "session_id": "uuid",
  "source": "aws_cloudtrail",
  "actor_id": "analyst-001",
  "actor_role": "analyst",
  "events": [ { ...CloudTrail event... } ]
}
```

`source` must be one of: `aws_cloudtrail`, `identity`, `vpc_flow`.
`actor_role` must be one of: `analyst`, `responder`, `admin`.

### IncidentReport response

```json
{
  "id": "uuid",
  "session_id": "uuid",
  "created_at": "2026-02-25T02:22:00Z",
  "summary": "...",
  "risk_score": 9.5,
  "mitre_tactics": [{ "id": "T1078", "name": "Valid Accounts", "description": "..." }],
  "recommended_actions": ["Revoke credentials", "..."],
  "timeline": [{ "timestamp": "...", "event_type": "...", "actor": "...", "resource": "...", "description": "...", "raw": {} }],
  "evidence_citations": [{ "doc_id": "uuid", "chunk_id": "uuid", "title": "...", "score": 0.91, "url": null }],
  "reasoning_chain": [{ "step": "log_summarizer", "reasoning": "...", "output_summary": "..." }]
}
```

---

## Configuration

All settings live in `app/core/config.py` (`Settings` class, line 6) and are read from
environment variables or `.env`.

| Env var | Default | Description |
|---------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://cdrmind:cdrmind@localhost:5432/cdrmind` | cdrmind + raggy DB |
| `RAGGY_URL` | `http://raggy:8001` | raggy service URL |
| `TASKONAUT_URL` | `http://taskonaut-soc:8002` | taskonaut-soc URL |
| `GUARDFLOW_URL` | `http://guardflow:8003` | guardflow URL |
| `LLM_API_KEY` | `ollama` | API key (use `ollama` for local Ollama) |
| `LLM_BASE_URL` | `http://host.docker.internal:11434/v1` | LLM API base URL |
| `LLM_MODEL` | `qwen2.5:7b` | Model slug — change to switch models |
| `LLM_MAX_TOKENS` | `4096` | Max tokens per LLM call |
| `LLM_TIMEOUT_SECS` | `300` | Per-call LLM timeout (seconds) |
| `REDIS_URL` | `redis://redis:6379` | Redis URL for rate limiting |
| `RATE_LIMIT_PER_MINUTE` | `10` | Max requests per minute per actor |
| `TASK_POLL_INTERVAL_SECS` | `1.0` | Poll interval for taskonaut task status |
| `TASK_POLL_MAX_ATTEMPTS` | `120` | Max poll attempts before timeout |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## Development

```bash
# Install dependencies (Python 3.12+, uv required)
uv pip install -e ".[dev]"

# Run all tests (49: unit + integration + red-team)
uv run pytest tests/ -v

# Subsets
uv run pytest tests/unit/ -v
uv run pytest tests/integration/ -v
uv run pytest tests/red_team/ -v -m red_team

# Evaluation (CI mode — no API calls)
uv run pytest tests/integration/test_eval_harness.py -v -m eval

# Type checking
uv run mypy app/

# Linting
uv run ruff check app/ tests/ eval/
```

### Project structure

```
app/
  api/routes/         # HTTP route handlers
    incidents.py      # POST /incidents, POST /incidents/quick, GET /incidents/{id}
    agents.py         # POST /agents/summarize|classify|report
    health.py         # GET /health
    eval.py           # POST /eval/run
  agents/             # LLM agent logic
    log_summarizer.py
    threat_classifier.py
    incident_reporter.py
    quick_analyst.py
  services/           # External service clients
    llm.py            # OpenAI-compatible LLM (Ollama or OpenRouter)
    taskonaut_client.py
    raggy_client.py
    guardflow_client.py
    audit.py
  core/
    config.py         # Pydantic settings
    security.py       # Prompt injection defense + log sanitization
    logging.py        # structlog JSON setup
  schemas/            # Pydantic request/response models
  models/             # SQLAlchemy ORM (Incident, AuditEntry)
  db/session.py       # Async engine + session factory

data/
  mitre/attack_patterns.json   # 30 MITRE ATT&CK techniques
  logs/aws_cloudtrail.json     # Sample 20-event test batch

eval/
  golden_dataset.json          # 15 labeled evaluation samples
  scorer.py                    # CI scorer (no API) + LLM judge mode

scripts/
  ingest_mitre.py              # Ingest MITRE data into raggy
  verify_llm.py                # Verify LLM key + model without Docker

tests/
  unit/                        # Fast, no external deps (mock LLM)
  integration/                 # ASGI transport, mock DB
  red_team/                    # Prompt injection adversarial tests
```

---

## Security

- **Prompt injection defense** (`app/core/security.py:20`) — 9 regex patterns escape
  `ignore previous instructions`, `[INST]`, `<|im_start|>`, and similar before any log
  reaches the LLM prompt. Logs are wrapped with `<<<LOGS START/END>>>` delimiters.
- **Pydantic strict validation** — all LLM JSON output is validated against typed schemas;
  null fields are coalesced with `or` before Pydantic sees them.
- **guardflow RBAC** — every agent call is authorized against a Casbin RBAC policy;
  403 propagates to the caller.
- **Rate limiting** — 10 req/min per remote address via slowapi + Redis.
- **Audit trail** — every incident and agent call writes an `AuditEntry` with SHA-256
  hashes of input and output (`app/services/audit.py:12`).
