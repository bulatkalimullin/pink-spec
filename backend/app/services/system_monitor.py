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
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            driver_version = None
            try:
                driver_version = pynvml.nvmlSystemGetDriverVersion()
                if isinstance(driver_version, bytes):
                    driver_version = driver_version.decode("utf-8", errors="replace")
            except Exception:
                pass
            metrics["gpu"] = {
                "name": name,
                "util_percent": util.gpu,
                "mem_used_mb": round(mem.used / 1024 / 1024, 1),
                "mem_total_mb": round(mem.total / 1024 / 1024, 1),
                "temp_c": temp,
                "driver_version": driver_version,
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

            from app.services.log_bus import log_bus

            enabled_sessions = {
                sid: cfg
                for sid, cfg in self._active_sessions.items()
                if cfg.get("enabled", True)
            }
            if not enabled_sessions:
                await asyncio.sleep(1)
                continue

            show_per_core = any(cfg.get("show_per_core") for cfg in enabled_sessions.values())
            min_interval = min(
                cfg.get("interval_sec", 3) for cfg in enabled_sessions.values()
            )
            metrics = _collect_metrics(show_per_core=show_per_core)

            for session_id, cfg in list(enabled_sessions.items()):
                from app.services.session_metrics_accumulator import session_metrics_accumulator

                session_metrics_accumulator.record(session_id, metrics)
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
            from app.services.session_metrics_accumulator import session_metrics_accumulator

            session_metrics_accumulator.record_warning(session_id)
            await log_bus.emit(
                session_id,
                "system_warning",
                {"metric": label, "value": metrics[key], "threshold": threshold, "hint": hint},
            )


system_monitor = SystemMonitor()
