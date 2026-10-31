import math
import statistics


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return 0.0, 0.0
    p = hits / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, center - margin), min(1.0, center + margin)


def latency_summary(seconds: list[float]) -> dict[str, float]:
    ordered = sorted(seconds)
    return {
        "latencia_p50_s": round(statistics.median(ordered), 2),
        "latencia_p95_s": round(ordered[int(0.95 * (len(ordered) - 1))], 2),
    }
