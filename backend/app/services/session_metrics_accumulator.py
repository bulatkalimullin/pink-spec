"""In-memory per-session infrastructure metrics (CPU/RAM/GPU peaks and averages)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class _SessionInfraStats:
    sample_count: int = 0
    cpu_sum: float = 0.0
    cpu_peak: float = 0.0
    ram_sum: float = 0.0
    ram_peak: float = 0.0
    gpu_mem_peak: float = 0.0
    process_rss_peak_mb: float = 0.0
    system_warnings_count: int = 0


class SessionMetricsAccumulator:
    """Tracks host resource samples per active session."""

    def __init__(self) -> None:
        self._sessions: dict[str, _SessionInfraStats] = {}

    def record(self, session_id: str, metrics: dict[str, Any]) -> None:
        stats = self._sessions.setdefault(session_id, _SessionInfraStats())
        cpu = float(metrics.get("cpu_percent", 0) or 0)
        ram = float(metrics.get("ram_percent", 0) or 0)
        rss = float(metrics.get("process_rss_mb", 0) or 0)

        stats.sample_count += 1
        stats.cpu_sum += cpu
        stats.cpu_peak = max(stats.cpu_peak, cpu)
        stats.ram_sum += ram
        stats.ram_peak = max(stats.ram_peak, ram)
        stats.process_rss_peak_mb = max(stats.process_rss_peak_mb, rss)

        gpu = metrics.get("gpu")
        if gpu and gpu.get("mem_total_mb", 0) > 0:
            gpu_pct = gpu["mem_used_mb"] / gpu["mem_total_mb"] * 100
            stats.gpu_mem_peak = max(stats.gpu_mem_peak, gpu_pct)

    def record_warning(self, session_id: str) -> None:
        stats = self._sessions.setdefault(session_id, _SessionInfraStats())
        stats.system_warnings_count += 1

    def snapshot(self, session_id: str) -> dict[str, float | int]:
        stats = self._sessions.get(session_id)
        if stats is None or stats.sample_count == 0:
            return {
                "cpu_avg": 0.0,
                "cpu_peak": 0.0,
                "ram_avg": 0.0,
                "ram_peak": 0.0,
                "gpu_mem_peak": 0.0,
                "process_rss_peak_mb": 0.0,
                "system_warnings_count": 0,
                "infra_samples_count": 0,
            }
        n = stats.sample_count
        return {
            "cpu_avg": round(stats.cpu_sum / n, 2),
            "cpu_peak": round(stats.cpu_peak, 2),
            "ram_avg": round(stats.ram_sum / n, 2),
            "ram_peak": round(stats.ram_peak, 2),
            "gpu_mem_peak": round(stats.gpu_mem_peak, 2),
            "process_rss_peak_mb": round(stats.process_rss_peak_mb, 2),
            "system_warnings_count": stats.system_warnings_count,
            "infra_samples_count": n,
        }

    def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


session_metrics_accumulator = SessionMetricsAccumulator()
