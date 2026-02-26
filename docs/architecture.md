# cdrmind Architecture

## Overview

cdrmind is a SOC Copilot that orchestrates three backend services to analyze security logs and produce structured incident reports.

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  POST /incidents                                                │
│       │                                                        │
│       ▼                                                        │
│  cdrmind (8000)                                                │
│  ├── POST /tasks ──────────────────► taskonaut-soc (8002)      │
│  │                                   flow: soc_pipeline        │
│  │                                   node1: summarize ─────►  │
│  │   ◄── POST /agents/summarize ─────────────────────────────  │
│  │        Claude → log_summary                                 │
│  │                                   node2: classify  ─────►  │
│  │   ◄── POST /agents/classify  ─────────────────────────────  │
│  │        guardflow(8003) + raggy(8001) + Claude               │
│  │                                   node3: report   ─────►   │
│  │   ◄── POST /agents/report    ─────────────────────────────  │
│  │        guardflow(8003) + Claude → IncidentReport            │
│  │                                   task COMPLETED            │
│  └── persist Incident to cdrmind DB                           │
│                                                                │
│  raggy (8001): doc store + semantic search (pgvector)         │
│  guardflow (8003): tool allowlist + RBAC                      │
└─────────────────────────────────────────────────────────────────┘
```

## Services

| Service | Port | Role |
|---------|------|------|
| cdrmind | 8000 | Orchestrator, API gateway, agent host |
| raggy | 8001 | RAG backend — pgvector document store |
| taskonaut-soc | 8002 | LangGraph task runner — soc_pipeline flow |
| guardflow | 8003 | Policy enforcement — RBAC + tool allowlist |
| PostgreSQL (shared) | 5432 | cdrmind + raggy database |
| PostgreSQL (taskonaut) | 5433 | taskonaut-soc database |
| Redis | 6379 | Rate limiting backend |
| Jaeger | 16686 | Distributed tracing UI |

## Data Flow

1. `POST /incidents {logs, actor_id, actor_role}` arrives at cdrmind
2. cdrmind creates a `soc_pipeline` task in taskonaut-soc
3. taskonaut-soc runs 3 nodes in sequence:
   - **summarize**: HTTP POST → cdrmind `/agents/summarize` → Claude extracts timeline + entities
   - **classify**: HTTP POST → cdrmind `/agents/classify` → guardflow check + raggy MITRE lookup + Claude
   - **report**: HTTP POST → cdrmind `/agents/report` → guardflow check + Claude → IncidentReport
4. cdrmind polls taskonaut-soc until COMPLETED
5. Final IncidentReport is validated with Pydantic strict mode and persisted
6. `GET /incidents/{id}` returns full report

## Key Design Decisions

- **Circular callback architecture**: taskonaut-soc calls back to cdrmind agents. Both run in same Docker network; startup ordering handled via health checks.
- **Stateless agents**: Each agent endpoint is stateless; all context flows through the task graph state.
- **Prompt injection defense**: All log data sanitized before insertion into LLM prompts; `<<<LOGS START/END>>>` delimiters used.
- **Schema validation**: LLM output validated with Pydantic `model_validate(strict=True)` — malformed responses rejected.
- **Rate limiting**: `slowapi` on `POST /incidents` — 10 req/min per actor via Redis.
