"""
scripts/benchmark.py

CLI entry point for the Decision Engine benchmark.

Usage:
    uv run python scripts/benchmark.py
    uv run python scripts/benchmark.py --dataset app/decision/dataset/intents.json
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.decision.benchmark import run_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenVoice Decision Engine Benchmark")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("app/decision/dataset/intents.json"),
        help="Path to the benchmark dataset JSON file.",
    )
    args = parser.parse_args()

    results = asyncio.run(run_benchmark(args.dataset))
    sys.exit(0 if results["passed"] else 1)


if __name__ == "__main__":
    main()
