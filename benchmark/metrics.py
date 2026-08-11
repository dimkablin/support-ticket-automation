from __future__ import annotations

import re


def reciprocal_rank(expected: str, actual: list[str]) -> float:
    try:
        return 1.0 / (actual.index(expected) + 1)
    except ValueError:
        return 0.0


def fact_coverage(answer: str, required: list[str]) -> float:
    normalized = answer.casefold()
    return sum(fact.casefold() in normalized for fact in required) / len(required)


def forbidden_fact_rate(answer: str, forbidden: list[str]) -> float:
    normalized = answer.casefold()
    return sum(fact.casefold() in normalized for fact in forbidden) / len(forbidden)


def token_f1(predicted: str, expected: str) -> float:
    predicted_tokens = set(re.findall(r"\w+", predicted.casefold()))
    expected_tokens = set(re.findall(r"\w+", expected.casefold()))
    if not predicted_tokens or not expected_tokens:
        return 0.0
    overlap = len(predicted_tokens & expected_tokens)
    precision = overlap / len(predicted_tokens)
    recall = overlap / len(expected_tokens)
    return 2 * precision * recall / (precision + recall) if overlap else 0.0
