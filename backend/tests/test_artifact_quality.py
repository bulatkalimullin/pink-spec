"""Tests for artifact quality gates."""

from app.agent.supervisor import review_issues_plateau
from app.services.artifact_quality import (
    content_similarity,
    deduplicate_tasks,
    extract_assumptions,
    inject_nfr_from_intake,
    load_existing_artifact_texts,
    normalize_embedding_vector,
    validate_artifact_key,
)


def test_extract_assumptions():
    text = "Hello [ASSUMPTION: Photo analysis is Phase 2] world"
    assert extract_assumptions(text) == ["Photo analysis is Phase 2"]


def test_validate_artifact_key_ok():
    content = "# Spec\n\n**Artifact Key:** security_spec\n\nBody text here."
    ok, msg = validate_artifact_key(content, "security_spec")
    assert ok is True
    assert msg == ""


def test_validate_artifact_key_wrong():
    content = "**Artifact Key:** webapp_telegram_design\n\nDuplicate boilerplate."
    ok, msg = validate_artifact_key(content, "security_spec")
    assert ok is False
    assert "Wrong artifact key" in msg


def test_content_similarity_detects_duplicates():
    a = "Okay, here's a consolidated technical specification " * 20
    b = "Okay, here's a consolidated technical specification " * 20
    assert content_similarity(a, b) > 0.95


def test_normalize_embedding_vector_numpy_scalar():
    import numpy as np

    vec = [np.float32(-0.01719826)] * 3
    out = normalize_embedding_vector(vec)
    assert all(isinstance(x, float) for x in out)
    assert len(out) == 3


def test_deduplicate_tasks_merges_titles():
    tasks = [
        {"id": "001", "title": "Define User Profile Schema", "spec_refs": ["docs/a.md"]},
        {"id": "002", "title": "define user profile schema", "spec_refs": ["docs/b.md"]},
        {"id": "003", "title": "Other Task", "spec_refs": []},
    ]
    out = deduplicate_tasks(tasks)
    assert len(out) == 2
    assert out[0]["id"] == "001"
    assert "docs/a.md" in out[0]["spec_refs"]
    assert "docs/b.md" in out[0]["spec_refs"]


def test_inject_nfr_from_intake_rps():
    rules = {"nfr": {}}
    idea = "Telegram dating bot 3000+ RPS"
    answers = {"q1": "Хэширование и шифрования"}
    updated = inject_nfr_from_intake(rules, idea, answers)
    assert updated["nfr"]["latency_p95_ms"] == 200
    assert updated["nfr"]["availability"] == "99.5%"
    assert "TLS 1.3" in updated["nfr"]["security"]


def test_review_issues_plateau():
    issue = {
        "severity": "critical",
        "description": "Missing NFRs",
        "location": "spec#1",
    }
    reports = [{"passed": False, "issues": [issue]} for _ in range(3)]
    assert review_issues_plateau(reports, window=3) is True
    reports[-1]["passed"] = True
    assert review_issues_plateau(reports, window=3) is False


def test_load_existing_artifact_texts_uses_export_reader(tmp_path, monkeypatch):
    from app.services import export as export_mod
    from app.services.artifact_store import init_session_output, save_artifact

    session_id = "sess-load-texts"
    monkeypatch.setattr(export_mod, "OUTPUT_ROOT", tmp_path)

    async def noop_save_manifest(_sid: str, _manifest: dict) -> None:
        pass

    monkeypatch.setattr("app.services.artifact_store.save_manifest", noop_save_manifest)

    import asyncio

    init_session_output(session_id)
    asyncio.run(
        save_artifact(session_id, "product_spec", "# Product\n\n**Artifact Key:** product_spec\n\nBody")
    )

    texts = load_existing_artifact_texts(session_id)
    assert "product_spec" in texts
    assert "Body" in texts["product_spec"]
