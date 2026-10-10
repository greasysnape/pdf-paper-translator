"""Heuristics for deciding which blocks should not be translated."""

from __future__ import annotations

import re

MATH_CHARS = set("=+−-×÷±∓·∑∏∫∂∇√∞≈≠≤≥∈∉⊂⊆∪∩∀∃→←↔⇒⇔αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ^_{}()[]|<>/*")

_REF_ONLY = re.compile(r"^\[?\d+(?:[,–-]\s*\d+)*\]?$")
_NUMERIC = re.compile(r"^[\d\s.,%±()+\-−×]+$")
_EQ_NUMBER = re.compile(r"^\(\d+[a-z]?\)$")
_URL_OR_DOI = re.compile(r"^(https?://|doi:|arXiv:)\S+$", re.IGNORECASE)
_FIG_LABEL = re.compile(r"^(fig(ure)?|table|tab|eq)\.?\s*\d+[a-z]?$", re.IGNORECASE)


def math_ratio(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    mathy = sum(1 for c in chars if c in MATH_CHARS or c.isdigit())
    return mathy / len(chars)


def alpha_words(text: str) -> int:
    return sum(1 for w in text.split() if sum(ch.isalpha() for ch in w) >= 3)


def should_translate(text: str, min_words: int = 2, max_math_ratio: float = 0.35) -> bool:
    t = text.strip()
    if not t:
        return False
    if _REF_ONLY.match(t) or _NUMERIC.match(t) or _EQ_NUMBER.match(t):
        return False
    if _URL_OR_DOI.match(t) or _FIG_LABEL.match(t):
        return False
    if alpha_words(t) < min_words:
        return False
    if math_ratio(t) > max_math_ratio:
        return False
    return True
