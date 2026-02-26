# Threat Model — OWASP LLM Top 10 Mitigations

## LLM01: Prompt Injection

**Risk**: Adversary-controlled log data contains instructions that manipulate the LLM.

**Mitigations**:
- `app/core/security.py::sanitize_logs()` strips 10+ injection patterns (regex-based)
- `<<<LOGS START>>>` / `<<<LOGS END>>>` delimiters isolate log content from instructions
- Delimiter injection prevented: pattern `<<<LOGS (START|END)>>>` is stripped from input
- Red team test suite: `tests/red_team/test_prompt_injection.py` (12 payloads)

## LLM02: Insecure Output Handling

**Risk**: LLM output used directly without validation, enabling downstream injection.

**Mitigations**:
- All agent outputs validated with `IncidentReport.model_validate(strict=True)`
- JSON parsing with `json.loads()` — no `eval()` usage
- LLM output that fails schema validation raises `ValueError` → 422 response

## LLM03: Training Data Poisoning

**Risk**: MITRE ATT&CK data in raggy contains malicious content.

**Mitigations**:
- MITRE data sourced from `data/mitre/attack_patterns.json` (curated, not user-supplied)
- Document ingestion via authenticated service (future: admin-only endpoint)

## LLM04: Model Denial of Service

**Risk**: Attackers send extremely large log payloads to exhaust LLM context or budget.

**Mitigations**:
- `POST /incidents` rate limited: 10 req/min per `actor_id` via Redis + slowapi
- Log payload truncated in classify agent (max 20 events)
- taskonaut-soc `max_input_bytes = 1MB`

## LLM05: Supply Chain Vulnerabilities

**Risk**: Compromised LLM library or model endpoint.

**Mitigations**:
- Uses official `anthropic` SDK with pinned version in `pyproject.toml`
- API key stored in environment variable, never in code

## LLM06: Sensitive Information Disclosure

**Risk**: LLM leaks sensitive customer data from logs in its responses.

**Mitigations**:
- Audit trail logs `input_hash` and `output_hash` (SHA-256), not raw content
- Reports stored in DB with RBAC-controlled access

## LLM07: Insecure Plugin Design

**Risk**: Tool calls bypass authorization.

**Mitigations**:
- Every agent endpoint calls guardflow `/authorize` before execution
- guardflow enforces two-gate policy: tool allowlist + Casbin RBAC
- SOC roles: `analyst`, `responder`, `admin` — each mapped to permitted tools

## LLM08: Excessive Agency

**Risk**: LLM takes autonomous destructive actions.

**Mitigations**:
- cdrmind is read-only with respect to external infrastructure
- All tool calls are bounded to: read logs, query RAG, generate report
- No write-back to AWS, no code execution

## LLM09: Overreliance

**Risk**: Analysts trust LLM output without verification.

**Mitigations**:
- `evidence_citations` link claims to raggy source chunks
- `reasoning_chain` exposes each agent step's logic for review
- Confidence/risk scores are explicit (not hidden)

## LLM10: Model Theft

**Risk**: Prompt/model extraction via repeated queries.

**Mitigations**:
- Rate limiting prevents bulk enumeration
- System prompts are hardcoded in agent modules (not DB-driven)
- OPENROUTER_API_KEY not logged or exposed in responses
