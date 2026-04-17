"""
Automation Rules Engine — Business Rule Automation for NexDesk.

Implements configurable automation rules for IT ticket lifecycle management:
  1. Auto-Assignment: Route tickets by category, priority, workload
  2. Auto-Escalation: Escalate tickets exceeding open-time thresholds
  3. Auto-Closure: Close tickets unanswered beyond N days
  4. SLA Breach Notifications: Alert when high-priority tickets exceed limits
  5. Predefined Reply Templates: Auto-generate acknowledgment responses

All rules are traceable — every automation action is logged with timestamp,
rule name, reason, and before/after state for full auditability.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


# ── Predefined Reply Templates ──

REPLY_TEMPLATES: Dict[str, str] = {
    "ack_critical": (
        "PRIORITY ALERT: Your ticket has been received and classified as CRITICAL. "
        "Our on-call team has been immediately notified and is actively investigating. "
        "Expected first response: within 15 minutes. "
        "Incident commander has been assigned. You will receive updates every 30 minutes."
    ),
    "ack_high": (
        "Your ticket has been received and classified as HIGH priority. "
        "A specialist has been assigned and will respond within 1 hour. "
        "We understand this is impacting your work and are treating it with urgency."
    ),
    "ack_medium": (
        "Thank you for submitting your ticket. It has been classified as MEDIUM priority "
        "and assigned to the appropriate team. Expected response time: 4-8 hours. "
        "You will be notified when a technician begins working on your issue."
    ),
    "ack_low": (
        "Your request has been logged and will be addressed during normal business hours. "
        "Expected response time: 1-2 business days. "
        "If your situation changes or becomes more urgent, please update this ticket."
    ),
    "auto_escalate": (
        "NOTICE: This ticket has been automatically escalated due to exceeding the "
        "maximum open time threshold. A senior specialist has been notified. "
        "We apologize for the delay and are prioritizing this issue."
    ),
    "auto_close_warning": (
        "This ticket has been inactive for an extended period. "
        "If your issue is still unresolved, please respond within 48 hours "
        "to keep this ticket open. Otherwise, it will be automatically closed."
    ),
    "auto_closed": (
        "This ticket has been automatically closed due to inactivity. "
        "If you still need assistance, please open a new ticket referencing "
        "this ticket number and we will resume from where we left off."
    ),
}


# ── Assignment Rules ──

# Maps ticket category to the team that should handle it
CATEGORY_TEAM_MAP: Dict[str, str] = {
    "network": "network-ops",
    "hardware": "sysadmin",
    "software": "dev",
    "access": "sysadmin",
    "security": "security",
    "database": "dev",
    "other": "helpdesk",
}

# SLA thresholds by priority (in minutes)
SLA_THRESHOLDS: Dict[str, Dict[str, int]] = {
    "critical": {"first_response": 15, "resolution": 60, "escalation": 30},
    "high":     {"first_response": 60, "resolution": 240, "escalation": 120},
    "medium":   {"first_response": 240, "resolution": 480, "escalation": 360},
    "low":      {"first_response": 480, "resolution": 1440, "escalation": 720},
}


class AutomationRule:
    """Represents a single automation rule with metadata."""

    def __init__(self, name: str, description: str, rule_type: str,
                 condition_fn: Callable, action_fn: Callable, enabled: bool = True):
        self.name = name
        self.description = description
        self.rule_type = rule_type  # "assignment", "escalation", "closure", "notification"
        self.condition_fn = condition_fn
        self.action_fn = action_fn
        self.enabled = enabled
        self.execution_count = 0
        self.last_executed = None

    def evaluate(self, ticket: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Evaluate this rule against a ticket. Returns action result or None."""
        if not self.enabled:
            return None
        try:
            if self.condition_fn(ticket, context):
                result = self.action_fn(ticket, context)
                self.execution_count += 1
                self.last_executed = datetime.now().isoformat()
                return result
        except Exception as e:
            logger.error(f"Rule '{self.name}' failed: {e}")
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "type": self.rule_type,
            "enabled": self.enabled,
            "execution_count": self.execution_count,
            "last_executed": self.last_executed,
        }


class AutomationEngine:
    """Manages and executes automation rules with full audit logging."""

    def __init__(self):
        self.rules: List[AutomationRule] = []
        self.audit_log: List[Dict[str, Any]] = []
        self.team_workload: Dict[str, int] = defaultdict(int)
        self._register_default_rules()

    def _log_action(self, rule_name: str, ticket_id: str, action: str,
                    detail: str, before: Any = None, after: Any = None):
        """Record an auditable automation action."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "rule": rule_name,
            "ticket_id": ticket_id,
            "action": action,
            "detail": detail,
            "before": before,
            "after": after,
        }
        self.audit_log.append(entry)
        logger.info(f"[AUTOMATION] {rule_name}: {action} on {ticket_id} — {detail}")

    def _register_default_rules(self):
        """Register built-in automation rules."""

        # Rule 1: Auto-assign by category
        self.rules.append(AutomationRule(
            name="auto_assign_by_category",
            description="Assign incoming tickets to the correct team based on category",
            rule_type="assignment",
            condition_fn=lambda t, ctx: (
                t.get("category") in CATEGORY_TEAM_MAP
                and not t.get("assigned_team")
            ),
            action_fn=lambda t, ctx: self._action_auto_assign(t, ctx),
        ))

        # Rule 2: Auto-assign by workload balancing
        self.rules.append(AutomationRule(
            name="auto_balance_workload",
            description="Re-route tickets if assigned team is overloaded (>5 active tickets)",
            rule_type="assignment",
            condition_fn=lambda t, ctx: (
                t.get("assigned_team")
                and self.team_workload.get(t["assigned_team"], 0) > 5
            ),
            action_fn=lambda t, ctx: self._action_balance_workload(t, ctx),
        ))

        # Rule 3: Auto-escalate stale tickets
        self.rules.append(AutomationRule(
            name="auto_escalate_stale",
            description="Escalate tickets that exceed the escalation time threshold",
            rule_type="escalation",
            condition_fn=lambda t, ctx: self._check_stale(t, ctx),
            action_fn=lambda t, ctx: self._action_auto_escalate(t, ctx),
        ))

        # Rule 4: SLA breach notification
        self.rules.append(AutomationRule(
            name="sla_breach_alert",
            description="Send alert when a high-priority ticket exceeds SLA threshold",
            rule_type="notification",
            condition_fn=lambda t, ctx: self._check_sla_breach(t, ctx),
            action_fn=lambda t, ctx: self._action_sla_alert(t, ctx),
        ))

        # Rule 5: Auto-close inactive tickets
        self.rules.append(AutomationRule(
            name="auto_close_inactive",
            description="Close tickets with no user response after 7 days",
            rule_type="closure",
            condition_fn=lambda t, ctx: self._check_inactive(t, ctx),
            action_fn=lambda t, ctx: self._action_auto_close(t, ctx),
        ))

        # Rule 6: Auto-reply acknowledgment
        self.rules.append(AutomationRule(
            name="auto_reply_ack",
            description="Send priority-appropriate acknowledgment on ticket creation",
            rule_type="notification",
            condition_fn=lambda t, ctx: (
                t.get("status") == "new" and not t.get("ack_sent")
            ),
            action_fn=lambda t, ctx: self._action_auto_reply(t, ctx),
        ))

    # ── Condition Checkers ──

    def _check_stale(self, ticket: Dict, ctx: Dict) -> bool:
        """Check if ticket exceeds escalation threshold."""
        priority = ticket.get("priority", "medium")
        thresholds = SLA_THRESHOLDS.get(priority, SLA_THRESHOLDS["medium"])
        elapsed = ctx.get("elapsed_minutes", 0)
        return (
            elapsed > thresholds["escalation"]
            and ticket.get("status") not in ("closed", "escalated", "resolved")
        )

    def _check_sla_breach(self, ticket: Dict, ctx: Dict) -> bool:
        """Check if ticket has breached SLA."""
        priority = ticket.get("priority", "medium")
        thresholds = SLA_THRESHOLDS.get(priority, SLA_THRESHOLDS["medium"])
        elapsed = ctx.get("elapsed_minutes", 0)
        return (
            elapsed > thresholds["resolution"]
            and ticket.get("status") not in ("closed", "resolved")
            and not ticket.get("sla_breach_notified")
        )

    def _check_inactive(self, ticket: Dict, ctx: Dict) -> bool:
        """Check if ticket has been inactive for closure."""
        days_inactive = ctx.get("days_since_last_response", 0)
        return (
            days_inactive >= 7
            and ticket.get("status") not in ("closed", "resolved")
            and ticket.get("priority") not in ("critical", "high")
        )

    # ── Action Handlers ──

    def _action_auto_assign(self, ticket: Dict, ctx: Dict) -> Dict:
        """Assign ticket to the correct team based on category."""
        category = ticket.get("category", "other")
        team = CATEGORY_TEAM_MAP.get(category, "helpdesk")
        old_team = ticket.get("assigned_team")
        ticket["assigned_team"] = team
        self.team_workload[team] += 1
        self._log_action(
            "auto_assign_by_category", ticket.get("id", "?"),
            "assign", f"Assigned to {team} (category: {category})",
            before=old_team, after=team,
        )
        return {"action": "assigned", "team": team, "category": category}

    def _action_balance_workload(self, ticket: Dict, ctx: Dict) -> Dict:
        """Re-route to least loaded team."""
        current = ticket.get("assigned_team", "helpdesk")
        # Find team with lowest workload
        candidates = list(set(CATEGORY_TEAM_MAP.values()))
        least_loaded = min(candidates, key=lambda t: self.team_workload.get(t, 0))
        if least_loaded != current:
            ticket["assigned_team"] = least_loaded
            self.team_workload[current] = max(0, self.team_workload[current] - 1)
            self.team_workload[least_loaded] += 1
            self._log_action(
                "auto_balance_workload", ticket.get("id", "?"),
                "reassign", f"Rebalanced from {current} (load:{self.team_workload[current]+1}) to {least_loaded} (load:{self.team_workload[least_loaded]})",
                before=current, after=least_loaded,
            )
        return {"action": "rebalanced", "from": current, "to": least_loaded}

    def _action_auto_escalate(self, ticket: Dict, ctx: Dict) -> Dict:
        """Escalate a stale ticket."""
        old_status = ticket.get("status")
        old_priority = ticket.get("priority", "medium")

        # Bump priority
        bump_map = {"low": "medium", "medium": "high", "high": "critical", "critical": "critical"}
        ticket["priority"] = bump_map.get(old_priority, "high")
        ticket["status"] = "escalated"
        ticket["escalated_at"] = datetime.now().isoformat()
        ticket["auto_reply"] = REPLY_TEMPLATES["auto_escalate"]

        self._log_action(
            "auto_escalate_stale", ticket.get("id", "?"),
            "escalate",
            f"Auto-escalated: priority {old_priority}->{ticket['priority']}, status {old_status}->escalated",
            before={"status": old_status, "priority": old_priority},
            after={"status": "escalated", "priority": ticket["priority"]},
        )
        return {"action": "escalated", "old_priority": old_priority, "new_priority": ticket["priority"]}

    def _action_sla_alert(self, ticket: Dict, ctx: Dict) -> Dict:
        """Send SLA breach notification."""
        ticket["sla_breach_notified"] = True
        elapsed = ctx.get("elapsed_minutes", 0)
        priority = ticket.get("priority", "medium")
        threshold = SLA_THRESHOLDS.get(priority, SLA_THRESHOLDS["medium"])["resolution"]

        self._log_action(
            "sla_breach_alert", ticket.get("id", "?"),
            "notify",
            f"SLA BREACH: {elapsed}min elapsed, threshold was {threshold}min (priority: {priority})",
        )
        return {
            "action": "sla_breach_alert",
            "elapsed_minutes": elapsed,
            "threshold_minutes": threshold,
            "priority": priority,
        }

    def _action_auto_close(self, ticket: Dict, ctx: Dict) -> Dict:
        """Auto-close inactive ticket."""
        old_status = ticket.get("status")
        ticket["status"] = "closed"
        ticket["closed_at"] = datetime.now().isoformat()
        ticket["close_reason"] = "auto_closed_inactive"
        ticket["auto_reply"] = REPLY_TEMPLATES["auto_closed"]

        self._log_action(
            "auto_close_inactive", ticket.get("id", "?"),
            "close",
            f"Auto-closed after {ctx.get('days_since_last_response', '?')} days inactive",
            before={"status": old_status},
            after={"status": "closed", "reason": "auto_closed_inactive"},
        )
        return {"action": "auto_closed", "days_inactive": ctx.get("days_since_last_response")}

    def _action_auto_reply(self, ticket: Dict, ctx: Dict) -> Dict:
        """Send priority-based auto-acknowledgment."""
        priority = ticket.get("priority", "medium")
        template_key = f"ack_{priority}"
        reply = REPLY_TEMPLATES.get(template_key, REPLY_TEMPLATES["ack_medium"])
        ticket["ack_sent"] = True
        ticket["auto_reply"] = reply

        self._log_action(
            "auto_reply_ack", ticket.get("id", "?"),
            "reply", f"Auto-ack sent for {priority} priority ticket",
        )
        return {"action": "auto_reply", "priority": priority, "template": template_key}

    # ── Public API ──

    def process_ticket(self, ticket: Dict[str, Any],
                       context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Run all enabled rules against a ticket. Returns list of actions taken."""
        ctx = context or {}
        results = []
        for rule in self.rules:
            result = rule.evaluate(ticket, ctx)
            if result:
                result["rule_name"] = rule.name
                result["rule_type"] = rule.rule_type
                results.append(result)
        return results

    def update_workload(self, team: str, delta: int):
        """Manually adjust team workload counter."""
        self.team_workload[team] = max(0, self.team_workload.get(team, 0) + delta)

    def get_rules(self) -> List[Dict[str, Any]]:
        """Return all registered rules with stats."""
        return [r.to_dict() for r in self.rules]

    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent audit log entries."""
        return list(reversed(self.audit_log[-limit:]))

    def get_stats(self) -> Dict[str, Any]:
        """Return engine statistics."""
        type_counts: Dict[str, int] = defaultdict(int)
        for entry in self.audit_log:
            type_counts[entry.get("action", "unknown")] += 1
        return {
            "total_rules": len(self.rules),
            "enabled_rules": sum(1 for r in self.rules if r.enabled),
            "total_executions": len(self.audit_log),
            "action_breakdown": dict(type_counts),
            "team_workload": dict(self.team_workload),
        }

    def get_sla_thresholds(self) -> Dict[str, Dict[str, int]]:
        """Return SLA threshold configuration."""
        return dict(SLA_THRESHOLDS)

    def get_reply_templates(self) -> Dict[str, str]:
        """Return predefined reply templates."""
        return dict(REPLY_TEMPLATES)
