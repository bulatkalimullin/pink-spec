---
id: "NNN"
phase: "XX-phase-name"
title: "Short imperative title of the task"
priority: high
estimated_minutes: 45
depends_on: []
spec_refs:
  - "architecture_spec.md#relevant-section"
tags: []
status: todo
---

## Goal

One sentence describing what must work after this task is done.

## Context

2–3 sentences connecting this task to the larger project. Reference the relevant spec section or ADR if applicable.

## Steps

1. Step one — concrete action.
2. Step two — another concrete action.
3. Step three — finalize and verify.

## Acceptance Criteria

- [ ] Criterion A is satisfied.
- [ ] Criterion B passes all checks.
- [ ] No regressions in existing tests (if applicable).

## Notes / Pitfalls

- Watch out for X when doing Y.
- If Z happens, see `architecture_spec.md#section` for guidance.

## Verification

Describe how to verify completion:

```bash
# Example command or test
```

Or: navigate to `http://localhost:PORT/endpoint` and confirm the response.
