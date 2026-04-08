"""
NexDesk Graders
Each grader returns a float strictly in (0.0, 1.0) — never 0.0 or 1.0 exactly.
All graders are deterministic given the same input.
"""

from typing import Any, Dict

_EPS = 0.001  # minimum non-zero score / distance from 1.0


def _strict(score: float) -> float:
    """Clamp score to strictly open interval (0, 1) — validator requirement."""
    return round(max(_EPS, min(1.0 - _EPS, score)), 4)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _kw_score(text: str, keywords: list[str]) -> float:
    """Score based on how many keywords appear in text (case-insensitive)."""
    if not text or not keywords:
        return _EPS
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    return min(hits / max(len(keywords) * 0.4, 1), 1.0 - _EPS)


def _sla_score(predicted: int | None, expected: int) -> float:
    """Score SLA estimate. Within 2x = 0.9, within 4x = 0.5, beyond = 0.1"""
    if predicted is None:
        return _EPS
    ratio = predicted / expected if expected > 0 else 0.999
    if 0.5 <= ratio <= 2.0:
        return 0.9
    if 0.25 <= ratio <= 4.0:
        return 0.5
    return 0.1


# ─────────────────────────────────────────────
# Task 1: ticket_classify  (easy)
# Max score: 1.0
# Components: priority (0.5) + category (0.5)
# ─────────────────────────────────────────────


def grade_classify(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    score = _EPS

    # Priority score
    pred_priority = (action.get("priority") or "").strip().lower()
    if pred_priority == ticket["gt_priority"]:
        score += 0.5
    elif pred_priority in ticket.get("gt_priority_ok", []):
        score += 0.25

    # Category score
    pred_category = (action.get("category") or "").strip().lower()
    if pred_category == ticket["gt_category"]:
        score += 0.5
    elif pred_category in ticket.get("gt_category_ok", []):
        score += 0.25

    return _strict(score)


# ─────────────────────────────────────────────
# Task 2: ticket_route  (medium)
# Max score per step:
#   Step 1: priority(0.25) + category(0.25) + team(0.35) = 0.85
#   Step 2: affected_system(0.15) → total 1.0
# ─────────────────────────────────────────────


def grade_route_step1(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    score = _EPS

    pred_priority = (action.get("priority") or "").strip().lower()
    if pred_priority == ticket["gt_priority"]:
        score += 0.25
    elif pred_priority in ticket.get("gt_priority_ok", []):
        score += 0.12

    pred_category = (action.get("category") or "").strip().lower()
    if pred_category == ticket["gt_category"]:
        score += 0.25
    elif pred_category in ticket.get("gt_category_ok", []):
        score += 0.12

    pred_team = (action.get("team") or "").strip().lower()
    if pred_team == ticket["gt_team"]:
        score += 0.35
    elif pred_team in ticket.get("gt_team_ok", []):
        score += 0.17

    return _strict(score)


def grade_route_step2(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    pred_system = (action.get("affected_system") or "").strip().lower()
    gt_system = ticket.get("gt_affected_system", "").lower()
    if gt_system and gt_system in pred_system:
        return _strict(0.15)
    if pred_system:
        return _strict(0.07)
    return _EPS


# ─────────────────────────────────────────────
# Task 3: ticket_resolve  (hard)
# Max score per step:
#   Step 1: priority(0.15) + category(0.15) + team(0.15) = 0.45
#   Step 2: affected_system(0.10) + first_response quality(0.20) = 0.30
#   Step 3: resolution_steps(0.15) + sla_hours(0.10) = 0.25
#   Total: 1.0
# ─────────────────────────────────────────────


def grade_resolve_step1(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    score = _EPS

    pred_priority = (action.get("priority") or "").strip().lower()
    if pred_priority == ticket["gt_priority"]:
        score += 0.15
    elif pred_priority in ticket.get("gt_priority_ok", []):
        score += 0.07

    pred_category = (action.get("category") or "").strip().lower()
    if pred_category == ticket["gt_category"]:
        score += 0.15
    elif pred_category in ticket.get("gt_category_ok", []):
        score += 0.07

    pred_team = (action.get("team") or "").strip().lower()
    if pred_team == ticket["gt_team"]:
        score += 0.15
    elif pred_team in ticket.get("gt_team_ok", []):
        score += 0.07

    return _strict(score)


def grade_resolve_step2(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    score = _EPS

    # affected system
    pred_system = (action.get("affected_system") or "").strip().lower()
    gt_system = ticket.get("gt_affected_system", "").lower()
    if gt_system and gt_system in pred_system:
        score += 0.10
    elif pred_system:
        score += 0.05

    # first response quality: keyword coverage
    response = action.get("first_response") or ""
    if len(response) > 30:  # must be a real attempt
        kw_score = _kw_score(response, ticket.get("gt_keywords_response", []))
        score += 0.20 * kw_score

    return _strict(score)


def grade_resolve_step3(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    score = _EPS

    # resolution steps: list with relevant content
    steps = action.get("resolution_steps") or []
    if isinstance(steps, list) and len(steps) >= 2:
        combined = " ".join(steps).lower()
        kw_score = _kw_score(combined, ticket.get("gt_keywords_resolution", []))
        score += 0.15 * min(kw_score * 1.5, 1.0)
    elif isinstance(steps, list) and len(steps) == 1:
        score += 0.05

    # SLA hours
    sla = action.get("sla_hours")
    score += 0.10 * _sla_score(sla, ticket.get("gt_sla_hours", 8))

    return _strict(score)
