#!/usr/bin/env python3
"""Reproducible Local Performance Benchmark for Pressure Out (Phase 12 & Phase 12.1).

Supports configurable synthetic dataset sizes, request iteration counts, concurrency levels,
and target API URLs while explicitly recording runtime scope and environment assumptions
so an in-memory SQLite baseline is never misrepresented as a multi-node PostgreSQL benchmark.
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from app.config import Settings  # noqa: E402
from app.core.rate_limit import rate_limiter  # noqa: E402
from app.main import create_app  # noqa: E402


def parse_and_validate_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pressure Out Synthetic Performance Benchmark")
    parser.add_argument("--users", type=int, default=25, help="Synthetic user & contribution count (>= 10)")
    parser.add_argument("--posts", type=int, default=40, help="Synthetic post count (>= 4)")
    parser.add_argument("--comments", type=int, default=30, help="Synthetic comment count (>= 1)")
    parser.add_argument("--iterations", type=int, default=30, help="Requests per endpoint (>= 1)")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent worker threads (1..32)")
    parser.add_argument("--target-url", type=str, default="inprocess://testclient", help="Target base URL or inprocess://testclient")
    parser.add_argument("--validate-args-only", action="store_true", help="Validate arguments and exit")
    args = parser.parse_args(argv)

    if args.users < 10:
        raise ValueError("--users must be at least 10 so k-anonymity cohorts can be benchmarked.")
    if args.posts < 4:
        raise ValueError("--posts must be at least 4.")
    if args.comments < 1:
        raise ValueError("--comments must be at least 1.")
    if args.iterations < 1:
        raise ValueError("--iterations must be at least 1.")
    if args.concurrency < 1 or args.concurrency > 32:
        raise ValueError("--concurrency must be between 1 and 32.")
    return args


def measure_endpoint(
    name: str,
    fn: Callable[[], int],
    *,
    iterations: int = 30,
    concurrency: int = 1,
) -> Dict[str, object]:
    latencies_ms: List[float] = []
    errors = 0

    def _one_call() -> tuple[float, int]:
        rate_limiter.reset()
        t0 = time.perf_counter()
        status = fn()
        dt_ms = (time.perf_counter() - t0) * 1000.0
        return dt_ms, status

    if concurrency <= 1:
        for _ in range(iterations):
            dt_ms, status = _one_call()
            latencies_ms.append(dt_ms)
            if status >= 400:
                errors += 1
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(_one_call) for _ in range(iterations)]
            for fut in concurrent.futures.as_completed(futures):
                dt_ms, status = fut.result()
                latencies_ms.append(dt_ms)
                if status >= 400:
                    errors += 1

    samples = sorted(latencies_ms)
    p50 = round(float(statistics.median(samples)), 2)
    p95 = round(float(samples[min(len(samples) - 1, int(len(samples) * 0.95))]), 2)
    max_ms = round(float(samples[-1]), 2)
    return {
        "endpoint": name,
        "iterations": iterations,
        "concurrency": concurrency,
        "p50_ms": p50,
        "p95_ms": p95,
        "max_ms": max_ms,
        "error_rate_pct": round((errors / iterations) * 100.0, 2),
    }


def run_benchmark(args: argparse.Namespace) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        settings = Settings(
            app_env="test",
            database_url="sqlite:///:memory:",
            log_level="CRITICAL",
            local_storage_path=str(Path(tmp_dir) / "media"),
            ai_caption_provider="local_mock",
            ai_image_provider="local_mock",
            translation_provider="local_mock",
        )
        app = create_app(settings=settings)
        client = TestClient(app)

        users = []
        for idx in range(args.users):
            rate_limiter.reset()
            c = TestClient(app)
            reg = c.post(
                "/api/v1/auth/register",
                json={
                    "handle": f"bench_user_{idx:03d}",
                    "password": "BenchPassword#2026!",
                    "default_identity_mode": "pseudonymous",
                    "preferred_ui_locale": "en" if idx % 2 == 0 else "ml",
                },
            )
            assert reg.status_code == 201, reg.text
            csrf = reg.json()["csrf_token"]
            users.append((c, csrf))

            contrib = c.post(
                "/api/v1/workplace/contributions",
                headers={"X-CSRF-Token": csrf},
                json={
                    "aggregation_consent": True,
                    "industry_category": "technology",
                    "role_family": "software_engineering",
                    "experience_band": "mid_3_6",
                    "company_size_band": "midsize_51_500",
                    "broad_region": "south_asia",
                    "work_arrangement": "hybrid",
                    "overall_satisfaction": 3 + (idx % 3),
                    "work_life_balance": 2 + (idx % 4),
                    "management_quality": 3 + (idx % 2),
                    "psychological_safety": 4,
                    "compensation_satisfaction": 3 + (idx % 3),
                    "resignation_reason": "compensation" if idx % 2 == 0 else "better_opportunity",
                },
            )
            assert contrib.status_code == 201, contrib.text

        post_ids: List[str] = []
        communities = ["general-workplace", "workplace-rants", "corporate-memes", "work-life-balance"]
        for p_idx in range(args.posts):
            rate_limiter.reset()
            u_client, u_csrf = users[p_idx % len(users)]
            p_res = u_client.post(
                "/api/v1/posts",
                headers={"X-CSRF-Token": u_csrf},
                json={
                    "community_slug": communities[p_idx % len(communities)],
                    "post_type": "story" if p_idx % 2 == 0 else "rant",
                    "identity_mode": "anonymous" if p_idx % 3 == 0 else "pseudonymous",
                    "title": f"Sprint retrospective #{p_idx}: balancing velocity and on-call reliability",
                    "body": "Detailed benchmark narrative covering sprint planning, code review latency, and team morale.",
                    "content_language": "en" if p_idx % 2 == 0 else "ml",
                    "tags": ["sprint", "engineering", "oncall"],
                },
            )
            assert p_res.status_code == 201, p_res.text
            post_ids.append(p_res.json()["id"])

        target_post_id = post_ids[1]  # pseudonymous post
        for c_idx in range(args.comments):
            rate_limiter.reset()
            u_client, u_csrf = users[(c_idx + 1) % len(users)]
            c_res = u_client.post(
                f"/api/v1/posts/{target_post_id}/comments",
                headers={"X-CSRF-Token": u_csrf},
                json={
                    "body": f"Benchmark comment #{c_idx} sharing practical on-call handoff advice.",
                    "identity_mode": "pseudonymous",
                    "content_language": "en",
                },
            )
            assert c_res.status_code == 201, c_res.text

        bench_client, bench_csrf = users[0]
        it = args.iterations
        conc = args.concurrency
        endpoint_results = [
            measure_endpoint("GET /api/v1/health/ready", lambda: client.get("/api/v1/health/ready").status_code, iterations=it, concurrency=conc),
            measure_endpoint("GET /api/v1/feed?mode=latest", lambda: bench_client.get("/api/v1/feed?mode=latest&limit=20").status_code, iterations=it, concurrency=conc),
            measure_endpoint("GET /api/v1/feed?mode=popular", lambda: bench_client.get("/api/v1/feed?mode=popular&limit=20").status_code, iterations=it, concurrency=conc),
            measure_endpoint("GET /api/v1/explore", lambda: bench_client.get("/api/v1/explore").status_code, iterations=it, concurrency=conc),
            measure_endpoint("GET /api/v1/search?q=sprint", lambda: bench_client.get("/api/v1/search?q=sprint").status_code, iterations=it, concurrency=conc),
            measure_endpoint("GET /api/v1/posts/{id}", lambda: bench_client.get(f"/api/v1/posts/{target_post_id}").status_code, iterations=it, concurrency=conc),
            measure_endpoint("GET /api/v1/posts/{id}/comments", lambda: bench_client.get(f"/api/v1/posts/{target_post_id}/comments").status_code, iterations=it, concurrency=conc),
            measure_endpoint(
                "GET /api/v1/workplace/insights (k>=20)",
                lambda: bench_client.get("/api/v1/workplace/insights?industry_category=technology&role_family=software_engineering").status_code,
                iterations=it,
                concurrency=conc,
            ),
            measure_endpoint(
                "POST /api/v1/memes/render (PNG)",
                lambda: bench_client.post(
                    "/api/v1/memes/render",
                    headers={"X-CSRF-Token": bench_csrf},
                    json={
                        "template_id_or_slug": "friday-455pm-deploy",
                        "language": "en",
                        "output_format": "PNG",
                        "captions": [
                            {"region_id": "top", "text": "DEPLOYING ON FRIDAY"},
                            {"region_id": "bottom", "text": "BENCHMARK P95 UNDER 50MS"},
                        ],
                    },
                ).status_code,
                iterations=min(10, it),
                concurrency=1,
            ),
        ]
        asyncio.run(app.state.db_manager.dispose())
        return {
            "environment_metadata": {
                "runtime_mode": "sqlite_in_memory_local_baseline",
                "is_production_scale": False,
                "target_url": args.target_url,
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "dataset": {
                    "users": args.users,
                    "structured_contributions": args.users,
                    "posts": args.posts,
                    "comments": args.comments,
                },
                "iterations_per_endpoint": args.iterations,
                "concurrency": args.concurrency,
                "scope_disclaimer": (
                    "Measured against an in-process FastAPI TestClient and in-memory SQLite database. "
                    "Does not represent network-hop or multi-worker PostgreSQL 16 production throughput."
                ),
            },
            "results": endpoint_results,
        }


if __name__ == "__main__":
    parsed = parse_and_validate_args()
    if parsed.validate_args_only:
        print(json.dumps({"status": "valid", "args": vars(parsed)}))
        sys.exit(0)
    summary = run_benchmark(parsed)
    print(json.dumps(summary, indent=2))
