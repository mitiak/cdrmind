.PHONY: up down rebuild restart logs logs-all test incident incident-quick status verify-llm ollama-pull use-openrouter

# ── Configuration ──────────────────────────────────────────────────────────────
# To change the LLM model, edit LLM_MODEL in .env then run: make restart

# ── Stack lifecycle ────────────────────────────────────────────────────────────

## Start the full stack (first time or after down)
up:
	docker-compose up -d

## Stop and remove containers
down:
	docker-compose down

## Full rebuild of cdrmind image + restart (needed after code changes)
rebuild:
	docker-compose up -d --build cdrmind

## Restart cdrmind only — picks up .env changes (e.g. LLM_MODEL) without rebuilding
restart:
	docker-compose up -d --force-recreate cdrmind

## Show status of all containers
status:
	docker-compose ps

# ── Logs ───────────────────────────────────────────────────────────────────────

## Stream cdrmind logs (Ctrl-C to stop)
logs:
	docker-compose logs -f cdrmind

## Stream all service logs (Ctrl-C to stop)
logs-all:
	docker-compose logs -f

# ── Testing ────────────────────────────────────────────────────────────────────

## Run the full test suite (unit + integration + red-team)
test:
	uv run pytest tests/ -v

## Fire a test incident against the running stack
incident:
	curl -s -X POST http://localhost:8000/incidents \
	  -H "Content-Type: application/json" \
	  -d @data/logs/aws_cloudtrail.json | jq .

## Fire a minimal quick-test incident (1 LLM call, 3 events — fast iteration)
incident-quick:
	curl -s -X POST http://localhost:8000/incidents/quick \
	  -H "Content-Type: application/json" \
	  -d @data/logs/quick_test.json | jq .

## Verify OpenRouter API key and model (reads .env, no Docker needed)
## Usage: make verify-llm [MODEL=<slug>]
verify-llm:
	uv run python scripts/verify_llm.py $(MODEL)

# ── Ollama / LLM backend ───────────────────────────────────────────────────────

## Pull the default local model (requires Ollama installed: brew install ollama)
ollama-pull:
	ollama pull qwen2.5:7b

## Switch to OpenRouter (edits .env, then run: make restart)
## Usage: make use-openrouter MODEL=meta-llama/llama-3.3-70b-instruct:free KEY=sk-or-...
use-openrouter:
	@sed -i '' 's|^LLM_BASE_URL=.*|LLM_BASE_URL=https://openrouter.ai/api/v1|' .env
	@sed -i '' 's|^LLM_API_KEY=.*|LLM_API_KEY=$(KEY)|' .env
	@sed -i '' 's|^LLM_MODEL=.*|LLM_MODEL=$(MODEL)|' .env
	@echo "Switched to OpenRouter. Run: make restart"
