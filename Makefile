.PHONY: up down rebuild restart logs logs-all test incident status

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
