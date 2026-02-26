#!/usr/bin/env python3
"""Ingest MITRE ATT&CK patterns into raggy vector store."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

RAGGY_URL = "http://localhost:8001"
DATA_FILE = Path(__file__).parent.parent / "data" / "mitre" / "attack_patterns.json"


async def ingest_pattern(client: httpx.AsyncClient, pattern: dict) -> None:
    content = f"""# {pattern['id']}: {pattern['name']}

**Tactic:** {pattern.get('tactic', 'Unknown')}

**Description:** {pattern['description']}

**Subtechniques:** {', '.join(pattern.get('subtechniques', [])) or 'None'}

**Mitigations:** {', '.join(pattern.get('mitigations', [])) or 'None'}
"""
    payload = {
        "source_type": "md",
        "title": f"MITRE ATT&CK {pattern['id']}: {pattern['name']}",
        "content": content,
        "metadata": {
            "mitre_id": pattern["id"],
            "tactic": pattern.get("tactic", ""),
            "source": "mitre_attack",
        },
    }
    response = await client.post(f"{RAGGY_URL}/documents", json=payload)
    if response.status_code in (200, 201):
        print(f"  ✓ Ingested {pattern['id']}: {pattern['name']}")
    else:
        print(f"  ✗ Failed {pattern['id']}: {response.status_code} {response.text[:100]}")


async def main() -> None:
    if not DATA_FILE.exists():
        print(f"Data file not found: {DATA_FILE}")
        sys.exit(1)

    patterns = json.loads(DATA_FILE.read_text())
    print(f"Ingesting {len(patterns)} MITRE ATT&CK patterns into raggy at {RAGGY_URL}...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Check raggy health
        try:
            r = await client.get(f"{RAGGY_URL}/health")
            r.raise_for_status()
        except Exception as exc:
            print(f"raggy not reachable: {exc}")
            sys.exit(1)

        for pattern in patterns:
            await ingest_pattern(client, pattern)

    print(f"\nDone. Ingested {len(patterns)} patterns.")


if __name__ == "__main__":
    asyncio.run(main())
