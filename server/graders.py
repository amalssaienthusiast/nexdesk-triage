# nexdesk grading logic
# exact matches get the highest score, acceptable alternates get partial credit
# keyword scoring uses simple stemming so "connecting" matches "connection"
# anti-stuffing reduces rewards for keyword dumps with poor sentence structure
# response quality uses a small rubric (empathy + clarity + actionability)

import re
from collections import Counter
from collections.abc import Mapping
from typing import Any, Dict, List, Optional

_EPS = 0.01


def _strict(score: float) -> float:
    # bounds: (0.01, 0.99) — validator requires strictly inside (0, 1)
    return float(round(max(0.01, min(0.99, float(score))), 4))


def _safe_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return ""


def _safe_text_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if hasattr(value, "dict"):
        dumped = value.dict()
        if isinstance(dumped, dict):
            return dumped
    if hasattr(value, "__dict__"):
        return {k: v for k, v in vars(value).items() if not k.startswith("_")}
    return {}


# ── simple stemmer (didn't want to add nltk as a dependency) ──

_SUFFIXES = [
    "ational",
    "tional",
    "enci",
    "anci",
    "izer",
    "isation",
    "ization",
    "ation",
    "ator",
    "alism",
    "iveness",
    "fulness",
    "ousness",
    "aliti",
    "iviti",
    "biliti",
    "ment",
    "ness",
    "ence",
    "ance",
    "able",
    "ible",
    "ting",
    "ing",
    "ied",
    "ies",
    "ive",
    "ful",
    "ous",
    "ism",
    "ist",
    "ity",
    "ed",
    "er",
    "ly",
    "al",
    "es",
    "ic",
]


def _stem(word: str) -> str:
    word = word.lower().strip()
    if len(word) <= 3:
        return word
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _stem_phrase(phrase: str) -> str:
    words = re.findall(r"[a-z0-9]+", phrase.lower())
    return " ".join(_stem(w) for w in words)


# ── anti-keyword-stuffing ──


def _detect_stuffing(text: str, keywords: List[str]) -> float:
    """
    if >50% of the text is just raw keywords with no sentence structure,
    it's probably stuffing — return a penalty factor
    """
    if not text or not keywords:
        return 1.0

    words = text.lower().split()
    if len(words) < 5:
        return 1.0

    stemmed_text = [_stem(w) for w in words]
    stemmed_kw = []
    for k in keywords:
        stemmed_kw.extend(_stem_phrase(k).split())

    kw_count = sum(1 for w in stemmed_text if w in stemmed_kw)
    ratio = kw_count / len(words)

    if ratio > 0.6:
        return 0.3
    if ratio > 0.4:
        return 0.6
    if ratio > 0.3:
        return 0.8
    return 1.0


# ── n-gram overlap (simplified BLEU) ──


def _ngrams(text: str, n: int) -> Counter:
    words = [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower())]
    if len(words) < n:
        return Counter()
    return Counter(tuple(words[i : i + n]) for i in range(len(words) - n + 1))


def _ngram_overlap(hypothesis: str, references: List[str], max_n: int = 3) -> float:
    if not hypothesis or not references:
        return _EPS

    ref_combined = " ".join(references)
    total = 0.0
    count = 0

    for n in range(1, max_n + 1):
        hyp_ng = _ngrams(hypothesis, n)
        ref_ng = _ngrams(ref_combined, n)
        if not hyp_ng or not ref_ng:
            continue

        clipped = Counter()
        for ng, cnt in hyp_ng.items():
            clipped[ng] = min(cnt, ref_ng.get(ng, 0))

        precision = sum(clipped.values()) / max(sum(hyp_ng.values()), 1)
        total += precision
        count += 1

    if count == 0:
        return _EPS
    return max(0.01, min(total / count, 0.99))


# ── response quality rubric ──


def _score_empathy(text: str) -> float:
    if not text or len(text) < 15:
        return _EPS
    markers = [
        "sorry",
        "apologize",
        "apologise",
        "understand",
        "frustrating",
        "appreciate",
        "thank",
        "concern",
        "patience",
        "apologies",
    ]
    hits = sum(1 for m in markers if m in text.lower())
    if hits == 0:
        return 0.1
    return min(hits / 3.0, 0.99)


def _score_clarity(text: str) -> float:
    if not text or len(text) < 15:
        return _EPS
    score = 0.3
    if any(m in text for m in ["1.", "2.", "- ", "•", "\n"]):
        score += 0.2
    wc = len(text.split())
    if 20 <= wc <= 200:
        score += 0.2
    elif 10 <= wc <= 400:
        score += 0.1
    sentences = text.count(".") + text.count("!") + text.count("?")
    if sentences >= 2:
        score += 0.2
    return min(score, 0.99)


def _score_actionability(text: str) -> float:
    if not text or len(text) < 15:
        return _EPS
    markers = [
        "will",
        "going to",
        "let me",
        "i can",
        "we'll",
        "i'll",
        "please",
        "try",
        "check",
        "restart",
        "verify",
        "ensure",
        "contact",
        "reach out",
        "follow up",
        "update",
    ]
    hits = sum(1 for m in markers if m in text.lower())
    if hits == 0:
        return 0.1
    return min(hits / 4.0, 0.99)


def _response_quality(text: str) -> float:
    """combined rubric: empathy 20%, clarity 30%, actionability 50%"""
    text = _safe_text(text)
    if not text or len(text) < 10:
        return _EPS
    e = _score_empathy(text)
    c = _score_clarity(text)
    a = _score_actionability(text)
    return _strict(0.2 * e + 0.3 * c + 0.5 * a)


# ── keyword scoring with stemming ──


def _kw_score(text: str, keywords: List[str]) -> float:
    text = _safe_text(text)
    if not text or not keywords:
        return _EPS

    text_lower = text.lower()
    stemmed_text = _stem_phrase(text)

    hits = 0
    for kw in keywords:
        kw_stemmed = _stem_phrase(kw)
        if kw.lower() in text_lower or kw_stemmed in stemmed_text:
            hits += 1

    raw = hits / max(len(keywords), 1)
    penalty = _detect_stuffing(text, keywords)
    return max(0.01, min(raw * penalty, 0.99))


# ── sla scoring ──


def _sla_score(predicted: Optional[int], expected: int) -> float:
    if predicted is None:
        return _EPS
    try:
        predicted = int(predicted)
        expected = int(expected)
    except (ValueError, TypeError):
        return _EPS
    if expected <= 0:
        return 0.5
    ratio = predicted / expected
    if 0.8 <= ratio <= 1.2:
        return 0.99
    if 0.5 <= ratio <= 2.0:
        return 0.7
    if 0.25 <= ratio <= 4.0:
        return 0.4
    return 0.01


# ── basic field scoring ──


def _priority_score(predicted: str, ground_truth: str, acceptable: List[str]) -> float:
    pred = _safe_text(predicted).strip().lower()
    if not ground_truth:
        return _EPS
    if pred == ground_truth:
        return 0.99
    if pred in acceptable:
        return 0.5
    return _EPS


def _category_score(predicted: str, ground_truth: str, acceptable: List[str]) -> float:
    pred = _safe_text(predicted).strip().lower()
    if not ground_truth:
        return _EPS
    if pred == ground_truth:
        return 0.99
    if pred in acceptable:
        return 0.5
    return _EPS


def _team_score(predicted: str, ground_truth: str, acceptable: List[str]) -> float:
    pred = _safe_text(predicted).strip().lower()
    if not ground_truth:
        return _EPS
    if pred == ground_truth:
        return 0.99
    if pred in acceptable:
        return 0.5
    return _EPS


# ── time and confidence (the interesting stuff) ──


def _compute_time_penalty(elapsed_minutes: float, sla_deadline: int, stress_level: float) -> float:
    """
    penalty ramps up as you approach the SLA deadline
    first 10% of the deadline is a grace period — don't penalize instant responses
    """
    if sla_deadline <= 0:
        return _EPS

    ratio = elapsed_minutes / sla_deadline

    if ratio < 0.1:
        return _EPS  # grace period
    elif ratio < 0.5:
        base = (ratio - 0.1) * 0.1
    elif ratio < 1.0:
        base = 0.04 + (ratio - 0.5) * 0.32
    else:
        base = 0.20 + min((ratio - 1.0) * 0.15, 0.15)

    stress_mult = 1.0 + (stress_level * 0.5)
    return min(base * stress_mult, 0.4)


def _compute_confidence_bonus(confidence: float, accuracy: float) -> float:
    """
    reward calibration (loosely based on Guo et al. 2017 ECE paper)
    well-calibrated = bonus, overconfident = penalty
    """
    if confidence is None:
        return _EPS

    try:
        confidence = float(confidence)
        accuracy = float(accuracy)
    except (ValueError, TypeError):
        return _EPS

    error = abs(confidence - accuracy)

    if error < 0.1:
        return 0.05
    if error < 0.2:
        return 0.02
    if confidence > accuracy + 0.3:
        return -0.08
    if accuracy > confidence + 0.3:
        return -0.03
    return _EPS


def compute_ece(
    confidence_history: List[float], accuracy_history: List[float], n_bins: int = 5
) -> float:
    """expected calibration error — lower is better"""
    if not confidence_history or len(confidence_history) != len(accuracy_history):
        return 0.5

    bins = [i / n_bins for i in range(n_bins + 1)]
    ece = 0.01
    total = len(confidence_history)

    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        indices = [
            j
            for j, c in enumerate(confidence_history)
            if lo <= c < hi or (i == n_bins - 1 and c == hi)
        ]
        if not indices:
            continue
        bsize = len(indices)
        avg_conf = sum(confidence_history[j] for j in indices) / bsize
        avg_acc = sum(accuracy_history[j] for j in indices) / bsize
        ece += (bsize / total) * abs(avg_conf - avg_acc)

    return max(0.01, min(0.99, ece))


# ── score breakdown for the info dict ──


def get_score_breakdown(
    task: str, step: int, action: Dict[str, Any], ticket: Dict[str, Any]
) -> Dict[str, float]:
    action = _as_dict(action)
    ticket = _as_dict(ticket)
    bd = {}

    pp = _safe_text(action.get("priority")).strip().lower()
    if pp:
        bd["priority"] = round(
            _priority_score(pp, ticket.get("gt_priority", ""), ticket.get("gt_priority_ok", [])), 4
        )

    pc = _safe_text(action.get("category")).strip().lower()
    if pc:
        bd["category"] = round(
            _category_score(pc, ticket.get("gt_category", ""), ticket.get("gt_category_ok", [])), 4
        )

    pt = _safe_text(action.get("team")).strip().lower()
    if pt:
        bd["team"] = round(
            _team_score(pt, ticket.get("gt_team", ""), ticket.get("gt_team_ok", [])), 4
        )

    ps = _safe_text(action.get("affected_system")).strip().lower()
    gt_s = ticket.get("gt_affected_system", "").lower()
    if ps:
        if gt_s and (gt_s in ps or ps in gt_s):
            bd["affected_system"] = 0.99
        else:
            bd["affected_system"] = 0.15

    resp = _safe_text(action.get("first_response"))
    if resp and len(resp) > 10:
        kw = _kw_score(resp, ticket.get("gt_keywords_response", []))
        rq = _response_quality(resp)
        bd["response_quality"] = round(0.5 * kw + 0.5 * rq, 4)

    steps_list = _safe_text_list(action.get("resolution_steps"))
    if steps_list:
        combined = " ".join(str(s) for s in steps_list)
        kw = _kw_score(combined, ticket.get("gt_keywords_resolution", []))
        ng = _ngram_overlap(combined, ticket.get("gt_keywords_resolution", []))
        bd["resolution_quality"] = round(0.6 * kw + 0.4 * ng, 4)

    sla = action.get("sla_hours")
    if sla is not None:
        bd["sla_accuracy"] = round(_sla_score(sla, ticket.get("gt_sla_hours", 8)), 4)

    return bd


# ── task 1: classify ──


def grade_classify(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    try:
        action = _as_dict(action)
        ticket = _as_dict(ticket)
        score = _EPS

        pp = _safe_text(action.get("priority")).strip().lower()
        gt_p = ticket.get("gt_priority", "")
        if gt_p and pp == gt_p:
            score += 0.5
        elif gt_p and pp in ticket.get("gt_priority_ok", []):
            score += 0.25

        pc = _safe_text(action.get("category")).strip().lower()
        gt_c = ticket.get("gt_category", "")
        if gt_c and pc == gt_c:
            score += 0.5
        elif gt_c and pc in ticket.get("gt_category_ok", []):
            score += 0.25

        return _strict(score)
    except Exception:
        return _EPS


# ── task 2: route ──


def grade_route_step1(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    try:
        action = _as_dict(action)
        ticket = _as_dict(ticket)
        score = _EPS

        pp = _safe_text(action.get("priority")).strip().lower()
        gt_p = ticket.get("gt_priority", "")
        if gt_p and pp == gt_p:
            score += 0.25
        elif gt_p and pp in ticket.get("gt_priority_ok", []):
            score += 0.12

        pc = _safe_text(action.get("category")).strip().lower()
        gt_c = ticket.get("gt_category", "")
        if gt_c and pc == gt_c:
            score += 0.25
        elif gt_c and pc in ticket.get("gt_category_ok", []):
            score += 0.12

        pt = _safe_text(action.get("team")).strip().lower()
        gt_t = ticket.get("gt_team", "")
        if gt_t and pt == gt_t:
            score += 0.30
        elif gt_t and pt in ticket.get("gt_team_ok", []):
            score += 0.15

        return _strict(score)
    except Exception:
        return _EPS


def grade_route_step2(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    try:
        action = _as_dict(action)
        ticket = _as_dict(ticket)
        ps = _safe_text(action.get("affected_system")).strip().lower()
        gt_s = _safe_text(ticket.get("gt_affected_system")).lower()
        if gt_s and (gt_s in ps or ps in gt_s):
            return _strict(0.15)
        if ps:
            return _strict(0.07)
        return _strict(_EPS)
    except Exception:
        return _EPS


# ── task 3: resolve ──


def grade_resolve_step1(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    try:
        action = _as_dict(action)
        ticket = _as_dict(ticket)
        score = _EPS

        pp = _safe_text(action.get("priority")).strip().lower()
        gt_p = ticket.get("gt_priority", "")
        if gt_p and pp == gt_p:
            score += 0.12
        elif gt_p and pp in ticket.get("gt_priority_ok", []):
            score += 0.06

        pc = _safe_text(action.get("category")).strip().lower()
        gt_c = ticket.get("gt_category", "")
        if gt_c and pc == gt_c:
            score += 0.13
        elif gt_c and pc in ticket.get("gt_category_ok", []):
            score += 0.06

        pt = _safe_text(action.get("team")).strip().lower()
        gt_t = ticket.get("gt_team", "")
        if gt_t and pt == gt_t:
            score += 0.15
        elif gt_t and pt in ticket.get("gt_team_ok", []):
            score += 0.07

        return _strict(score)
    except Exception:
        return _EPS


def grade_resolve_step2(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    try:
        action = _as_dict(action)
        ticket = _as_dict(ticket)
        score = _EPS

        ps = _safe_text(action.get("affected_system")).strip().lower()
        gt_s = _safe_text(ticket.get("gt_affected_system")).lower()
        if gt_s and (gt_s in ps or ps in gt_s):
            score += 0.10
        elif ps:
            score += 0.05

        resp = _safe_text(action.get("first_response"))
        if len(resp) > 10:
            kw = _kw_score(resp, ticket.get("gt_keywords_response", []))
            rq = _response_quality(resp)
            score += 0.20 * min(0.5 * kw + 0.5 * rq, 0.99)

        return _strict(score)
    except Exception:
        return _EPS


def grade_resolve_step3(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    try:
        action = _as_dict(action)
        ticket = _as_dict(ticket)
        score = _EPS

        steps = _safe_text_list(action.get("resolution_steps"))
        if len(steps) >= 2:
            combined = " ".join(str(s) for s in steps)
            kw = _kw_score(combined, ticket.get("gt_keywords_resolution", []))
            ng = _ngram_overlap(combined, ticket.get("gt_keywords_resolution", []))
            combined_score = 0.6 * kw + 0.4 * ng
            score += 0.15 * min(combined_score * 1.5, 0.99)
        elif len(steps) == 1:
            score += 0.05

        sla = action.get("sla_hours")
        score += 0.10 * _sla_score(sla, ticket.get("gt_sla_hours", 8))

        return _strict(score)
    except Exception:
        return _EPS


# ── task 4: crisis ──


def grade_crisis_ticket(action: Dict[str, Any], ticket: Dict[str, Any], step: int) -> float:
    try:
        action = _as_dict(action)
        ticket = _as_dict(ticket)
        score = _EPS

        pp = _safe_text(action.get("priority")).strip().lower()
        gt_p = ticket.get("gt_priority", "")
        if gt_p and pp == gt_p:
            score += 0.04  # exact match
        elif gt_p and pp in ticket.get("gt_priority_ok", []):
            score += 0.02  # acceptable alternative

        pc = _safe_text(action.get("category")).strip().lower()
        gt_c = ticket.get("gt_category", "")
        if gt_c and pc == gt_c:
            score += 0.03  # exact match
        elif gt_c and pc in ticket.get("gt_category_ok", []):
            score += 0.01  # acceptable alternative

        pt = _safe_text(action.get("team")).strip().lower()
        gt_t = ticket.get("gt_team", "")
        if gt_t and pt == gt_t:
            score += 0.04  # exact match
        elif gt_t and pt in ticket.get("gt_team_ok", []):
            score += 0.02  # acceptable alternative

        # bonus for handling critical tickets in first 3 steps (crisis priority)
        if step <= 3 and gt_p == "critical":
            score += 0.02
        if 4 <= step <= 6 and gt_p == "high":
            score += 0.01

        return _strict(score)
    except Exception:
        return _EPS


def grade_route(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    """
    Single-call compatibility grader for the route task.

    Combines the 2-step task into one deterministic score. Denominators are
    the empirical maximums of each step grader:
      step1 max = 0.01 + 0.25 + 0.25 + 0.30 = 0.81
      step2 max = 0.15  (exact affected_system match)
    """
    try:
        action = _as_dict(action)
        ticket = _as_dict(ticket)
        step1 = grade_route_step1(action, ticket)
        step2 = grade_route_step2(action, ticket)
        return _strict(0.84 * (step1 / 0.81) + 0.16 * (step2 / 0.15))
    except Exception:
        return _EPS


def grade_resolve(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    """
    Single-call compatibility grader for the resolve task.

    Combines the three environment steps into one deterministic score.
    Denominators are the empirical maximums of each step grader:
      step1 max = 0.41  (priority 0.12 + category 0.13 + team 0.15 + base 0.01)
      step2 max = 0.31  (affected_system 0.10 + response_quality 0.20 + base 0.01)
      step3 max = 0.26  (resolution_steps 0.15 + sla 0.10 + base 0.01)
    """
    try:
        action = _as_dict(action)
        ticket = _as_dict(ticket)
        step1 = grade_resolve_step1(action, ticket)
        step2 = grade_resolve_step2(action, ticket)
        step3 = grade_resolve_step3(action, ticket)
        return _strict(0.42 * (step1 / 0.41) + 0.32 * (step2 / 0.31) + 0.26 * (step3 / 0.26))
    except Exception:
        return _EPS


def grade_crisis(action: Dict[str, Any], ticket: Dict[str, Any]) -> float:
    """
    Single-call compatibility grader for the crisis task.

    Uses the per-ticket crisis grader at the first step so the standalone
    task-level grader stays deterministic and aligned with runtime behavior.
    """
    try:
        action = _as_dict(action)
        ticket = _as_dict(ticket)
        return grade_crisis_ticket(action, ticket, step=1)
    except Exception:
        return _EPS


# ── episode rollup ──


def grade_full_episode(
    task: str, rewards: List[float], metadata: Optional[Dict] = None
) -> Dict[str, Any]:
    try:
        rewards = list(rewards or [])
        metadata = _as_dict(metadata)
        total = sum(float(r) for r in rewards) if rewards else _EPS
        result = {
            "total_score": _strict(total),
            "step_rewards": [_strict(float(r)) for r in rewards],
            "num_steps": len(rewards),
            "avg_step_reward": _strict(total / len(rewards)) if rewards else _EPS,
        }
        if metadata:
            if "time_penalties" in metadata:
                result["total_time_penalty"] = _strict(
                    sum(float(v) for v in metadata["time_penalties"])
                )
            if "confidence_bonuses" in metadata:
                result["total_confidence_bonus"] = _strict(
                    sum(float(v) for v in metadata["confidence_bonuses"])
                )
            if "sla_breaches" in metadata:
                result["sla_breaches"] = int(metadata["sla_breaches"])
            if "confidence_history" in metadata and "accuracy_history" in metadata:
                result["ece"] = _strict(
                    compute_ece(
                        list(metadata["confidence_history"]), list(metadata["accuracy_history"])
                    )
                )
        return result
    except Exception:
        return {
            "total_score": _EPS,
            "step_rewards": [],
            "num_steps": 0,
            "avg_step_reward": _EPS,
        }
