"""
Helpdesk Notifier — Alert system for the AEDI pipeline.

Produces TUI banners, maintains an in-memory alert ring-buffer,
and integrates with the dashboard event feed.
"""

from collections import deque
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


class HelpdeskNotifier:
    """Notification hub for error discoveries and iteration events."""

    def __init__(self, max_alerts: int = 100, emit_fn: Optional[Callable] = None):
        """
        Args:
            max_alerts: Maximum alerts to keep in the ring buffer.
            emit_fn: Optional callback to push events to the dashboard
                     (e.g. app.py's _emit_event function).
        """
        self.alerts: deque = deque(maxlen=max_alerts)
        self._emit_fn = emit_fn

    def notify_new_issue(self, classified_event: Dict[str, Any]) -> Dict[str, Any]:
        """Emit an alert for a newly discovered unknown error."""
        alert = {
            "id": len(self.alerts) + 1,
            "type": "NEW_UNKNOWN_ERROR",
            "severity": classified_event.get("severity", "unknown"),
            "title": classified_event.get("suggested_title", "Unnamed Issue"),
            "category": classified_event.get("category", "unknown"),
            "source": classified_event.get("source", "unknown"),
            "action": classified_event.get("suggested_action", ""),
            "confidence": classified_event.get("confidence", 0),
            "aedi_id": classified_event.get("id", ""),
            "timestamp": datetime.now().isoformat(),
        }
        self.alerts.appendleft(alert)

        # Push to dashboard if emit function is configured
        if self._emit_fn:
            try:
                self._emit_fn(
                    event_type="aedi_discovery",
                    detail=f"Novel error: {alert['title']} [{alert['severity']}]",
                )
            except Exception:
                pass

        return alert

    def notify_iteration(self, ticket_id: str, iteration_result: Dict[str, Any]) -> Dict[str, Any]:
        """Emit an alert for an iteration/escalation cycle."""
        action = iteration_result.get("action", "unknown")
        issue = iteration_result.get("updated_issue", {})
        retry = iteration_result.get("retry_num", 0)

        action_labels = {
            "re_classify": f"Re-classifying #{ticket_id} with elevated severity",
            "retry_new_strategy": f"Retrying #{ticket_id} with alternative strategy",
            "escalate_human": f"ESCALATING #{ticket_id} to human agent",
            "close_with_postmortem": f"Closing #{ticket_id} with post-mortem (max retries)",
            "not_found": f"#{ticket_id} not found in flagged queue",
        }

        alert = {
            "id": len(self.alerts) + 1,
            "type": f"iteration_{action}",
            "ticket_id": ticket_id,
            "action": action,
            "label": action_labels.get(action, f"#{ticket_id}: {action}"),
            "severity": issue.get("severity", "unknown"),
            "retry_num": retry,
            "timestamp": datetime.now().isoformat(),
        }
        self.alerts.appendleft(alert)

        if self._emit_fn:
            try:
                self._emit_fn(
                    event_type=f"aedi_{action}",
                    detail=alert["label"],
                )
            except Exception:
                pass

        return alert

    def get_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent alerts."""
        return list(self.alerts)[:limit]

    def get_stats(self) -> Dict[str, Any]:
        """Return alert statistics."""
        type_counts: Dict[str, int] = {}
        for a in self.alerts:
            t = a.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        return {
            "total_alerts": len(self.alerts),
            "alert_types": type_counts,
        }
