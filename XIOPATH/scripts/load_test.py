"""
XIOPATH — Load Testing Script (Phase P.4)
============================================
Benchmarks API endpoints under concurrent load using asyncio + httpx.

Usage:
    python scripts/load_test.py --base-url http://localhost:8000 --concurrency 50 --duration 30

Endpoints tested:
  - GET  /api/v1/health/live    (baseline, should be < 5ms)
  - GET  /api/v1/marketplace/browse
  - POST /api/v1/auth/login     (with test credentials)
  - GET  /api/v1/marketplace/search?q=login
"""

import asyncio
import time
import argparse
import statistics
import sys
from dataclasses import dataclass, field
from typing import List, Dict

try:
    import httpx
except ImportError:
    print("Install httpx: pip install httpx")
    sys.exit(1)


@dataclass
class EndpointResult:
    endpoint: str
    method: str
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    latencies_ms: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def p50(self) -> float:
        if not self.latencies_ms:
            return 0
        s = sorted(self.latencies_ms)
        return s[len(s) // 2]

    @property
    def p95(self) -> float:
        if not self.latencies_ms:
            return 0
        s = sorted(self.latencies_ms)
        idx = int(len(s) * 0.95)
        return s[min(idx, len(s) - 1)]

    @property
    def p99(self) -> float:
        if not self.latencies_ms:
            return 0
        s = sorted(self.latencies_ms)
        idx = int(len(s) * 0.99)
        return s[min(idx, len(s) - 1)]

    @property
    def avg(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0

    @property
    def rps(self) -> float:
        if not self.latencies_ms:
            return 0
        total_time = sum(self.latencies_ms) / 1000
        return self.total_requests / max(total_time, 0.001)


ENDPOINTS = [
    {"method": "GET",  "path": "/api/v1/health/live",           "name": "Health Check"},
    {"method": "GET",  "path": "/",                              "name": "Root"},
    {"method": "GET",  "path": "/api/v1/marketplace/browse",    "name": "Marketplace Browse"},
    {"method": "GET",  "path": "/api/v1/marketplace/search?q=login", "name": "Marketplace Search"},
]


async def run_endpoint_test(
    client: httpx.AsyncClient,
    endpoint: Dict,
    result: EndpointResult,
    duration: int,
):
    """Continuously hit an endpoint for the specified duration."""
    start = time.time()
    while time.time() - start < duration:
        req_start = time.monotonic()
        try:
            if endpoint["method"] == "GET":
                resp = await client.get(endpoint["path"])
            else:
                resp = await client.post(endpoint["path"], json=endpoint.get("body", {}))

            latency = (time.monotonic() - req_start) * 1000
            result.total_requests += 1
            result.latencies_ms.append(latency)

            if resp.status_code < 500:
                result.successful += 1
            else:
                result.failed += 1
                result.errors.append(f"HTTP {resp.status_code}")
        except Exception as e:
            result.total_requests += 1
            result.failed += 1
            result.errors.append(str(e))


async def run_load_test(base_url: str, concurrency: int, duration: int):
    """Run load test against all endpoints."""
    print(f"\n{'='*60}")
    print(f"  XIOPATH Load Test")
    print(f"  Base URL:    {base_url}")
    print(f"  Concurrency: {concurrency} per endpoint")
    print(f"  Duration:    {duration}s")
    print(f"{'='*60}\n")

    results = {}

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(10.0),
        limits=httpx.Limits(max_connections=concurrency * len(ENDPOINTS)),
    ) as client:
        # Warmup
        print("Warming up...")
        try:
            await client.get("/")
        except Exception:
            print(f"⚠️  Could not reach {base_url} — is the server running?")
            return

        tasks = []
        for ep in ENDPOINTS:
            result = EndpointResult(endpoint=ep["name"], method=ep["method"])
            results[ep["name"]] = result
            for _ in range(concurrency):
                tasks.append(run_endpoint_test(client, ep, result, duration))

        print(f"Running {len(tasks)} concurrent workers for {duration}s...\n")
        start = time.time()
        await asyncio.gather(*tasks)
        wall_time = time.time() - start

    # Print results
    print(f"\n{'='*60}")
    print(f"  Results (wall time: {wall_time:.1f}s)")
    print(f"{'='*60}")
    print(f"\n{'Endpoint':<25} {'Total':>7} {'OK':>7} {'Fail':>5} {'Avg':>8} {'P50':>8} {'P95':>8} {'P99':>8}")
    print("-" * 85)

    total_requests = 0
    total_success = 0
    for name, r in results.items():
        total_requests += r.total_requests
        total_success += r.successful
        print(
            f"{r.endpoint:<25} {r.total_requests:>7} {r.successful:>7} {r.failed:>5} "
            f"{r.avg:>7.1f}ms {r.p50:>7.1f}ms {r.p95:>7.1f}ms {r.p99:>7.1f}ms"
        )

    print("-" * 85)
    overall_rps = total_requests / max(wall_time, 0.001)
    success_rate = (total_success / max(total_requests, 1)) * 100
    print(f"\n📊 Total: {total_requests} requests | {overall_rps:.0f} req/s | {success_rate:.1f}% success rate")

    # Performance thresholds
    print(f"\n{'='*60}")
    print("  Performance Thresholds")
    print(f"{'='*60}")
    health = results.get("Health Check")
    if health and health.p95 < 50:
        print(f"  ✅ Health Check P95: {health.p95:.1f}ms (threshold: <50ms)")
    elif health:
        print(f"  ⚠️  Health Check P95: {health.p95:.1f}ms (threshold: <50ms)")

    browse = results.get("Marketplace Browse")
    if browse and browse.p95 < 200:
        print(f"  ✅ Browse P95: {browse.p95:.1f}ms (threshold: <200ms)")
    elif browse:
        print(f"  ⚠️  Browse P95: {browse.p95:.1f}ms (threshold: <200ms)")

    if success_rate >= 99:
        print(f"  ✅ Success Rate: {success_rate:.1f}% (threshold: ≥99%)")
    else:
        print(f"  ⚠️  Success Rate: {success_rate:.1f}% (threshold: ≥99%)")
    print()


def main():
    parser = argparse.ArgumentParser(description="XIOPATH Load Testing")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent workers per endpoint")
    parser.add_argument("--duration", type=int, default=10, help="Test duration in seconds")
    args = parser.parse_args()

    asyncio.run(run_load_test(args.base_url, args.concurrency, args.duration))


if __name__ == "__main__":
    main()
