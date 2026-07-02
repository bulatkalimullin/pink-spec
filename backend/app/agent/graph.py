"""Build and compile the LangGraph multi-agent graph."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from app.agent.state import MultiAgentState, initial_state
from app.agent.stage_progress import emit_stage_changed
from app.agent.supervisor import check_l4_criteria, handle_l4_post_review, supervisor_node
from app.services.artifact_store import init_session_output, load_manifest_file, patch_manifest
from app.services.export import write_gaps
from app.services.log_bus import log_bus

logger = structlog.get_logger(__name__)


async def _export_node(state: MultiAgentState) -> dict[str, Any]:
    """Finalize manifest and gaps — artifacts/tasks already on disk."""
    session_id = state["session_id"]
    artifacts = state.get("artifacts", {})
    tasks = state.get("tasks", [])
    artifacts_count = len(artifacts)
    has_errors = bool(state.get("errors"))
    is_partial = state.get("status") in ("degraded", "completed_partial") or (
        has_errors and artifacts_count > 0
    )
    is_failed = artifacts_count == 0 and has_errors

    await emit_stage_changed(
        state,
        stage_id="export",
        label="Экспортируем",
        detail=f"{artifacts_count} артефактов, {len(tasks)} задач",
        agent_id="export",
        sub_progress=0.3,
    )

    await log_bus.emit(
        session_id,
        "log_entry",
        {
            "level": "info",
            "agent_id": "export",
            "message": f"Finalizing export: {artifacts_count} artifacts, {len(tasks)} tasks...",
        },
    )

    review_reports = state.get("review_reports", [])
    review_never_passed = bool(review_reports) and not any(r.get("passed") for r in review_reports)
    needs_gaps = (
        is_partial
        or is_failed
        or bool(state.get("errors"))
        or review_never_passed
        or state.get("_review_plateau")
    )

    if needs_gaps:
        gaps_payload: dict[str, Any] = {
            "status": "failed" if is_failed else state.get("status", "unknown"),
            "reason": _partial_export_reason(state, is_partial, is_failed, review_never_passed),
            "failed_steps": [
                {"agent": e.split(":")[0], "reason": e} for e in state.get("errors", [])
            ],
            "open_questions": [q.get("text", "") for q in state.get("open_questions", [])],
            "manual_actions": ["Review gaps.md and complete missing sections manually"],
        }
        if review_never_passed and not state.get("errors"):
            last = review_reports[-1] if review_reports else {}
            for issue in last.get("issues", [])[:10]:
                gaps_payload["failed_steps"].append(
                    {
                        "agent": "reviewer",
                        "reason": f"[{issue.get('severity', '?')}] {issue.get('description', '')}",
                    }
                )
            gaps_payload["manual_actions"].insert(
                0,
                f"Reviewer never passed after {len(review_reports)} cycle(s)",
            )
        if state.get("spec_level") == "L4":
            criteria = check_l4_criteria(state)
            unmet = [k for k, met in criteria.items() if not met]
            gaps_payload["l4_criteria"] = criteria
            gaps_payload["unmet_l4_criteria"] = unmet
            if unmet:
                gaps_payload["manual_actions"].insert(
                    0,
                    f"Unmet L4 criteria: {', '.join(unmet)}",
                )
        write_gaps(session_id, gaps_payload)

    elapsed = time.time() - state["started_at"]
    disk_manifest = load_manifest_file(session_id)
    manifest = {
        **disk_manifest,
        "session_id": session_id,
        "spec_level": state["spec_level"],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_sec": int(elapsed),
        "pipeline": state.get("pipeline", []),
        "pipeline_reasoning": state.get("pipeline_reasoning", ""),
        "tasks": disk_manifest.get("tasks") or {"count": len(tasks), "phases": _count_phases(tasks)},
        "context": {
            "session_summary": state.get("context", {}).get("session_summary", ""),
            "saturation": state.get("saturation_report", {}),
        },
        "assumptions": state.get("assumptions", []),
        "decisions": state.get("decisions", []),
        "review_reports": state.get("review_reports", []),
        "recovery_trace": state.get("recovery_trace", []),
        "errors": state.get("errors", []),
        "gaps_file": "gaps.md" if needs_gaps else None,
    }
    manifest_body = {k: v for k, v in manifest.items() if k != "session_id"}
    await patch_manifest(session_id, **manifest_body)

    if is_failed:
        final_status = "failed"
    elif is_partial:
        final_status = "completed_partial"
    else:
        final_status = "completed"
    await emit_stage_changed(
        state,
        stage_id="done",
        label="Готово",
        detail=f"{artifacts_count} артефактов",
        sub_progress=1.0,
    )
    if is_partial and state.get("spec_level") == "L4":
        criteria = check_l4_criteria(state)
        failed_criteria = [k for k, met in criteria.items() if not met]
        await log_bus.emit(
            session_id,
            "session_completed_partial",
            {
                "failed_criteria": failed_criteria,
                "criteria": criteria,
                "tasks_count": len(tasks),
                "review_cycles": state.get("review_cycles", 0),
            },
        )
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


def _partial_export_reason(
    state: MultiAgentState,
    is_partial: bool,
    is_failed: bool,
    review_never_passed: bool = False,
) -> str:
    if is_failed:
        return "errors"
    if review_never_passed:
        return "review_never_passed"
    if state.get("_review_plateau"):
        return "review_plateau"
    if not is_partial:
        return "unknown"
    if state.get("errors"):
        return "errors"
    if state.get("spec_level") == "L4":
        criteria = check_l4_criteria(state)
        unmet = [k for k, met in criteria.items() if not met]
        if unmet:
            return f"l4_criteria_unmet:{','.join(unmet)}"
    return "degraded"


async def run_graph(
    session_id: str,
    idea: str,
    rules: dict[str, Any],
    llm_provider,
    embedding_provider,
    cancel_event: asyncio.Event | None = None,
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
    from app.agent.agents.refinement_fixer import RefinementFixerAgent
    from app.agent.agents.researcher import ResearcherAgent
    from app.agent.agents.reviewer import ReviewerAgent
    from app.agent.agents.task_decomposer import TaskDecomposerAgent
    from app.agent.agents.ui_designer import UIDesignerAgent
    from app.agent.pipeline_utils import step_builtin_agent_id
    from app.services.session import save_checkpoint, save_pipeline, update_session_status
    from app.services.session_control import (
        apply_control_directives,
        apply_rules_overrides,
        clear_session,
        pop_all,
    )
    from app.services.session_watchdog import watchdog

    spec_level = rules.get("spec_level", "L2")
    time_budget = _time_budget(spec_level)
    rules = apply_rules_overrides(rules, session_id)

    from app.agent.l4_guards import apply_l4_runtime_guards
    from app.config import get_settings
    from app.llm.provider_resolver import active_llm_model_name

    rules, l4_warnings = apply_l4_runtime_guards(
        rules,
        global_llm_max_tokens=get_settings().llm_max_tokens,
        active_llm_model=active_llm_model_name(rules),
    )

    state = initial_state(
        session_id=session_id,
        idea=idea,
        rules=rules,
        time_budget_sec=time_budget,
    )
    init_session_output(session_id)

    await update_session_status(session_id, "running")
    await emit_stage_changed(
        state,
        stage_id="starting",
        label="Запускаем сессию",
        detail=f"Уровень {spec_level}",
        sub_progress=0.05,
    )
    await log_bus.emit(
        session_id,
        "log_entry",
        {
            "level": "info",
            "agent_id": "system",
            "message": f"Starting {spec_level} session — budget: {time_budget}s",
        },
    )
    for warning in l4_warnings:
        await log_bus.emit(
            session_id,
            "log_entry",
            {"level": "warn", "agent_id": "system", "message": warning},
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
        "refinement_fixer": RefinementFixerAgent(llm=llm_provider),
        "context_manager": ContextManagerAgent(llm=llm_provider),
    }
    generic_agent = GenericSpecAgent(llm=llm_provider)

    def resolve_agent(step_id: str, state: MultiAgentState):
        if step_id == "export":
            return None
        if step_id == "refinement_fixer":
            return builtin_agents["refinement_fixer"]
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

    from app.services.intake import (
        clear_intake_event,
        load_answered_qa,
        merge_answers_into_state,
        run_intake_phase,
        wait_for_intake_answers,
    )

    try:
        wd_state.mark_agent_started("intake")
        state, proceed = await run_intake_phase(state, llm_provider)
        if not proceed:
            from app.services.session import get_open_questions
            from app.services.session_runner import session_runner

            session_runner.clear_cancel(session_id)
        while not proceed:
            if cancel_event and cancel_event.is_set():
                open_qs = await get_open_questions(session_id)
                if open_qs:
                    session_runner.clear_cancel(session_id)
                else:
                    state = {**state, "current_agent": "export", "status": "degraded"}
                    break

            await emit_stage_changed(
                state,
                stage_id="intake",
                label="Ждём ответы",
                detail="Ответьте на все вопросы в панели Questions",
                agent_id="intake",
                sub_progress=0.1,
            )

            hitl_timeout = int(resilience_cfg.get("hitl_timeout_sec", 3600))
            resolved = await wait_for_intake_answers(session_id, hitl_timeout, watchdog)
            qa_rows = await load_answered_qa(session_id)
            if not resolved and not qa_rows:
                await log_bus.emit(
                    session_id,
                    "log_entry",
                    {
                        "level": "warn",
                        "agent_id": "intake",
                        "message": "Intake timeout — proceeding with available context",
                    },
                )
                state = {**state, "intake_complete": True, "status": "running"}
                proceed = True
                break

            state = merge_answers_into_state(state, qa_rows)
            state = {**state, "status": "running", "open_questions": []}
            await update_session_status(session_id, "running")
            if wd_state:
                wd_state.status = "running"
                wd_state.last_progress_at = time.time()
            await log_bus.emit(
                session_id,
                "intake_complete",
                {"ready": True, "answers_count": len(qa_rows)},
            )
            proceed = True

        if wd_state:
            wd_state.mark_agent_completed()
            if wd_state.current_agent == "intake":
                wd_state.current_agent = "supervisor"

        if state.get("current_agent") == "export":
            state = {**state, **await _export_node(state)}
            return

        max_steps = 200  # absolute safety limit
        step = 0
        while state["current_agent"] != "export" and step < max_steps:
            step += 1

            if cancel_event and cancel_event.is_set():
                state = {**state, "current_agent": "export", "status": "degraded"}
                break

            wd_check = watchdog.get_state(session_id)
            if wd_check and wd_check.status == "failed":
                state = {**state, "current_agent": "export", "status": "failed"}
                break
            if wd_check and wd_check.status == "paused":
                await asyncio.sleep(1)
                continue

            if step % 10 == 0:
                logger.debug(
                    "graph_iteration",
                    session_id=session_id,
                    step=step,
                    current_agent=state.get("current_agent"),
                    outputs_count=len(state.get("agent_outputs", {})),
                    artifacts_count=len(state.get("artifacts", {})),
                )

            directives = pop_all(session_id)
            if directives:
                state = apply_control_directives(state, directives)
                state["rules"] = apply_rules_overrides(state.get("rules", {}), session_id)
                if state.get("current_agent") == "export":
                    break

            current = state["current_agent"]

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
                wd_state.mark_agent_started(current)
                state = {
                    **state,
                    **await asyncio.wait_for(
                        agent.run(state), timeout=resilience_cfg.get("agent_timeout_sec", 600)
                    ),
                }
                wd_state.mark_agent_completed()
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

    except asyncio.CancelledError:
        logger.info("graph_cancelled", session_id=session_id)
        state = {**state, "current_agent": "export", "status": "degraded"}
        try:
            state = {**state, **await _export_node(state)}
        except Exception:
            logger.exception("export_after_cancel_failed", session_id=session_id)
    except Exception as e:
        logger.exception("graph_fatal_error", error=str(e))
        await log_bus.emit(
            session_id, "error", {"code": "GRAPH_FATAL", "message": str(e), "recoverable": False}
        )
        state = {**state, "status": "failed"}
    finally:
        clear_intake_event(session_id)
        clear_session(session_id)
        watchdog.unregister(session_id)
        final_status = state.get("status", "failed")
        await update_session_status(session_id, final_status)
        try:
            from app.services.stats_collector import collect_and_persist_metrics

            await collect_and_persist_metrics(session_id, dict(state))
        except Exception:
            logger.exception("metrics_collect_failed", session_id=session_id)


def _time_budget(spec_level: str) -> int | None:
    return {"L1": 300, "L2": 900, "L3": 1800, "L4": None}.get(spec_level)


def _slim_state(state: MultiAgentState) -> dict:
    """Strip large artifact text from checkpoint to keep SQLite lean."""
    slim = dict(state)
    slim["artifacts"] = dict(state.get("artifacts", {}))
    return slim
