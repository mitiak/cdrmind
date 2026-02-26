# cdrmind — SOC Copilot

Production-grade Security Operations Center (SOC) Copilot that orchestrates three microservices to analyze AWS/identity logs and produce structured incident reports with MITRE ATT&CK tactic mappings, risk scores, and evidence citations.

## Architecture

```
POST /incidents → cdrmind → taskonaut-soc (soc_pipeline)
                              ├── summarize → /agents/summarize (LLM via OpenRouter)
                              ├── classify  → /agents/classify  (guardflow + raggy + LLM)
                              └── report    → /agents/report    (guardflow + LLM)
```

See [docs/architecture.md](docs/architecture.md) for full diagram.

## Quick Start

```bash
# Copy environment config and add your OpenRouter key
cp .env.example .env
# Edit .env — set OPENROUTER_API_KEY and optionally LLM_MODEL

# Start full stack
make up

# Wait for services to be healthy, then ingest MITRE data
docker-compose exec cdrmind python scripts/ingest_mitre.py

# Run an investigation
make incident

# Stream logs while the pipeline runs
make logs

# View traces
open http://localhost:16686
```

## Switching Models

**Single config point: `LLM_MODEL` in `.env`**

1. Edit `.env` and change `LLM_MODEL` to any [free model on OpenRouter](https://openrouter.ai/models?q=:free):
   ```
   LLM_MODEL=google/gemma-3-12b-it:free
   ```
2. Apply without rebuilding:
   ```bash
   make restart
   ```
3. Fire a test request:
   ```bash
   make incident
   ```

Code changes (e.g. in `app/`) require a full rebuild instead:
```bash
make rebuild
```

## Development

```bash
# Install dependencies
uv pip install -e ".[dev]"

# Run all tests
uv run pytest tests/ -v

# Run only unit tests
uv run pytest tests/unit/ -v

# Run red team tests
uv run pytest tests/red_team/ -v -m red_team

# Run evaluation (CI mode — no API calls)
uv run pytest tests/integration/test_eval_harness.py -v -m eval

# Type checking
uv run mypy app/

# Linting
uv run ruff check app/ tests/ eval/
```

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/incidents` | Submit logs for investigation |
| `GET` | `/incidents/{id}` | Retrieve incident report |
| `POST` | `/agents/summarize` | Log summarization (called by taskonaut-soc) |
| `POST` | `/agents/classify` | Threat classification (called by taskonaut-soc) |
| `POST` | `/agents/report` | Report generation (called by taskonaut-soc) |
| `POST` | `/eval/run` | Trigger evaluation run |

## Services

| Service | Port |
|---------|------|
| cdrmind | 8000 |
| raggy | 8001 |
| taskonaut-soc | 8002 |
| guardflow | 8003 |
| Jaeger UI | 16686 |

## Security

See [docs/threat_model.md](docs/threat_model.md) for OWASP LLM Top 10 mitigations.

- Prompt injection defense with pattern-based sanitization
- Pydantic strict schema validation on all LLM outputs
- guardflow RBAC enforcement on every agent call
- Rate limiting: 10 req/min per actor_id via Redis
- Full audit trail (input/output hashes, session/actor IDs)
