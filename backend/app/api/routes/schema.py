"""Serve JSON Schema for the rules config (used by Monaco editor)."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.rules import Rules

router = APIRouter(prefix="/api/v1", tags=["schema"])


@router.get("/schema/rules")
async def get_rules_schema():
    return Rules.model_json_schema()


@router.get("/spec-levels")
async def get_spec_levels():
    return {
        "levels": [
            {"id": "L1", "name": "Brief", "time": "2–5 min", "description": "Outline only"},
            {
                "id": "L2",
                "name": "Standard",
                "time": "10–15 min",
                "description": "Core specs + 15–30 tasks",
            },
            {
                "id": "L3",
                "name": "Full",
                "time": "20–30 min",
                "description": "All artifacts + 50–100 tasks",
            },
            {
                "id": "L4",
                "name": "Exhaustive",
                "time": "Until approved",
                "description": "Deep-dive, iterative refinement",
            },
        ]
    }
