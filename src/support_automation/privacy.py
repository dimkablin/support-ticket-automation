from __future__ import annotations

import re

PATTERNS = (
    (re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}"), "[EMAIL]"),
    (
        re.compile(r"(?<!\d)(?:\+7|8)[\s()-]*\d{3}[\s()-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)"),
        "[PHONE]",
    ),
    (re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"), "[CARD]"),
)


def mask_pii(text: str) -> str:
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text
