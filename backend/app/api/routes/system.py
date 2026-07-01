"""System health and metrics endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.services.system_monitor import _collect_metrics

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/config")
async def get_config():
    """Current env-based configuration (safe for UI)."""
    return get_settings().public_dict()


@router.get("/metrics")
async def get_metrics():
    """Polling fallback — single snapshot of current host metrics."""
    return _collect_metrics()


@router.get("/health")
async def health():
    return {"status": "ok"}
