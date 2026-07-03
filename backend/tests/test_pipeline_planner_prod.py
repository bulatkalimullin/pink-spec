"""Production pipeline depth tests."""

from app.agent.domain_profiles import get_domain_deliverables, get_domain_work_packages
from app.agent.pipeline_utils import ensure_domain_deliverables, expand_prod_deliverables


def test_software_production_deliverables_include_ops():
    keys = {d["artifact_key"] for d in get_domain_deliverables("software", "production")}
    assert "observability_spec" in keys
    assert "operational_spec" in keys
    assert "sla_spec" in keys


def test_embedded_production_deliverables_include_ota():
    keys = {d["artifact_key"] for d in get_domain_deliverables("embedded", "production")}
    assert "ota_update_spec" in keys
    assert "manufacturing_spec" in keys


def test_embedded_production_work_packages():
    wp_ids = {wp["id"] for wp in get_domain_work_packages("embedded", "production")}
    assert "wp_certification" in wp_ids
    assert "wp_field_ops" in wp_ids


def test_ensure_domain_deliverables_production_software():
    steps = [{"id": "reviewer", "executor": "builtin:reviewer", "artifact_key": None}]
    result = ensure_domain_deliverables(steps, "software", min_deliverables=12, maturity="production")
    keys = {s.get("artifact_key") for s in result if s.get("artifact_key")}
    assert "product_spec" in keys
    assert "observability_spec" in keys
    assert len([s for s in result if s.get("executor") == "generic"]) >= 8


def test_expand_prod_splits_security_spec():
    steps = [
        {
            "id": "security_spec",
            "executor": "generic",
            "artifact_key": "security_spec",
            "prompt_focus": "security",
        }
    ]
    expanded = expand_prod_deliverables(steps, "software", "production")
    keys = {s.get("artifact_key") for s in expanded}
    assert "threat_model" in keys
    assert "security_controls" in keys
    assert "security_spec" not in keys
