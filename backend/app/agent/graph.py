"""Build and compile the LangGraph multi-agent graph."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from app.agent.state import MultiAgentState, initial_state
from app.agent.supervisor import handle_l4_post_review, supervisor_node
from app.services.export import (
    artifact_manifest_path,
    write_artifact,
    write_gaps,
    write_manifest,
    write_task,
    write_task_index,
)
from app.services.log_bus import log_bus

logger = structlog.get_logger(__name__)


async def _export_node(state: MultiAgentState) -> dict[str, Any]:
    """Write all artifacts to disk and emit done event."""
    session_id = state["session_id"]
    artifacts = state.get("artifacts", {})
    tasks = state.get("tasks", [])
    artifacts_count = len([v for v in artifacts.values() if v])
    has_errors = bool(state.get("errors"))
    is_partial = state.get("status") in ("degraded", "completed_partial") or (
        has_errors and artifacts_count > 0
    )
    is_failed = artifacts_count == 0 and has_errors

    await log_bus.emit(
        session_id,
        "log_entry",
        {
            "level": "info",
            "agent_id": "export",
            "message": f"Writing {len(artifacts)} artifacts and {len(tasks)} tasks...",
        },
    )

    # Write artifacts
    for artifact_type, content in artifacts.items():
        if content:
            write_artifact(session_id, artifact_type, content)

    # Write tasks
    for task in tasks:
        try:
            write_task(session_id, task)
        except Exception as e:
            logger.warning("task_write_failed", task_id=task.get("id"), error=str(e))

    if tasks:
        try:
            write_task_index(session_id, tasks)
        except Exception as e:
            logger.warning("task_index_failed", error=str(e))

    # Write gaps.md if partial or failed
    if is_partial or is_failed or state.get("errors"):
        write_gaps(
            session_id,
            {
                "status": "failed" if is_failed else state.get("status", "unknown"),
                "reason": "time_budget_exceeded" if is_partial and not is_failed else "errors",
                "failed_steps": [
                    {"agent": e.split(":")[0], "reason": e} for e in state.get("errors", [])
                ],
                "open_questions": [q.get("text", "") for q in state.get("open_questions", [])],
                "manual_actions": ["Review gaps.md and complete missing sections manually"],
            },
        )

    # Build manifest
    elapsed = time.time() - state["started_at"]
    manifest = {
        "session_id": session_id,
        "spec_level": state["spec_level"],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_sec": int(elapsed),
        "artifacts": {k: artifact_manifest_path(k) for k in artifacts if artifacts[k]},
        "pipeline": state.get("pipeline", []),
        "pipeline_reasoning": state.get("pipeline_reasoning", ""),
        "tasks": {"count": len(tasks), "phases": _count_phases(tasks)},
        "context": {
            "session_summary": state.get("context", {}).get("session_summary", ""),
            "saturation": state.get("saturation_report", {}),
        },
        "assumptions": state.get("assumptions", []),
        "decisions": state.get("decisions", []),
        "review_reports": state.get("review_reports", []),
        "recovery_trace": state.get("recovery_trace", []),
        "errors": state.get("errors", []),
        "gaps_file": "gaps.md" if (is_partial or is_failed) else None,
    }
    write_manifest(session_id, manifest)

    if is_failed:
        final_status = "failed"
    elif is_partial:
        final_status = "completed_partial"
    else:
        final_status = "completed"
    await log_bus.emit(
        session_id,
        "done",
        {
            "duration_sec": elapsed,
            "artifacts_count": artifacts_count,
            "tasks_count": len(tasks),
            "assumptions_count": len(state.get("assumptions", [])),
            "fallbacks_count": len(state.get("fallbacks_triggered", [])),
            "is_partial": is_partial,
        },
    )

    return {**state, "status": final_status}


def _count_phases(tasks: list[dict]) -> int:
    return len({t.get("phase", "") for t in tasks})


async def run_graph(
    session_id: str,
    idea: str,
    rules: dict[str, Any],
    llm_provider,
    embedding_provider,
) -> None:
    """
    Main entry point — runs the entire agent graph.
    This is called as an asyncio.Task so it runs concurrently with the API.
    """
    from app.agent.agents.api_designer import APIDesignerAgent
    from app.agent.agents.architect import ArchitectAgent
    from app.agent.agents.context_manager import ContextManagerAgent
    from app.agent.agents.generic_spec import GenericSpecAgent
    from app.agent.agents.pipeline_planner import PipelinePlannerAgent
    from app.agent.agents.product_analyst import ProductAnalystAgent
    from app.agent.agents.researcher import ResearcherAgent
    from app.agent.agents.reviewer import ReviewerAgent
    from app.agent.agents.task_decomposer import TaskDecomposerAgent
    from app.agent.agents.ui_designer import UIDesignerAgent
    from app.agent.pipeline_utils import step_builtin_agent_id
    from app.services.session import save_checkpoint, save_pipeline, update_session_status
    from app.services.session_watchdog import watchdog

    spec_level = rules.get("spec_level", "L2")
    time_budget = _time_budget(spec_level)

    state = initial_state(
        session_id=session_id,
        idea=idea,
        rules=rules,
        time_budget_sec=time_budget,
    )

    await update_session_status(session_id, "running")
    await log_bus.emit(
        session_id,
        "log_entry",
        {
            "level": "info",
            "agent_id": "system",
            "message": f"Starting {spec_level} session — budget: {time_budget}s",
        },
    )

    if state.get("pipeline_planned") and state.get("pipeline"):
        await save_pipeline(session_id, state["pipeline"], state.get("pipeline_reasoning", ""))
        await log_bus.emit(
            session_id,
            "pipeline_planned",
            {
                "steps": state["pipeline"],
                "reasoning": state.get("pipeline_reasoning") or f"Fixed pipeline for {spec_level}",
            },
        )

    # Build agents
    builtin_agents = {
        "researcher": ResearcherAgent(
            llm=llm_provider, embedding_provider=embedding_provider, rag_cfg=rules.get("rag", {})
        ),
        "pipeline_planner": PipelinePlannerAgent(llm=llm_provider),
        "product_analyst": ProductAnalystAgent(llm=llm_provider),
        "architect": ArchitectAgent(llm=llm_provider),
        "api_designer": APIDesignerAgent(llm=llm_provider),
        "ui_designer": UIDesignerAgent(llm=llm_provider),
        "task_decomposer": TaskDecomposerAgent(llm=llm_provider),
        "reviewer": ReviewerAgent(llm=llm_provider),
        "context_manager": ContextManagerAgent(llm=llm_provider),
    }
    generic_agent = GenericSpecAgent(llm=llm_provider)

    def resolve_agent(step_id: str, state: MultiAgentState):
        if step_id == "export":
            return None
        step = None
        for s in state.get("pipeline") or []:
            if s.get("id") == step_id:
                step = s
                break
        if step:
            executor = step.get("executor", "")
            if executor == "generic":
                return generic_agent
            builtin_id = step_builtin_agent_id(step)
            if builtin_id and builtin_id in builtin_agents:
                return builtin_agents[builtin_id]
        return builtin_agents.get(step_id)

    resilience_cfg = rules.get("resilience", {})
    wd_state = watchdog.register(session_id, resilience_cfg)
    checkpoint_enabled = resilience_cfg.get("checkpoint_every_agent", True)

    try:
        max_steps = 200  # absolute safety limit
        step = 0
        while state["current_agent"] != "export" and step < max_steps:
            step += 1
            current = state["current_agent"]
            wd_state.mark_progress(current)

            if current == "supervisor":
                state = {**state, **await supervisor_node(state)}
                if state["current_agent"] == "export":
                    break
                continue

            cb = wd_state.get_circuit_breaker(current)
            if cb.is_open():
                await log_bus.emit(
                    session_id,
                    "circuit_breaker_open",
                    {
                        "agent_id": current,
                        "retry_after_sec": cb.cooldown_sec,
                    },
                )
                await asyncio.sleep(min(cb.cooldown_sec, 30))
                state["current_agent"] = "supervisor"
                continue

            agent = resolve_agent(current, state)
            if agent is None and current == "export":
                break
            if agent is None:
                logger.error("unknown_agent", agent=current)
                state = {
                    **state,
                    "current_agent": "supervisor",
                    "errors": [*state.get("errors", []), f"Unknown agent: {current}"],
                }
                continue

            try:
                prev_errors = len(state.get("errors", []))
                prev_review_count = len(state.get("review_reports", []))
                state = {
                    **state,
                    **await asyncio.wait_for(
                        agent.run(state), timeout=resilience_cfg.get("agent_timeout_sec", 600)
                    ),
                }
                agent_failed = state.pop("_last_agent_failed", False)
                if agent_failed or len(state.get("errors", [])) > prev_errors:
                    if cb.record_failure():
                        await log_bus.emit(
                            session_id,
                            "circuit_breaker_open",
                            {
                                "agent_id": current,
                                "retry_after_sec": resilience_cfg.get(
                                    "circuit_breaker_cooldown_sec", 60
                                ),
                            },
                        )
                else:
                    cb.record_success()

                # L4 post-review gate (runs after reviewer completes)
                if (
                    spec_level == "L4"
                    and len(state.get("review_reports", [])) > prev_review_count
                ):
                    l4_update = await handle_l4_post_review(state)
                    state = {**state, **l4_update}
                    if state.get("current_agent") == "export":
                        break
            except TimeoutError:
                cb.record_failure()
                await log_bus.emit(
                    session_id,
                    "agent_timeout",
                    {
                        "agent_id": current,
                        "timeout_sec": resilience_cfg.get("agent_timeout_sec", 600),
                    },
                )
                state = {
                    **state,
                    "current_agent": "supervisor",
                    "errors": [*state.get("errors", []), f"{current}: timeout"],
                    "status": "degraded",
                }
            except Exception as e:
                cb.record_failure()
                if cb.record_failure():
                    await log_bus.emit(
                        session_id,
                        "circuit_breaker_open",
                        {
                            "agent_id": current,
                            "retry_after_sec": resilience_cfg.get(
                                "circuit_breaker_cooldown_sec", 60
                            ),
                        },
                    )
                state = {
                    **state,
                    "current_agent": "supervisor",
                    "errors": [*state.get("errors", []), f"{current}: {e}"],
                }

            # Checkpoint
            if checkpoint_enabled:
                try:
                    cp_id = await save_checkpoint(session_id, current, _slim_state(state))
                    await log_bus.emit(
                        session_id,
                        "checkpoint_saved",
                        {"checkpoint_id": cp_id, "agent_id": current},
                    )
                    state = {**state, "checkpoints": [*state.get("checkpoints", []), cp_id]}
                except Exception as e:
                    logger.warning("checkpoint_failed", error=str(e))

        # Export
        state = {**state, **await _export_node(state)}

    except Exception as e:
        logger.exception("graph_fatal_error", error=str(e))
        await log_bus.emit(
            session_id, "error", {"code": "GRAPH_FATAL", "message": str(e), "recoverable": False}
        )
        state = {**state, "status": "failed"}
    finally:
        watchdog.unregister(session_id)
        final_status = state.get("status", "failed")
        await update_session_status(session_id, final_status)


def _time_budget(spec_level: str) -> int | None:
    return {"L1": 300, "L2": 900, "L3": 1800, "L4": None}.get(spec_level)


def _slim_state(state: MultiAgentState) -> dict:
    """Strip large artifact text from checkpoint to keep SQLite lean."""
    slim = {k: v for k, v in state.items() if k != "artifacts"}
    slim["artifacts"] = {k: f"<{len(v)} chars>" for k, v in state.get("artifacts", {}).items()}
    return slim
