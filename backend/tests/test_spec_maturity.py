"""Tests for spec maturity resolution and pipeline defaults."""

from app.agent.spec_maturity import (
    build_maturity_prompt_block,
    is_production_maturity,
    maturity_pipeline_defaults,
    resolve_spec_maturity,
)
from app.schemas.rules import Rules, SpecLevel


def test_resolve_default_l2_mvp():
    rules = {"spec_level": "L2", "project": {}}
    assert resolve_spec_maturity(rules, "L2") == "mvp"


def test_resolve_default_l4_production():
    rules = {"spec_level": "L4", "project": {}}
    assert resolve_spec_maturity(rules, "L4") == "production"


def test_resolve_explicit_maturity():
    rules = {"spec_level": "L4", "project": {"spec_maturity": "enterprise"}}
    assert resolve_spec_maturity(rules, "L4") == "enterprise"


def test_l4_production_pipeline_defaults():
    defaults = maturity_pipeline_defaults("production", "L4")
    assert defaults["min_steps"] >= 20
    assert defaults["min_deliverables"] >= 12
    assert defaults["max_replan_cycles"] >= 4


def test_rules_validator_l4_production_min_steps():
    rules = Rules(spec_level=SpecLevel.L4, project={"spec_maturity": "production"})
    assert rules.pipeline.min_steps >= 20
    assert rules.pipeline.min_deliverables >= 12


def test_production_prompt_block_forbids_mvp():
    block = build_maturity_prompt_block("production", "software")
    assert "NOT MVP" in block or "production" in block.lower()
    assert is_production_maturity("production")


def test_mvp_prompt_allows_deferred():
    block = build_maturity_prompt_block("mvp", "software")
    assert "DEFERRED" in block
