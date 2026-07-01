"""Tests for statistics collector, scores, and aggregator."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.services.session_metrics_accumulator import SessionMetricsAccumulator
from app.services.stats_aggregator import _aggregate_rows, _summary_from_row
from app.services.stats_collector import (
    _analyze_logs,
    _compute_scores,
    build_metrics_from_state,
)


def _sample_state(**overrides) -> dict:
    base = {
        "session_id": "test-session-1",
        "idea": "A SaaS task tracker for remote teams",
        "rules": {"spec_level": "L2", "pipeline": {"mode": "auto"}},
        "spec_level": "L2",
        "status": "completed",
        "started_at": time.time() - 600,
        "time_budget_sec": 900,
        "artifacts": {
            "product_spec": "# Product",
            "architecture_spec": "# Arch",
            "api_spec": "openapi: 3",
        },
        "tasks": [
            {"phase": "foundation", "priority": "high", "estimated_minutes": 30},
            {"phase": "foundation", "priority": "medium", "estimated_minutes": 20},
            {"phase": "backend", "priority": "low", "estimated_minutes": 15},
        ],
        "agent_call_counts": {"product_analyst": 1, "architect": 1, "task_decomposer": 2},
        "agent_durations": {"product_analyst": 45000, "architect": 60000, "task_decomposer": 90000},
        "review_cycles": 0,
        "checkpoints": ["cp1", "cp2"],
        "assumptions": ["Uses PostgreSQL"],
        "decisions": [{"text": "Use FastAPI"}],
        "open_questions": [],
        "review_reports": [{"passed": True}],
        "errors": [],
        "fallbacks_triggered": [],
        "recovery_trace": [],
        "saturation_report": {"iterations": 3, "chunks": 12, "novelty": 0.8},
        "pipeline": [{"agent_id": "researcher"}, {"agent_id": "product_analyst"}],
        "has_gaps_file": False,
        "is_partial": False,
    }
    base.update(overrides)
    return base


def _sample_logs() -> list[dict]:
    return [
        {"type": "agent_started", "payload": {"agent_id": "product_analyst"}},
        {
            "type": "agent_completed",
            "payload": {"agent_id": "product_analyst", "duration_ms": 45000, "status": "success"},
        },
        {
            "type": "completion_check",
            "payload": {
                "criteria": {"tasks_ok": True, "artifacts_ok": True},
                "all_met": True,
            },
        },
        {"type": "refinement_cycle", "payload": {"cycle": 1, "confidence": 0.92}},
        {"type": "log_entry", "payload": {"level": "error", "agent_id": "x", "message": "oops"}},
    ]


class TestAnalyzeLogs:
    def test_counts_event_types(self):
        result = _analyze_logs(_sample_logs())
        assert result["events_total"] == 5
        assert result["events_by_type"]["agent_started"] == 1
        assert result["log_errors_count"] == 1
        assert result["l4_all_met"] is True
        assert result["l4_final_confidence"] == 0.92

    def test_agent_durations_from_logs(self):
        result = _analyze_logs(_sample_logs())
        assert result["agent_durations_from_logs"]["product_analyst"] == 45000


class TestComputeScores:
    def test_completed_high_quality(self):
        scores = _compute_scores(
            status="completed",
            spec_level="L2",
            is_partial=False,
            artifacts_count=3,
            tasks_total=20,
            duration_sec=600,
            assumptions_count=2,
            errors_count=0,
            fallbacks_count=0,
            has_gaps_file=False,
            l4_all_met=True,
            review_reports_count=1,
            circuit_breaker_opens=0,
            agent_timeouts=0,
            session_stuck_events=0,
        )
        assert scores["quality_score"] >= 80
        assert scores["reliability_score"] == 100.0

    def test_failed_low_quality(self):
        scores = _compute_scores(
            status="failed",
            spec_level="L2",
            is_partial=False,
            artifacts_count=0,
            tasks_total=0,
            duration_sec=100,
            assumptions_count=20,
            errors_count=5,
            fallbacks_count=3,
            has_gaps_file=True,
            l4_all_met=False,
            review_reports_count=0,
            circuit_breaker_opens=2,
            agent_timeouts=1,
            session_stuck_events=1,
        )
        assert scores["quality_score"] < 30
        assert scores["reliability_score"] < 70

    def test_partial_moderate_quality(self):
        scores = _compute_scores(
            status="completed_partial",
            spec_level="L3",
            is_partial=True,
            artifacts_count=2,
            tasks_total=30,
            duration_sec=1500,
            assumptions_count=8,
            errors_count=1,
            fallbacks_count=1,
            has_gaps_file=True,
            l4_all_met=False,
            review_reports_count=0,
            circuit_breaker_opens=0,
            agent_timeouts=0,
            session_stuck_events=0,
        )
        assert 15 <= scores["quality_score"] <= 60


class TestBuildMetrics:
    def test_full_metrics_shape(self):
        infra = {
            "cpu_avg": 25.0,
            "cpu_peak": 80.0,
            "ram_avg": 40.0,
            "ram_peak": 70.0,
            "gpu_mem_peak": 0.0,
            "process_rss_peak_mb": 512.0,
            "system_warnings_count": 1,
            "infra_samples_count": 10,
        }
        metrics = build_metrics_from_state(_sample_state(), _sample_logs(), infra)

        assert metrics["session_id"] == "test-session-1"
        assert metrics["artifacts_count"] == 3
        assert metrics["tasks_total"] == 3
        assert metrics["tasks_by_phase"]["foundation"] == 2
        assert metrics["slowest_agent_id"] == "task_decomposer"
        assert metrics["l4_all_met"] is True
        assert metrics["cpu_peak"] == 80.0
        assert "quality_score" in metrics["scores"]
        assert metrics["events_total"] == 5

    def test_rag_fallback_detection(self):
        state = _sample_state(
            fallbacks_triggered=[{"layer": "embedding", "step": "embed", "message": "fallback"}]
        )
        metrics = build_metrics_from_state(state, [], {})
        assert metrics["rag_fallback_used"] is True
        assert metrics["fallbacks_by_layer"]["embedding"] == 1


class TestAccumulator:
    def test_record_and_snapshot(self):
        acc = SessionMetricsAccumulator()
        acc.record("s1", {"cpu_percent": 50, "ram_percent": 60, "process_rss_mb": 100})
        acc.record("s1", {"cpu_percent": 80, "ram_percent": 70, "process_rss_mb": 200})
        acc.record_warning("s1")
        snap = acc.snapshot("s1")
        assert snap["cpu_peak"] == 80.0
        assert snap["cpu_avg"] == 65.0
        assert snap["system_warnings_count"] == 1
        acc.clear("s1")
        assert acc.snapshot("s1")["infra_samples_count"] == 0


class TestAggregator:
    def _make_row(self, session_id: str, status: str, spec: str, quality: float, metrics: dict):
        return {
            "session_id": session_id,
            "status": status,
            "spec_level": spec,
            "completed_at": "2026-06-15T12:00:00+00:00",
            "duration_sec": 600.0,
            "quality_score": quality,
            "metrics_json": json.dumps(metrics),
        }

    def test_aggregate_multiple_rows(self):
        rows = [
            self._make_row(
                "s1",
                "completed",
                "L2",
                85.0,
                {
                    "artifacts_count": 5,
                    "tasks_total": 20,
                    "errors_count": 0,
                    "fallbacks_count": 0,
                    "agent_calls": {"architect": 2},
                    "agent_durations_ms": {"architect": 50000},
                    "errors_by_agent": {},
                    "circuit_breaker_opens": 0,
                    "agent_timeouts": 0,
                    "session_stuck_events": 0,
                    "budget_warnings_count": 0,
                    "cpu_peak": 70,
                    "ram_peak": 60,
                    "scores": {"efficiency_score": 80, "reliability_score": 95},
                },
            ),
            self._make_row(
                "s2",
                "failed",
                "L4",
                20.0,
                {
                    "artifacts_count": 0,
                    "tasks_total": 0,
                    "errors_count": 3,
                    "fallbacks_count": 2,
                    "agent_calls": {"reviewer": 5},
                    "agent_durations_ms": {"reviewer": 120000},
                    "errors_by_agent": {"reviewer": 3},
                    "circuit_breaker_opens": 1,
                    "agent_timeouts": 1,
                    "session_stuck_events": 1,
                    "budget_warnings_count": 2,
                    "cpu_peak": 90,
                    "ram_peak": 85,
                    "scores": {"efficiency_score": 10, "reliability_score": 40},
                },
            ),
        ]
        stats = _aggregate_rows(rows)
        assert stats["totals"]["sessions"] == 2
        assert stats["totals"]["completed"] == 1
        assert stats["totals"]["failed"] == 1
        assert stats["rates"]["success_rate"] == 50.0
        assert "L2" in stats["by_spec_level"]
        assert "L4" in stats["by_spec_level"]
        assert len(stats["agent_leaderboard"]) >= 2
        assert stats["reliability"]["circuit_breaker_opens"] == 1

    def test_summary_from_row(self):
        row = self._make_row(
            "abc",
            "completed",
            "L2",
            75.0,
            {
                "artifacts_count": 4,
                "tasks_total": 15,
                "errors_count": 1,
                "scores": {"efficiency_score": 70, "reliability_score": 90},
            },
        )
        summary = _summary_from_row(row)
        assert summary["session_id"] == "abc"
        assert summary["quality_score"] == 75.0
        assert summary["tasks_total"] == 15


@pytest.mark.asyncio
async def test_collect_session_metrics_with_mock_logs():
    from app.services.stats_collector import collect_session_metrics

    state = _sample_state()
    logs = _sample_logs()

    with patch(
        "app.services.stats_collector.log_bus.get_log_history",
        new_callable=AsyncMock,
        return_value=logs,
    ):
        metrics = await collect_session_metrics("test-session-1", state)

    assert metrics["artifacts_count"] == 3
    assert metrics["l4_all_met"] is True


@pytest.mark.asyncio
async def test_backfill_skips_existing():
    from contextlib import asynccontextmanager

    from app.services.stats_aggregator import backfill_all_sessions

    mock_db = AsyncMock()

    sessions_cursor = AsyncMock()
    sessions_cursor.fetchall = AsyncMock(return_value=[{"id": "s1", "status": "completed"}])
    existing_cursor = AsyncMock()
    existing_cursor.fetchone = AsyncMock(return_value=(1,))
    mock_db.execute = AsyncMock(side_effect=[sessions_cursor, existing_cursor])

    @asynccontextmanager
    async def fake_get_db():
        yield mock_db

    with (
        patch("app.services.stats_aggregator.get_db", fake_get_db),
        patch(
            "app.services.stats_aggregator.collect_and_persist_metrics",
            new_callable=AsyncMock,
        ) as mock_collect,
        patch(
            "app.services.stats_aggregator.rebuild_global_stats",
            new_callable=AsyncMock,
        ),
    ):
        result = await backfill_all_sessions(force=False)
        assert result["skipped"] == 1
        assert result["processed"] == 0
        mock_collect.assert_not_called()
