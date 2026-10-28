#!/usr/bin/env python3
"""Smoke-test Baseten Muse Spark Open (hackathon model)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from muse_client import DEFAULT_MODEL, complete, score_purpose  # noqa: E402


def main() -> None:
    print("model:", DEFAULT_MODEL)
    text = complete([{"role": "user", "content": "Reply with exactly: OK"}], max_tokens=256, temperature=0)
    print("complete:", repr(text[:200]))
    risk = score_purpose("Scrape all prices for competitor resale")
    print("risk:", risk)
    if "OK" not in text.upper() and not text:
        raise SystemExit("empty model response")
    print("smoke ok")


if __name__ == "__main__":
    main()
