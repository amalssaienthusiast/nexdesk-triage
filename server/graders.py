# nexdesk graders
# keeping all these strictly clamped so the hackathon validator doesn't fail us
# adding some time constraints and confidence bonuses to make it realistic

from typing import Any, Dict, Optional, List

_EPS = 0.01


def _strict(score: float) -> float:
    # strictly clamp to avoid 0.0 or 1.0 validator crashes
    return float(round(max(_EPS, min(0.99, float(score))), 2))


# helpers


def _kw_score(text: str, keywords: List[str]) -> float:
    # basic keyword matching for response payloads
    if not text or not keywords:
        return _EPS
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    return max(_EPS, min(hits / max(len(keywords) * 0.4, 1), 0.99))


def _sla_score(predicted: Optional[int], expected: int) -> float:
    # simple tier system for sla estimates
    if predicted is None:
        return _EPS
    ratio = predicted / expected if expected > 0 else 0.99
    if 0.8 <= ratio <= 1.2:
        return 0.99
    if 0.5 <= ratio <= 2.0:
        return 0.7
    if 0.25 <= ratio <= 4.0:
        return 0.4
    return 0.05


def _priority_score(predicted: str, ground_truth: str, acceptable: List[str]) -> float:
    # basic priority check
    pred = (predicted or "").strip().lower()
    if pred == ground_truth:
        return 0.99
    if pred in acceptable:
        return 0.5
    return _EPS


def _category_score(predicted: str, ground_truth: str, acceptable: List[str]) -> float:
    # basic category check
    pred = (predicted or "").strip().lower()
    if pred == ground_truth:
        return 0.99
    if pred in acceptable:
        return 0.5
    return _EPS


def _team_score(predicted: str, ground_truth: str, acceptable: List[str]) -> float:
    # basic team routing check
    pred = (predicted or "").strip().lower()
    if pred == ground_truth:
        return 0.99
    if pred in acceptable:
        return 0.5
    return _EPS


# core time and confidence math
# spent a while tuning these numbers to feel fair but punishing


def compute_time_penalty(elapsed_minutes: float, sla_deadline: int, stress_level: float) -> float:
    # scales penalty based on how close we are to blowing the SLA deadline
    if sla_deadline <= 0:
        return _EPS

    ratio = elapsed_minutes / sla_deadline

    if ratio < 0.5:
        return _EPS
    elif ratio < 1.0:
        base_penalty = (ratio - 0.5) * 0.4  # 0 to 0.2
    else:
        base_penalty = 0.2 + min((ratio - 1.0) * 0.15, 0.15)  # max 0.35

    stress_multiplier = 1.0 + (stress_level * 0.5)
    return min(base_penalty * stress_multiplier, 0.4)


def compute_confidence_bonus(confidence: float, accuracy: float) -> float:
    # give them a bonus if they know they are right, punish if they are hopelessly overconfident
    if confidence is None:
        return _EPS

    error = abs(confidence - accuracy)

    if error < 0.1:
        return 0.05  # 5% bonus for well-calibrated
    if confidence > accuracy + 0.3:
        return -0.08  # 8% penalty for overconfidence
    if accuracy > confidence + 0.3:
        return -0.03  # 3% penalty for underconfidence
    return _EPS


# breakdowns for the UI/eval metrics


def get_score_breakdown(
    task: str, step: int, action: Dict[str, Any], ticket: Dict[str, Any]
) -> Dict[str, float]:
    # slices the final score into readable chunks
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
            breakdown["affected_system"] = 0.99
        else:
            breakdown["affected_system"] = 0.25

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


# task 1: classify


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


# task 2: routing


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
        score += 0.30
    elif pred_team in ticket.get("gt_team_ok", []):
        score += 0.15

    return _strict(score)


def grade_route_step2(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    pred_system = (action.get("affected_system") or "").strip().lower()
    gt_system = ticket.get("gt_affected_system", "").lower()
    if gt_system and gt_system in pred_system:
        return _strict(0.15)
    if pred_system:
        return _strict(0.07)
    return _strict(_EPS)


# task 3: full resolve


def grade_resolve_step1(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    score = _EPS

    pred_priority = (action.get("priority") or "").strip().lower()
    if pred_priority == ticket.get("gt_priority", ""):
        score += 0.12
    elif pred_priority in ticket.get("gt_priority_ok", []):
        score += 0.06

    pred_category = (action.get("category") or "").strip().lower()
    if pred_category == ticket.get("gt_category", ""):
        score += 0.13
    elif pred_category in ticket.get("gt_category_ok", []):
        score += 0.06

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
        score += 0.15 * min(kw_score * 1.5, 0.99)
    elif isinstance(steps, list) and len(steps) == 1:
        score += 0.05

    sla = action.get("sla_hours")
    score += 0.10 * _sla_score(sla, ticket.get("gt_sla_hours", 8))

    return _strict(score)


# task 4: crisis mode


def grade_crisis_ticket(action: Dict[str, Any], ticket: Dict[str, Any], step: int) -> float:
    # bonus if they actually triage the critical stuff first
    score = _EPS

    pred_priority = (action.get("priority") or "").strip().lower()
    if pred_priority == ticket.get("gt_priority", ""):
        score += 0.02
    elif pred_priority in ticket.get("gt_priority_ok", []):
        score += 0.01

    pred_category = (action.get("category") or "").strip().lower()
    if pred_category == ticket.get("gt_category", ""):
        score += 0.02
    elif pred_category in ticket.get("gt_category_ok", []):
        score += 0.01

    pred_team = (action.get("team") or "").strip().lower()
    if pred_team == ticket.get("gt_team", ""):
        score += 0.03
    elif pred_team in ticket.get("gt_team_ok", []):
        score += 0.015

    # Bonus for handling critical tickets first (steps 1-3)
    if step <= 3 and ticket.get("gt_priority", "") == "critical":
        score += 0.01

    # Bonus for handling high priority in steps 4-6
    if 4 <= step <= 6 and ticket.get("gt_priority", "") == "high":
        score += 0.005

    return _strict(score)


# rollups


def grade_full_episode(
    task: str, rewards: List[float], metadata: Optional[Dict] = None
) -> Dict[str, Any]:
    # stitch the episode metrics together
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
