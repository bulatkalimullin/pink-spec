"""Tests for SEARCH/REPLACE artifact patching."""

from __future__ import annotations

from app.services.artifact_patcher import (
    annotate_lines,
    apply_patches,
    parse_patch_blocks,
    validate_patch_result,
    PatchOp,
)


def test_parse_single_block():
    raw = """<<<<<<< SEARCH
old line
=======
new line
>>>>>>> REPLACE"""
    ops = parse_patch_blocks(raw)
    assert len(ops) == 1
    assert ops[0].search == "old line"
    assert ops[0].replace == "new line"


def test_parse_multiple_blocks():
    raw = """<<<<<<< SEARCH
a
=======
b
>>>>>>> REPLACE

<<<<<<< SEARCH
c
=======
d
>>>>>>> REPLACE"""
    assert len(parse_patch_blocks(raw)) == 2


def test_apply_exact_match():
    content = "# Title\n\nold body\n"
    ops = [PatchOp(search="old body", replace="new body")]
    patched, result = apply_patches(content, ops)
    assert "new body" in patched
    assert "old body" not in patched
    assert result.applied == 1
    assert result.failed == 0


def test_apply_fuzzy_whitespace():
    content = "# Title\n\nold   body\n"
    ops = [PatchOp(search="old body", replace="new body")]
    patched, result = apply_patches(content, ops)
    assert result.applied == 1
    assert "new body" in patched


def test_failed_patch_leaves_content():
    content = "unchanged"
    patched, result = apply_patches(content, [PatchOp(search="missing", replace="x")])
    assert patched == content
    assert result.applied == 0
    assert result.failed == 1


def test_validate_patch_result_rejects_empty():
    assert validate_patch_result("hello world " * 20, "") is False


def test_validate_patch_result_accepts_minor_edit():
    original = "# Spec\n\n" + "paragraph. " * 30
    patched = original.replace("paragraph.", "updated paragraph.", 1)
    assert validate_patch_result(original, patched) is True


def test_annotate_lines():
    out = annotate_lines("a\nbb")
    assert out.startswith("L001: a")
    assert "L002: bb" in out
