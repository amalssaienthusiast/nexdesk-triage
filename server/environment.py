"""
NexDesk Environment — Core Logic with Advanced Features
Handles session management, time pressure, confidence calibration, crisis surge, and business metrics.

Advanced Features:
- Time pressure penalty with SLA deadlines
- Confidence calibration bonus/penalty
- Multi-dimensional score breakdown
- Crisis surge batch processing
- Business metrics tracking
"""

import logging
import random
import time
import uuid
from typing import Any, Dict, List, Optional

from .graders import (
    grade_classify,
    grade_route_step1,
    grade_route_step2,
    grade_resolve_step1,
    grade_resolve_step2,
    grade_resolve_step3,
    grade_crisis_ticket,
    compute_confidence_bonus,
    compute_time_penalty,
    get_score_breakdown,
)
from .tickets import TICKETS
from .metrics import BusinessMetrics

logger = logging.getLogger(__name__)

_EPS = 0.01


def _strict_clamp(score: float) -> float:
    """Clamp score to strictly open interval (0, 1) — Phase 2 requirement."""
    return float(round(max(_EPS, min(0.99, float(score))), 4))


# Task configurations with max rewards per step
TASK_CONFIGS = {
    "ticket_classify": {
        "max_steps": 1,
        "description": "Classify ticket priority and category.",
        "required_fields": ["priority", "category"],
        "difficulty": "easy",
        "base_sla_minutes": 60,
        "max_reward_per_step": {1: 0.99},
    },
    "ticket_route": {
        "max_steps": 2,
        "description": "Step 1: Classify and route to team. Step 2: Identify affected system.",
        "required_fields": ["priority", "category", "team", "affected_system"],
        "difficulty": "medium",
        "base_sla_minutes": 30,
        "max_reward_per_step": {1: 0.85, 2: 0.15},
    },
    "ticket_resolve": {
        "max_steps": 3,
        "description": "Step 1: Classify and assign. Step 2: Respond to user. Step 3: Resolution steps and SLA.",
        "required_fields": [
            "priority",
            "category",
            "team",
            "affected_system",
            "first_response",
            "resolution_steps",
            "sla_hours",
        ],
        "difficulty": "hard",
        "base_sla_minutes": 20,
        "max_reward_per_step": {1: 0.45, 2: 0.30, 3: 0.25},
    },
    "crisis_surge": {
        "max_steps": 10,
        "description": "CRISIS MODE: Triage 10 tickets under time pressure.",
        "required_fields": ["priority", "category", "team"],
        "difficulty": "hard",
        "base_sla_minutes": 5,
        "is_batch": True,
        "max_reward_per_step": {i: 0.12 for i in range(1, 11)},
    },
}

# Organizational context for richer observations
ORG_CONTEXT = {
    "total_employees": 500,
    "departments": [
        "Engineering",
        "Sales",
        "Marketing",
        "Finance",
        "HR",
        "Legal",
        "Operations",
        "Design",
        "IT Security",
    ],
    "teams": {
        "helpdesk": {"capacity": 10, "avg_response_time": "2h"},
        "network-ops": {"capacity": 4, "avg_response_time": "4h"},
        "sysadmin": {"capacity": 6, "avg_response_time": "3h"},
        "security": {"capacity": 3, "avg_response_time": "1h"},
        "dev": {"capacity": 8, "avg_response_time": "6h"},
    },
    "current_oncall": "network-ops",
    "recent_incidents": ["database-slowness", "vpn-issues"],
}


class NexDeskEnv:
    """NexDesk IT Ticket Triage Environment with advanced features."""

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._metrics = BusinessMetrics()
        self._session_timeout_seconds = 3600
        logger.info("NexDesk environment initialized with advanced features")

    def reset(self, task: Optional[str] = None) -> Dict[str, Any]:
        """Start a new episode for the given task."""
        self._cleanup_expired_sessions()

        task = (task or "ticket_classify").strip().lower()
        if task not in TASK_CONFIGS:
            raise ValueError(f"Unknown task: '{task}'. Choose from: {', '.join(TASK_CONFIGS.keys())}")

        cfg = TASK_CONFIGS[task]

        # Select tickets for this episode
        if cfg.get("is_batch"):
            num_tickets = min(cfg["max_steps"], len(TICKETS))
            tickets = random.sample(TICKETS, k=num_tickets)
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            tickets = sorted(tickets, key=lambda t: priority_order.get(t.get("gt_priority", "medium"), 2))
            current_ticket = tickets[0]
        else:
            tickets = [random.choice(TICKETS)]
            current_ticket = tickets[0]

        queue_depth = random.randint(5, 25)
        stress_level = min(queue_depth / 30.0, 0.99)

        # Adjust SLA based on priority
        base_sla = cfg.get("base_sla_minutes", 60)
        gt_priority = current_ticket.get("gt_priority", "medium")
        if gt_priority == "critical":
            base_sla = max(1, base_sla // 2)
        elif gt_priority == "high":
            base_sla = max(1, int(base_sla * 0.75))

        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {
            "session_id": session_id,
            "task": task,
            "tickets": tickets,
            "current_ticket_idx": 0,
            "ticket": current_ticket,
            "step": 0,
            "max_steps": cfg["max_steps"],
            "done": False,
            "total_reward": 0.0,
            "rewards": [],
            "accumulated": {},
            "start_time": time.time(),
            "last_activity": time.time(),
            "sla_deadline_minutes": base_sla,
            "queue_depth": queue_depth,
            "stress_level": stress_level,
            "confidence_history": [],
            "accuracy_history": [],
            "tickets_resolved": 0,
            "escalations": 0,
            "sla_breaches": 0,
        }

        logger.info(f"Reset: task={task}, session_id={session_id}")
        return {"observation": self._build_observation(session_id, _EPS), "session_id": session_id}

    def step(self, session_id: str, action: Dict[str, Any]) -> Dict[str, Any]:
        """Take a step in the environment with time pressure and confidence calibration."""
        if not session_id or not isinstance(session_id, str):
            raise ValueError("session_id is required")
        if session_id not in self._sessions:
            raise ValueError(f"Unknown session_id: '{session_id}'. Call reset() first.")

        sess = self._sessions[session_id]
        if sess["done"]:
            raise ValueError("Episode already done. Call reset() to start a new one.")

        sess["last_activity"] = time.time()
        sess["step"] += 1
        step = sess["step"]
        task = sess["task"]
        ticket = sess["ticket"]
        cfg = TASK_CONFIGS[task]

        # Merge action into accumulated state
        if action and isinstance(action, dict):
            for k, v in action.items():
                if v is not None:
                    sess["accumulated"][k] = v
        merged = sess["accumulated"]

        # Compute base reward
        try:
            base_reward = self._compute_reward(task, step, merged, ticket)
        except Exception as e:
            logger.error(f"Reward computation error: {e}")
            base_reward = _EPS

        # Apply time penalty (advanced feature)
        elapsed_minutes = (time.time() - sess["start_time"]) / 60.0
        try:
            time_penalty = compute_time_penalty(
                elapsed_minutes, sess["sla_deadline_minutes"], sess["stress_level"]
            )
        except Exception as e:
            logger.error(f"Time penalty error: {e}")
            time_penalty = 0.0

        # Apply confidence calibration bonus/penalty (advanced feature)
        confidence = action.get("confidence") if action else None
        confidence_bonus = 0.0
        normalized_accuracy = 0.0

        if confidence is not None and isinstance(confidence, (int, float)):
            try:
                max_reward_for_step = cfg.get("max_reward_per_step", {}).get(step, 1.0)
                normalized_accuracy = base_reward / max_reward_for_step if max_reward_for_step > 0 else 0.0
                confidence_bonus = compute_confidence_bonus(confidence, normalized_accuracy)
                sess["confidence_history"].append(float(confidence))
                sess["accuracy_history"].append(normalized_accuracy)
            except Exception as e:
                logger.error(f"Confidence bonus error: {e}")
                confidence_bonus = 0.0

        # Final reward calculation with penalties and bonuses
        reward = base_reward * (1.0 - time_penalty) + confidence_bonus

        # Track SLA breaches
        sla_penalty = 0.0
        if elapsed_minutes > sess["sla_deadline_minutes"]:
            sess["sla_breaches"] += 1
            sla_penalty = 0.05 * sess["sla_breaches"]
            reward = reward * (1.0 - min(sla_penalty, 0.3))

        reward = _strict_clamp(reward)

        sess["total_reward"] += reward
        sess["rewards"].append(reward)

        # Get multi-dimensional score breakdown (advanced feature)
        try:
            score_breakdown = get_score_breakdown(task, step, merged, ticket)
        except Exception as e:
            logger.error(f"Score breakdown error: {e}")
            score_breakdown = {}

        score_breakdown.update({
            "time_penalty": round(time_penalty, 4),
            "confidence_bonus": round(confidence_bonus, 4),
            "base_reward": round(base_reward, 4),
            "sla_penalty": round(sla_penalty, 4),
            "sla_breaches": sess["sla_breaches"],
        })

        # Crisis surge: advance to next ticket
        if cfg.get("is_batch") and step < sess["max_steps"]:
            sess["current_ticket_idx"] += 1
            if sess["current_ticket_idx"] < len(sess["tickets"]):
                sess["ticket"] = sess["tickets"][sess["current_ticket_idx"]]
                sess["accumulated"] = {}
                sess["stress_level"] = max(_EPS, sess["stress_level"] - 0.08)
                sess["queue_depth"] = max(0, sess["queue_depth"] - 1)
                # Random new ticket arrival (30% chance)
                if random.random() < 0.3:
                    sess["queue_depth"] += 1
                    sess["stress_level"] = min(0.99, sess["stress_level"] + 0.05)
            sess["tickets_resolved"] += 1

        done = step >= sess["max_steps"]
        sess["done"] = done

        if done:
            try:
                self._metrics.record_episode(
                    task=task,
                    total_reward=sess["total_reward"],
                    tickets_resolved=sess.get("tickets_resolved", 1),
                    sla_breaches=sess["sla_breaches"],
                    confidence_calibration=self._compute_calibration(sess),
                )
            except Exception as e:
                logger.error(f"Metrics recording error: {e}")

        return {
            "observation": self._build_observation(session_id, reward),
            "reward": round(reward, 4),
            "done": done,
            "info": {
                "step": step,
                "total_reward": round(sess["total_reward"], 4),
                "task": task,
                "score_breakdown": score_breakdown,
                "time_penalty": round(time_penalty, 4),
                "confidence_bonus": round(confidence_bonus, 4),
            },
        }

    def state(self, session_id: str) -> Dict[str, Any]:
        """Get current episode state."""
        if not session_id or session_id not in self._sessions:
            raise ValueError(f"Unknown session_id: '{session_id}'")
        sess = self._sessions[session_id]
        return {
            "session_id": session_id,
            "task": sess["task"],
            "step": sess["step"],
            "max_steps": sess["max_steps"],
            "done": sess["done"],
            "total_reward": round(sess["total_reward"], 4),
            "ticket_id": sess["ticket"]["id"],
            "sla_breaches": sess.get("sla_breaches", 0),
            "stress_level": round(sess.get("stress_level", _EPS), 2),
        }

    def get_metrics(self) -> Dict[str, Any]:
        return self._metrics.get_summary()

    def _compute_reward(
        self, task: str, step: int, action: Dict[str, Any], ticket: Dict[str, Any]
    ) -> float:
        """Compute reward using appropriate grader."""
        try:
            if task == "ticket_classify":
                return grade_classify(action, ticket)
            if task == "ticket_route":
                return (
                    grade_route_step1(action, ticket)
                    if step == 1
                    else grade_route_step2(action, ticket)
                )
            if task == "ticket_resolve":
                if step == 1:
                    return grade_resolve_step1(action, ticket)
                elif step == 2:
                    return grade_resolve_step2(action, ticket)
                else:
                    return grade_resolve_step3(action, ticket)
            if task == "crisis_surge":
                # Simple grader for crisis_surge (priority + category + team)
                score = _EPS
                pred_priority = (action.get("priority") or "").strip().lower()
                if pred_priority == ticket.get("gt_priority"):
                    score += 0.02
                elif pred_priority in ticket.get("gt_priority_ok", []):
                    score += 0.01
                pred_category = (action.get("category") or "").strip().lower()
                if pred_category == ticket.get("gt_category"):
                    score += 0.02
                elif pred_category in ticket.get("gt_category_ok", []):
                    score += 0.01
                pred_team = (action.get("team") or "").strip().lower()
                if pred_team == ticket.get("gt_team"):
                    score += 0.04
                elif pred_team in ticket.get("gt_team_ok", []):
                    score += 0.02
                return _strict_clamp(score)
            return _EPS
        except Exception as e:
            logger.error(f"Reward computation failed: {e}")
            return _EPS

    def _compute_calibration(self, sess: Dict[str, Any]) -> float:
        """Compute confidence calibration score (1 - MAE)."""
        conf_hist = sess.get("confidence_history", [])
        acc_hist = sess.get("accuracy_history", [])
        if not conf_hist or len(conf_hist) != len(acc_hist):
            return 0.5  # neutral default
        try:
            mae = sum(abs(c - a) for c, a in zip(conf_hist, acc_hist)) / len(conf_hist)
            return max(0.01, min(0.99, 1.0 - mae))
        except Exception:
            return 0.5

    def _build_observation(self, session_id: str, last_reward: float) -> Dict[str, Any]:
        """Build observation dict for current state."""
        sess = self._sessions[session_id]
        ticket = sess["ticket"]
        task = sess["task"]
        cfg = TASK_CONFIGS[task]

        if sess["done"]:
            message = f"Episode complete. Total reward: {sess['total_reward']:.4f}. SLA breaches: {sess.get('sla_breaches', 0)}."
        elif sess["step"] == 0:
            message = f"New ticket. Task: {task}. Max steps: {cfg['max_steps']}. SLA: {sess['sla_deadline_minutes']} min."
        else:
            remaining = max(
                0, sess["sla_deadline_minutes"] - int((time.time() - sess["start_time"]) / 60)
            )
            message = f"Step {sess['step']} done. Reward: {last_reward:.4f}. SLA remaining: ~{remaining} min."

        obs = {
            "ticket_id": ticket["id"],
            "subject": ticket["subject"],
            "description": ticket["description"],
            "submitter": ticket["submitter"],
            "department": ticket["department"],
            "submitted_at": ticket["submitted_at"],
            "task": task,
            "step": sess["step"],
            "max_steps": sess["max_steps"],
            "last_reward": round(last_reward, 4),
            "session_id": session_id,
            "message": message,
            "sla_deadline_minutes": sess["sla_deadline_minutes"],
            "queue_depth": sess["queue_depth"],
            "stress_level": round(sess["stress_level"], 2),
            "org_context": ORG_CONTEXT,
            "similar_tickets": self._find_similar_tickets(ticket),
        }

        if cfg.get("is_batch"):
            obs["batch_info"] = {
                "total_tickets": len(sess["tickets"]),
                "current_index": sess["current_ticket_idx"],
                "tickets_resolved": sess.get("tickets_resolved", 0),
            }
        return obs

    def _find_similar_tickets(self, ticket: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find similar tickets by category."""
        try:
            gt_category = ticket.get("gt_category", "")
            ticket_id = ticket.get("id", "")
            candidates = [
                t
                for t in TICKETS
                if t.get("id") != ticket_id and t.get("gt_category") == gt_category
            ]
            random.shuffle(candidates)
            return [
                {
                    "id": t["id"],
                    "subject": t["subject"][:50],
                    "category": t["gt_category"],
                    "priority": t["gt_priority"],
                    "team": t["gt_team"],
                }
                for t in candidates[:3]
            ]
        except Exception:
            return []

    def _cleanup_expired_sessions(self) -> None:
        """Remove sessions older than timeout."""
        current_time = time.time()
        expired = [
            sid
            for sid, sess in self._sessions.items()
            if current_time - sess.get("last_activity", 0) > self._session_timeout_seconds
        ]
        for sid in expired:
            del self._sessions[sid]
            logger.info(f"Cleaned up expired session: {sid}")
