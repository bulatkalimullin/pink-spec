"""SEARCH/REPLACE patch parsing and application for artifact refinement."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_BLOCK_RE = re.compile(
    r"<<<<<<< SEARCH\s*\n(.*?)\n=======\s*\n(.*?)\n>>>>>>> REPLACE",
    re.DOTALL,
)


@dataclass
class PatchOp:
    search: str
    replace: str


@dataclass
class PatchResult:
    applied: int = 0
    failed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    errors: list[str] = field(default_factory=list)


def annotate_lines(content: str) -> str:
    """Prefix each line with LNNN: for LLM navigation in patch prompts."""
    lines = content.splitlines()
    width = max(3, len(str(len(lines) or 1)))
    return "\n".join(f"L{i + 1:0{width}d}: {line}" for i, line in enumerate(lines))


def parse_patch_blocks(raw: str) -> list[PatchOp]:
    """Extract SEARCH/REPLACE operations from LLM output."""
    raw = raw.strip()
    ops: list[PatchOp] = []
    for match in _BLOCK_RE.finditer(raw):
        search = match.group(1)
        replace = match.group(2)
        if search or replace:
            ops.append(PatchOp(search=search, replace=replace))
    return ops


def _normalize_ws(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines())


def _count_line_delta(before: str, after: str) -> tuple[int, int]:
    old_lines = before.count("\n") + (1 if before else 0)
    new_lines = after.count("\n") + (1 if after else 0)
    if new_lines >= old_lines:
        return new_lines - old_lines, 0
    return 0, old_lines - new_lines


def _flexible_replace(content: str, search: str, replace: str) -> str | None:
    """Replace first occurrence where whitespace between tokens is flexible."""
    tokens = search.split()
    if not tokens:
        return None
    pattern = r"\s+".join(re.escape(t) for t in tokens)
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return None
    return content[: match.start()] + replace + content[match.end() :]


def apply_patches(content: str, ops: list[PatchOp]) -> tuple[str, PatchResult]:
    """Apply patch ops in order; fuzzy match on whitespace-normalized text if exact miss."""
    result = PatchResult()
    current = content

    for i, op in enumerate(ops):
        if not op.search:
            result.failed += 1
            result.errors.append(f"patch {i + 1}: empty SEARCH block")
            continue

        if op.search in current:
            before = current
            current = current.replace(op.search, op.replace, 1)
            added, removed = _count_line_delta(before, current)
            result.lines_added += added
            result.lines_removed += removed
            result.applied += 1
            continue

        norm_content = _normalize_ws(current)
        norm_search = _normalize_ws(op.search)
        if norm_search in norm_content:
            idx = norm_content.index(norm_search)
            end = idx + len(norm_search)
            lines_before = norm_content[:idx].count("\n")
            lines_search = norm_search.count("\n") + (1 if norm_search else 0)
            content_lines = current.splitlines(keepends=True)
            start_line = lines_before
            end_line = start_line + lines_search
            chunk = "".join(content_lines[start_line:end_line])
            if _normalize_ws(chunk) == norm_search:
                before = current
                current = "".join(content_lines[:start_line]) + op.replace + "".join(
                    content_lines[end_line:]
                )
                added, removed = _count_line_delta(before, current)
                result.lines_added += added
                result.lines_removed += removed
                result.applied += 1
                continue

        flex = _flexible_replace(current, op.search, op.replace)
        if flex is not None:
            before = current
            current = flex
            added, removed = _count_line_delta(before, current)
            result.lines_added += added
            result.lines_removed += removed
            result.applied += 1
            continue

        result.failed += 1
        result.errors.append(f"patch {i + 1}: SEARCH text not found in document")

    return current, result


def validate_patch_result(original: str, patched: str) -> bool:
    """Reject patches that empty the doc or shrink it drastically without explicit deletion."""
    if not patched.strip():
        return False
    if len(original.strip()) < 80:
        return bool(patched.strip())
    if len(patched) < len(original) * 0.5:
        return False
    return True
