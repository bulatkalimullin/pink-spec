#!/usr/bin/env python3
"""Full replan for session b2e53269 — clear output, keep intake answers, relaunch."""

import asyncio
import json
import sys
from datetime import UTC, datetime

SESSION = "b2e53269-e9c0-4179-8e35-560ab99db942"


async def main() -> None:
    from app.db.connection import get_db
    from app.services.session import get_session
    from app.services.artifact_store import clear_session_output
    from app.services.session_control import clear_session
    from app.services.session_runner import session_runner
    from app.services.intake import load_answered_qa
    from app.services.log_bus import log_bus

    session = await get_session(SESSION)
    if not session:
        print("ERROR: session not found", file=sys.stderr)
        sys.exit(1)

    if session_runner.is_running(SESSION):
        print("Cancelling running graph...")
        await session_runner.cancel(SESSION)
        await asyncio.sleep(2)

    rules = dict(session["rules"])
    ollama = dict(rules.get("ollama") or {})
    ollama["llm_model"] = "jayeshpandit2480/gemma3-UNCENSORED:4b"
    ollama["fallback_models"] = ["gemma3:4b", "gemma3:1b"]
    rules["ollama"] = ollama
    rules["llm_provider"] = "ollama"
    project = dict(rules.get("project") or {})
    project["domain"] = "embedded"
    rules["project"] = project
    pipeline_cfg = dict(rules.get("pipeline") or {})
    pipeline_cfg["mode"] = "auto"
    rules["pipeline"] = pipeline_cfg

    from app.agent.agents.pipeline_planner import apply_domain_l4_rules

    rules = apply_domain_l4_rules(rules)

    clear_session_output(SESSION)
    clear_session(SESSION)

    answered = await load_answered_qa(SESSION)
    print(f"Preserving {len(answered)} intake answer(s)")

    now = datetime.now(UTC).isoformat()
    async with get_db() as db:
        await db.execute(
            "UPDATE sessions SET status=?, rules_json=?, pipeline_json=NULL, manifest_json=NULL, updated_at=? WHERE id=?",
            ("interrupted", json.dumps(rules), now, SESSION),
        )
        await db.commit()

    await log_bus.emit(
        SESSION,
        "log_entry",
        {
            "level": "info",
            "agent_id": "system",
            "message": (
                f"Полный реплан: output очищен, domain=embedded, model={ollama['llm_model']}, "
                f"сохранено ответов intake: {len(answered)}. Ожидает POST /restart."
            ),
        },
    )
    print("OK: prep done — call POST /restart")


if __name__ == "__main__":
    asyncio.run(main())
