import json

graders_script = """\"\"\"
NexDesk Graders - Complete with all advanced features
Each grader returns a float strictly in (0.01, 0.99) for Phase 2 compliance.
All graders are deterministic given the same input.

Features:
- Multi-dimensional scoring
- Confidence calibration bonus/penalty  
- Time pressure penalty
- Crisis mode grading with prioritization bonuses
\"\"\"

from typing import Any, Dict, Optional, List

_EPS = 0.01


def _strict(score: float) -> float:
    \"\"\"Clamp score to strictly open interval (0, 1) - Phase 2 requirement.\"\"\"
    return float(round(max(_EPS, min(0.99, float(score))), 4))


# ─────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────


def _kw_score(text: str, keywords: List[str]) -> float:
    \"\"\"Score based on how many keywords appear in text (case-insensitive).\"\"\"
    if not text or not keywords:
        return _EPS
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    return max(_EPS, min(hits / max(len(keywords) * 0.4, 1), 0.99))


def _sla_score(predicted: Optional[int], expected: int) -> float:
    \"\"\"Score SLA estimate. Exact = 0.99, within 2x = 0.7, within 4x = 0.4, beyond = 0.05\"\"\"
    if predicted is None:
        return _EPS
    ratio = predicted / expected if expected > 0 else 1.0
    if 0.8 <= ratio <= 1.2:
        return 0.99
    if 0.5 <= ratio <= 2.0:
        return 0.7
    if 0.25 <= ratio <= 4.0:
        return 0.4
    return 0.05


def _priority_score(predicted: str, ground_truth: str, acceptable: List[str]) -> float:
    \"\"\"Score priority prediction.\"\"\"
    pred = (predicted or "").strip().lower()
    if pred == ground_truth:
        return 1.0
    if pred in acceptable:
        return 0.5
    return 0.0


def _category_score(predicted: str, ground_truth: str, acceptable: List[str]) -> float:
    \"\"\"Score category prediction.\"\"\"
    pred = (predicted or "").strip().lower()
    if pred == ground_truth:
        return 1.0
    if pred in acceptable:
        return 0.5
    return 0.0


def _team_score(predicted: str, ground_truth: str, acceptable: List[str]) -> float:
    \"\"\"Score team assignment.\"\"\"
    pred = (predicted or "").strip().lower()
    if pred == ground_truth:
        return 1.0
    if pred in acceptable:
        return 0.5
    return 0.0


# ─────────────────────────────────────────────
# Time Pressure & Confidence (Advanced Features)
# ─────────────────────────────────────────────


def compute_time_penalty(elapsed_minutes: float, sla_deadline: int, stress_level: float) -> float:
    \"\"\"
    Compute penalty for time pressure.
    - No penalty if under 50% of SLA
    - Linear penalty from 50% to 100%
    - Max 35% penalty + stress multiplier
    \"\"\"
    if sla_deadline <= 0:
        return 0.0

    ratio = elapsed_minutes / sla_deadline

    if ratio < 0.5:
        return 0.0
    elif ratio < 1.0:
        base_penalty = (ratio - 0.5) * 0.4  # 0 to 0.2
    else:
        base_penalty = 0.2 + min((ratio - 1.0) * 0.15, 0.15)  # max 0.35

    stress_multiplier = 1.0 + (stress_level * 0.5)
    return min(base_penalty * stress_multiplier, 0.4)


def compute_confidence_bonus(confidence: float, accuracy: float) -> float:
    \"\"\"
    Compute bonus/penalty for confidence calibration.
    Well-calibrated agents (confidence ≈ accuracy) get bonus.
    Overconfident wrong answers get penalty.
    \"\"\"
    if confidence is None:
        return 0.0

    error = abs(confidence - accuracy)

    if error < 0.1:
        return 0.05  # 5% bonus for well-calibrated
    if confidence > accuracy + 0.3:
        return -0.08  # 8% penalty for overconfidence
    if accuracy > confidence + 0.3:
        return -0.03  # 3% penalty for underconfidence
    return 0.0


# ─────────────────────────────────────────────
# Multi-Dimensional Score Breakdown
# ─────────────────────────────────────────────


def get_score_breakdown(
    task: str, step: int, action: Dict[str, Any], ticket: Dict[str, Any]
) -> Dict[str, float]:
    \"\"\"Return detailed score breakdown by dimension for analysis.\"\"\"
    breakdown = {}

    pred_priority = (action.get("priority") or "").strip().lower()
    if pred_priority:
        breakdown["priority"] = round(
            _priority_score(pred_priority, ticket.get("gt_priority", ""), ticket.get("gt_priority_ok", [])), 4
        )

    pred_category = (action.get("category") or "").strip().lower()
    if pred_category:
        breakdown["category"] = round(
            _category_score(pred_category, ticket.get("gt_category", ""), ticket.get("gt_category_ok", [])), 4
        )

    pred_team = (action.get("team") or "").strip().lower()
    if pred_team:
        breakdown["team"] = round(
            _team_score(pred_team, ticket.get("gt_team", ""), ticket.get("gt_team_ok", [])), 4
        )

    pred_system = (action.get("affected_system") or "").strip().lower()
    gt_system = ticket.get("gt_affected_system", "").lower()
    if pred_system:
        if gt_system and gt_system in pred_system:
            breakdown["affected_system"] = 1.0
        else:
            breakdown["affected_system"] = 0.5

    response = action.get("first_response") or ""
    if response and len(response) > 30:
        breakdown["response_quality"] = round(_kw_score(response, ticket.get("gt_keywords_response", [])), 4)

    steps_list = action.get("resolution_steps") or []
    if isinstance(steps_list, list) and steps_list:
        combined = " ".join(steps_list).lower()
        breakdown["resolution_quality"] = round(_kw_score(combined, ticket.get("gt_keywords_resolution", [])), 4)

    sla = action.get("sla_hours")
    if sla is not None:
        breakdown["sla_accuracy"] = round(_sla_score(sla, ticket.get("gt_sla_hours", 8)), 4)

    return breakdown


# ─────────────────────────────────────────────
# Task 1: ticket_classify (easy)
# Max score: 0.99 (strict)
# Components: priority (0.5) + category (0.5)
# ─────────────────────────────────────────────


def grade_classify(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    score = _EPS

    pred_priority = (action.get("priority") or "").strip().lower()
    if pred_priority == ticket.get("gt_priority", ""):
        score += 0.5
    elif pred_priority in ticket.get("gt_priority_ok", []):
        score += 0.25

    pred_category = (action.get("category") or "").strip().lower()
    if pred_category == ticket.get("gt_category", ""):
        score += 0.5
    elif pred_category in ticket.get("gt_category_ok", []):
        score += 0.25

    return _strict(score)


# ─────────────────────────────────────────────
# Task 2: ticket_route (medium)
# Max score per step:
#   Step 1: priority(0.25) + category(0.25) + team(0.35) = 0.85
#   Step 2: affected_system(0.15) → total 0.99
# ─────────────────────────────────────────────


def grade_route_step1(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    score = _EPS

    pred_priority = (action.get("priority") or "").strip().lower()
    if pred_priority == ticket.get("gt_priority", ""):
        score += 0.25
    elif pred_priority in ticket.get("gt_priority_ok", []):
        score += 0.12

    pred_category = (action.get("category") or "").strip().lower()
    if pred_category == ticket.get("gt_category", ""):
        score += 0.25
    elif pred_category in ticket.get("gt_category_ok", []):
        score += 0.12

    pred_team = (action.get("team") or "").strip().lower()
    if pred_team == ticket.get("gt_team", ""):
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
    return _strict(_EPS)


# ─────────────────────────────────────────────
# Task 3: ticket_resolve (hard)
# Max score per step:
#   Step 1: priority(0.15) + category(0.15) + team(0.15) = 0.45
#   Step 2: affected_system(0.10) + first_response(0.20) = 0.30
#   Step 3: resolution_steps(0.15) + sla_hours(0.10) = 0.25
#   Total: 0.99
# ─────────────────────────────────────────────


def grade_resolve_step1(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    score = _EPS

    pred_priority = (action.get("priority") or "").strip().lower()
    if pred_priority == ticket.get("gt_priority", ""):
        score += 0.15
    elif pred_priority in ticket.get("gt_priority_ok", []):
        score += 0.07

    pred_category = (action.get("category") or "").strip().lower()
    if pred_category == ticket.get("gt_category", ""):
        score += 0.15
    elif pred_category in ticket.get("gt_category_ok", []):
        score += 0.07

    pred_team = (action.get("team") or "").strip().lower()
    if pred_team == ticket.get("gt_team", ""):
        score += 0.15
    elif pred_team in ticket.get("gt_team_ok", []):
        score += 0.07

    return _strict(score)


def grade_resolve_step2(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    score = _EPS

    pred_system = (action.get("affected_system") or "").strip().lower()
    gt_system = ticket.get("gt_affected_system", "").lower()
    if gt_system and gt_system in pred_system:
        score += 0.10
    elif pred_system:
        score += 0.05

    response = action.get("first_response") or ""
    if len(response) > 30:
        kw_score = _kw_score(response, ticket.get("gt_keywords_response", []))
        score += 0.20 * kw_score

    return _strict(score)


def grade_resolve_step3(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    score = _EPS

    steps = action.get("resolution_steps") or []
    if isinstance(steps, list) and len(steps) >= 2:
        combined = " ".join(steps).lower()
        kw_score = _kw_score(combined, ticket.get("gt_keywords_resolution", []))
        score += 0.15 * min(kw_score * 1.5, 1.0)
    elif isinstance(steps, list) and len(steps) == 1:
        score += 0.05

    sla = action.get("sla_hours")
    score += 0.10 * _sla_score(sla, ticket.get("gt_sla_hours", 8))

    return _strict(score)


# ─────────────────────────────────────────────
# Task 4: crisis_surge (hard, batch)
# Each ticket graded on classification + routing
# Max score per ticket: 0.10 (10 tickets = 1.0 total)
# Bonus for correct prioritization order
# ─────────────────────────────────────────────


def grade_crisis_ticket(action: Dict[str, Any], ticket: Dict[str, Any], step: int) -> float:
    \"\"\"Grade a single ticket in crisis surge mode with prioritization bonuses.\"\"\"
    score = _EPS

    pred_priority = (action.get("priority") or "").strip().lower()
    if pred_priority == ticket.get("gt_priority", ""):
        score += 0.03
    elif pred_priority in ticket.get("gt_priority_ok", []):
        score += 0.015

    pred_category = (action.get("category") or "").strip().lower()
    if pred_category == ticket.get("gt_category", ""):
        score += 0.03
    elif pred_category in ticket.get("gt_category_ok", []):
        score += 0.015

    pred_team = (action.get("team") or "").strip().lower()
    if pred_team == ticket.get("gt_team", ""):
        score += 0.04
    elif pred_team in ticket.get("gt_team_ok", []):
        score += 0.02

    # Bonus for handling critical tickets first (steps 1-3)
    if step <= 3 and ticket.get("gt_priority", "") == "critical":
        score += 0.01

    # Bonus for handling high priority in steps 4-6
    if 4 <= step <= 6 and ticket.get("gt_priority", "") == "high":
        score += 0.005

    return _strict(score)


# ─────────────────────────────────────────────
# Aggregate Grading Functions
# ─────────────────────────────────────────────


def grade_full_episode(
    task: str, rewards: List[float], metadata: Optional[Dict] = None
) -> Dict[str, Any]:
    \"\"\"Compute comprehensive episode metrics.\"\"\"
    total = sum(rewards)

    result = {
        "total_score": round(total, 4),
        "step_rewards": [round(r, 4) for r in rewards],
        "num_steps": len(rewards),
        "avg_step_reward": round(total / len(rewards), 4) if rewards else _EPS,
    }

    if metadata:
        if "time_penalties" in metadata:
            result["total_time_penalty"] = round(sum(metadata["time_penalties"]), 4)
        if "confidence_bonuses" in metadata:
            result["total_confidence_bonus"] = round(sum(metadata["confidence_bonuses"]), 4)
        if "sla_breaches" in metadata:
            result["sla_breaches"] = metadata["sla_breaches"]

    return result
"""

with open("server/graders.py", "w") as f:
    f.write(graders_script)
