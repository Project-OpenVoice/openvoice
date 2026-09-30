"""
scripts/seed_dataset.py

Validates and reports statistics on the intent benchmark dataset.
Use this to audit balance, spot duplicates, and verify coverage.

Usage:
    uv run python scripts/seed_dataset.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

DATASET_PATH = Path("app/decision/dataset/intents.json")
EXPECTED_CATEGORIES = {
    "system.volume",
    "system.brightness",
    "system.media.spotify",
    "system.media.youtube",
    "system.file.open",
    "system.file.search",
    "memory.note.create",
    "memory.note.search",
    "calendar.event.create",
    "calendar.event.search",
    "general.chat",
    "unknown",
}


def main() -> None:
    samples = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    sep = "-" * 60
    print(f"\n{sep}")
    print("  OpenVoice Dataset Audit")
    print(f"  File: {DATASET_PATH}")
    print(f"  Total samples: {len(samples)}")
    print(sep)

    counter: Counter[str] = Counter()
    texts: list[str] = []
    errors: list[str] = []

    for i, s in enumerate(samples):
        if "text" not in s or "intent" not in s:
            errors.append(f"  Sample {i} missing 'text' or 'intent' field: {s}")
            continue
        counter[s["intent"]] += 1
        texts.append(s["text"].lower().strip())

    # Check coverage
    missing = EXPECTED_CATEGORIES - set(counter.keys())
    unknown_cats = set(counter.keys()) - EXPECTED_CATEGORIES
    duplicates = [t for t, c in Counter(texts).items() if c > 1]

    print("\n  Category distribution:")
    for cat in sorted(EXPECTED_CATEGORIES):
        count = counter.get(cat, 0)
        flag = "  [LOW]" if count < 30 else ""
        print(f"    {cat:<35} {count:>4}{flag}")

    if missing:
        print(f"\n  MISSING categories: {missing}")
    else:
        print(f"\n  OK: All {len(EXPECTED_CATEGORIES)} categories covered")

    if unknown_cats:
        print(f"  ERROR: Unknown categories in dataset: {unknown_cats}")

    if duplicates:
        print(f"  ERROR: Duplicate texts ({len(duplicates)} found):")
        for d in duplicates[:5]:
            print(f"      - {d!r}")
    else:
        print("  OK: No duplicate texts")

    if errors:
        print(f"  ERROR: Schema errors ({len(errors)}):")
        for e in errors:
            print(e)
    else:
        print("  OK: All samples have valid schema")

    ok = not missing and not unknown_cats and not duplicates and not errors
    print(f"\n  Dataset: {'VALID' if ok else 'NEEDS ATTENTION'}")
    print(f"{sep}\n")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
