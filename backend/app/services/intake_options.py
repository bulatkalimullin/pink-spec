"""Normalize intake question options from LLM output."""

from __future__ import annotations

import re

# Meta / placeholder labels that are not real answer choices.
_META_OPTION_PATTERNS = (
    r"^выбрать\s+из\s+списка$",
    r"^select\s+from\s+(the\s+)?list$",
    r"^choose\s+from\s+(the\s+)?list$",
    r"^pick\s+from\s+(the\s+)?list$",
    r"^другое$",
    r"^other$",
    r"^прочее$",
    r"^свой\s+вариант$",
    r"^custom(\s+answer)?$",
    r"^none\s+of\s+the\s+above$",
    r"^ни\s+один\s+из\s+вышеуказанных$",
    r"^n/?a$",
    r"^—+$",
    r"^\.{2,}$",
    r"^optional$",
    r"^опционально$",
)

_META_RE = re.compile("|".join(f"(?:{p})" for p in _META_OPTION_PATTERNS), re.IGNORECASE)


def _is_meta_option(label: str) -> bool:
    return bool(_META_RE.match(label.strip()))


def normalize_intake_options(options: list | None, language: str = "en") -> list[str]:
    """
    Return 2–8 concrete choice labels, or [] for free-text questions.

    Single options, meta-instructions, and duplicates are stripped.
    Fewer than two valid choices → free text (empty options).
    """
    _ = language  # reserved for locale-specific meta patterns later
    if not options or not isinstance(options, list):
        return []

    seen: set[str] = set()
    normalized: list[str] = []
    for raw in options:
        label = str(raw).strip()
        if not label or _is_meta_option(label):
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(label)

    if len(normalized) < 2:
        return []
    return normalized[:8]
