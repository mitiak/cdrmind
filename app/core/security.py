from __future__ import annotations

import hashlib
import re

# Patterns that could be prompt injection attempts
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"new\s+instructions?:", re.IGNORECASE),
    re.compile(r"system\s*:", re.IGNORECASE),
    re.compile(r"<\s*/?system\s*>", re.IGNORECASE),
    re.compile(r"###\s*(instruction|prompt|system)", re.IGNORECASE),
    re.compile(r"\[INST\]|\[/INST\]"),
    re.compile(r"<\|im_start\|>|<\|im_end\|>"),
    re.compile(r"<<<LOGS\s*(START|END)>>>"),  # prevent delimiter injection
]


def sanitize_log_entry(entry: str) -> str:
    """Escape potential prompt injection patterns in a single log entry."""
    sanitized = entry
    for pattern in _INJECTION_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def sanitize_logs(logs: list[str]) -> list[str]:
    """Sanitize a list of log strings before injecting into prompts."""
    return [sanitize_log_entry(log) for log in logs]


def wrap_logs_for_prompt(logs: list[str]) -> str:
    """Wrap sanitized log lines with safe delimiters for prompt insertion."""
    sanitized = sanitize_logs(logs)
    body = "\n".join(sanitized)
    return f"<<<LOGS START>>>\n{body}\n<<<LOGS END>>>"


def hash_content(content: str) -> str:
    """Return SHA-256 hex digest of content for audit trail."""
    return hashlib.sha256(content.encode()).hexdigest()
