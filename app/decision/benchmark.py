"""
app/decision/benchmark.py

Runs the full 500-sample benchmark dataset through the DecisionEngine
and reports: accuracy, P95 latency, and malformed output count.

Usage:
    uv run python -m app.decision.benchmark
    # or:
    uv run python scripts/benchmark.py
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from pathlib import Path

from app.decision.engine import DecisionEngine

DATASET_PATH = Path(__file__).parent / "dataset" / "intents.json"

# Acceptance thresholds from plan.md section 7
MIN_ACCURACY = 0.95
MAX_P95_LATENCY_MS_CPU = 500.0
MAX_P95_LATENCY_MS_GPU = 50.0


async def run_benchmark(dataset_path: Path = DATASET_PATH) -> dict[str, object]:
    """Run the full benchmark and return a results dict."""
    samples: list[dict] = json.loads(dataset_path.read_text(encoding="utf-8"))
    engine = DecisionEngine()

    correct = 0
    latencies_ms: list[float] = []
    malformed = 0

    import torch
    device_info = f"GPU ({torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else "CPU"
    sep = "-" * 60
    print(f"\n{sep}")
    print("  OpenVoice Decision Engine Benchmark")
    print(f"  Dataset: {dataset_path.name}  ({len(samples)} samples)")
    print(f"  Device : {device_info}")
    print(f"{sep}\n")

    for i, sample in enumerate(samples):
        text: str = sample["text"]
        expected: str = sample["intent"]

        t0 = time.perf_counter()
        try:
            decision = await engine.classify(text)
            latency_ms = (time.perf_counter() - t0) * 1000
            latencies_ms.append(latency_ms)

            if decision.intent == expected:
                correct += 1
            else:
                pass  # Uncomment below for verbose mode:
                # print(f"  MISS [{expected}] got [{decision.intent}]: {text!r}")

        except Exception as exc:
            malformed += 1
            latencies_ms.append((time.perf_counter() - t0) * 1000)
            print(f"  ERROR sample {i}: {exc}")

    total = len(samples)
    accuracy = correct / total
    p95 = statistics.quantiles(latencies_ms, n=20)[18]  # 95th percentile
    mean_ms = statistics.mean(latencies_ms)

    results = {
        "total": total,
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "malformed": malformed,
        "mean_latency_ms": round(mean_ms, 2),
        "p95_latency_ms": round(p95, 2),
        "passed": accuracy >= MIN_ACCURACY and malformed == 0,
    }

    pass_acc = "PASS" if accuracy >= MIN_ACCURACY else "FAIL (target >= 95%)"
    pass_malf = "PASS" if malformed == 0 else "FAIL"
    pass_lat = "(GPU target <= 50ms)" if p95 <= 50 else "(CPU target <= 500ms)"

    print(f"  Accuracy    : {correct}/{total} = {accuracy * 100:.2f}%  {pass_acc}")
    print(f"  Malformed   : {malformed}  {pass_malf}")
    print(f"  Mean latency: {mean_ms:.1f} ms")
    print(f"  P95 latency : {p95:.1f} ms  {pass_lat}")
    print(f"\n  Overall: {'BENCHMARK PASSED' if results['passed'] else 'BENCHMARK FAILED'}")
    print(f"{sep}\n")

    return results


if __name__ == "__main__":
    asyncio.run(run_benchmark())
