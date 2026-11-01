"""Process-aware operational metrics collector for Phase 12 & Phase 12.1 Observability.

Explicitly distinguishes process-local per-worker telemetry (`collection_scope = 'process_local'`)
from database-backed shared queue telemetry (`meme_jobs`) so a single Uvicorn worker's
in-memory counters are never misrepresented as cluster-wide totals when `WEB_CONCURRENCY > 1`.
Never stores user IDs, IP addresses, handles, or request payloads.
"""
from __future__ import annotations

import os
import statistics
import threading
from collections import Counter, deque
from typing import Any, Dict


class OperationalMetricsCollector:
    """Thread-safe/async-safe bounded per-process operational telemetry collector."""

    def __init__(self, max_samples: int = 2000) -> None:
        self._lock = threading.Lock()
        self._max_samples = max_samples
        self._latencies_ms: deque[float] = deque(maxlen=max_samples)
        self._counters: Counter[str] = Counter()

    def record_request(self, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self._counters["http_requests_total"] += 1
            status_class = f"http_status_{status_code // 100}xx"
            self._counters[status_class] += 1
            if status_code == 429:
                self._counters["rate_limit_429_total"] += 1
            if status_code == 413:
                self._counters["payload_too_large_413_total"] += 1
            self._latencies_ms.append(round(duration_ms, 2))

    def increment(self, metric_name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[metric_name] += amount

    def snapshot(self, *, configured_web_concurrency: int = 1) -> Dict[str, Any]:
        with self._lock:
            samples = sorted(self._latencies_ms)
            counters_copy = dict(self._counters)

        n = len(samples)
        if n == 0:
            p50 = 0.0
            p95 = 0.0
        else:
            p50 = round(float(statistics.median(samples)), 2)
            idx_95 = min(n - 1, int(n * 0.95))
            p95 = round(float(samples[idx_95]), 2)

        is_single_worker = int(configured_web_concurrency) == 1
        return {
            "collection_scope": "process_local",
            "is_cluster_wide": is_single_worker,
            "worker_pid": os.getpid(),
            "configured_web_concurrency": int(configured_web_concurrency),
            "aggregation_methodology": (
                f"Per-process sliding window of up to {self._max_samples} recent requests in worker PID {os.getpid()}. "
                "When configured_web_concurrency > 1, scrape each worker process or aggregate at the reverse proxy/load balancer."
            ),
            "http_requests_total": counters_copy.get("http_requests_total", 0),
            "http_status_2xx": counters_copy.get("http_status_2xx", 0),
            "http_status_4xx": counters_copy.get("http_status_4xx", 0),
            "http_status_5xx": counters_copy.get("http_status_5xx", 0),
            "rate_limit_429_total": counters_copy.get("rate_limit_429_total", 0),
            "payload_too_large_413_total": counters_copy.get("payload_too_large_413_total", 0),
            "latency_p50_ms": p50,
            "latency_p95_ms": p95,
            "sample_window_size": n,
        }

    def reset(self) -> None:
        with self._lock:
            self._latencies_ms.clear()
            self._counters.clear()


metrics_collector = OperationalMetricsCollector()
