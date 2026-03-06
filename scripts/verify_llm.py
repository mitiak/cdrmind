#!/usr/bin/env python3
"""Verify OpenRouter API key and model availability."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import openai

api_key  = os.getenv("OPENROUTER_API_KEY", "")
base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
model    = sys.argv[1] if len(sys.argv) > 1 else os.getenv("LLM_MODEL", DEFAULT_MODEL)

if not api_key:
    print("ERROR: OPENROUTER_API_KEY not set (.env or environment)", file=sys.stderr)
    sys.exit(1)

print(f"key   : {api_key[:16]}...")
print(f"model : {model}")
print(f"url   : {base_url}")
print("sending request...")

client = openai.OpenAI(api_key=api_key, base_url=base_url)
resp = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Reply with exactly one word: OK"}],
    max_tokens=10,
)
reply = (resp.choices[0].message.content or "").strip()
print(f"reply : {reply}")
print("OK — OpenRouter is reachable and the model responded")
