"""System resource monitor — broadcasts metrics via LogBus every N seconds."""

from __future__ import annotations

import asyncio

import psutil
import structlog

logger = structlog.get_logger(__name__)

try:
    import pynvml  # type: ignore

    pynvml.nvmlInit()
    _NVML_AVAILABLE = True
except Exception:
    _NVML_AVAILABLE = False


def _collect_metrics(show_per_core: bool = False) -> dict:
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage(".")

    try:
        proc_rss = psutil.Process().memory_info().rss / 1024 / 1024
    except Exception:
        proc_rss = 0.0

    metrics: dict = {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram_percent": vm.percent,
        "ram_used_mb": round(vm.used / 1024 / 1024, 1),
        "ram_total_mb": round(vm.total / 1024 / 1024, 1),
        "swap_percent": swap.percent,
        "disk_percent": disk.percent,
        "process_rss_mb": round(proc_rss, 1),
        "gpu": None,
        "per_cpu": psutil.cpu_percent(percpu=True) if show_per_core else None,
    }

    if _NVML_AVAILABLE:
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            metrics["gpu"] = {
                "util_percent": util.gpu,
                "mem_used_mb": round(mem.used / 1024 / 1024, 1),
                "mem_total_mb": round(mem.total / 1024 / 1024, 1),
                "temp_c": temp,
            }
        except Exception:
            metrics["gpu"] = None

    return metrics


class SystemMonitor:
    def __init__(self) -> None:
        self._active_sessions: dict[str, dict] = {}

    def add_session(self, session_id: str, monitoring_cfg: dict) -> None:
        self._active_sessions[session_id] = monitoring_cfg

    def remove_session(self, session_id: str) -> None:
        self._active_sessions.pop(session_id, None)

    async def run(self) -> None:
        """Background loop — collect once per shortest interval among active sessions."""
        psutil.cpu_percent(interval=None)  # warm up
        while True:
            if not self._active_sessions:
                await asyncio.sleep(1)
                continue

            # lazy import to avoid circular; log_bus is singleton
            from app.services.log_bus import log_bus

            min_interval = min(cfg.get("interval_sec", 3) for cfg in self._active_sessions.values())
            metrics = _collect_metrics()

            for session_id, cfg in list(self._active_sessions.items()):
                await log_bus.emit(session_id, "system_metrics", metrics)
                await _check_thresholds(session_id, metrics, cfg)

            await asyncio.sleep(min_interval)


async def _check_thresholds(session_id: str, metrics: dict, cfg: dict) -> None:
    from app.services.log_bus import log_bus

    checks = [
        (
            "cpu_percent",
            "cpu_percent",
            cfg.get("warn_cpu_pct", 90),
            "Reduce parallel agents or switch to API mode",
        ),
        (
            "ram_percent",
            "ram_percent",
            cfg.get("warn_ram_pct", 85),
            "Enable context compression or switch to API mode",
        ),
    ]
    if metrics.get("gpu") and cfg.get("warn_gpu_mem_pct"):
        gpu_pct = (
            metrics["gpu"]["mem_used_mb"] / metrics["gpu"]["mem_total_mb"] * 100
            if metrics["gpu"]["mem_total_mb"] > 0
            else 0
        )
        checks.append(
            (
                "gpu_mem_percent",
                "gpu_mem_percent",
                cfg["warn_gpu_mem_pct"],
                "Reduce local model batch size",
            )
        )
        metrics["gpu_mem_percent"] = gpu_pct

    for key, label, threshold, hint in checks:
        if metrics.get(key, 0) >= threshold:
            await log_bus.emit(
                session_id,
                "system_warning",
                {"metric": label, "value": metrics[key], "threshold": threshold, "hint": hint},
            )


system_monitor = SystemMonitor()
