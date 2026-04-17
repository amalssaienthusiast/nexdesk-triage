"""
Iteration Engine — Handles unresolved and flagged issues.

Implements a 4-cycle escalation ladder:
  1. Re-classify with elevated severity
  2. Retry with alternative resolution strategy
  3. Escalate to human agent
  4. Close with post-mortem record
"""

from datetime import datetime
from typing import Any, Dict, List, Optional


class IterationEngine:
    """Manages the lifecycle of unresolved/flagged issues through
    progressive escalation."""

    MAX_RETRIES = 4

    def __init__(self):
        self.flagged_issues: Dict[str, Dict[str, Any]] = {}
        self.retry_counts: Dict[str, int] = {}
        self.iteration_log: List[Dict[str, Any]] = []
        self.post_mortems: List[Dict[str, Any]] = []

    def flag(self, ticket_id: str, issue: Dict[str, Any], reason: str) -> Dict[str, Any]:
        """Flag an issue as needing re-handling.
        
        Args:
            ticket_id: Unique identifier for the ticket
            issue: The issue dict from AEDI discovery
            reason: Why it was flagged (e.g., "agent_low_confidence", "resolution_failed")
        
        Returns:
            The flagged issue dict with metadata attached.
        """
        issue["flag_reason"] = reason
        issue["flagged_at"] = datetime.now().isoformat()
        issue["status"] = "flagged"
        issue["original_severity"] = issue.get("severity", "medium")
        self.flagged_issues[ticket_id] = issue
        self.retry_counts[ticket_id] = 0
        return issue

    def iterate(self, ticket_id: str) -> Dict[str, Any]:
        """Execute the next iteration cycle for a flagged ticket.
        
        The escalation ladder:
          Cycle 0: Re-classify — bump severity one level
          Cycle 1: Retry — attempt alternative resolution strategy
          Cycle 2: Escalate — hand off to human agent
          Cycle 3+: Close — create post-mortem record
        
        Returns:
            Dict with action type and updated issue data.
        """
        if ticket_id not in self.flagged_issues:
            return {"action": "not_found", "ticket_id": ticket_id}

        retries = self.retry_counts.get(ticket_id, 0)
        issue = self.flagged_issues[ticket_id]

        if retries == 0:
            # Cycle 1: Re-classify with elevated severity
            action = "re_classify"
            severity_map = {
                "low": "medium",
                "medium": "high",
                "high": "critical",
                "critical": "critical",
            }
            old_sev = issue.get("severity", "medium")
            issue["severity"] = severity_map.get(old_sev, "high")
            issue["status"] = "re_classifying"
            issue["re_classified_at"] = datetime.now().isoformat()

        elif retries == 1:
            # Cycle 2: Retry with alternative strategy
            action = "retry_new_strategy"
            issue["status"] = "retrying"
            issue["retry_strategy"] = (
                f"Alternative resolution for '{issue.get('suggested_title', '?')}': "
                f"Attempt L2 specialist diagnostic, check KB for similar resolved tickets"
            )
            issue["suggested_action"] = (
                f"[Retry {retries + 1}] Escalate to L2 specialist for "
                f"'{issue.get('category', 'unknown')}' category. "
                f"Apply alternative diagnostic procedure."
            )

        elif retries == 2:
            # Cycle 3: Escalate to human
            action = "escalate_human"
            issue["status"] = "escalated_to_human"
            issue["escalated_at"] = datetime.now().isoformat()
            issue["escalation_reason"] = (
                f"Automated resolution failed after {retries} attempts. "
                f"Original reason: {issue.get('flag_reason', 'unknown')}. "
                f"Severity: {issue.get('severity', '?')}."
            )

        else:
            # Cycle 4+: Close with post-mortem
            action = "close_with_postmortem"
            issue["status"] = "closed_postmortem"
            issue["closed_at"] = datetime.now().isoformat()
            post_mortem = {
                "ticket_id": ticket_id,
                "title": issue.get("suggested_title", "Unknown"),
                "category": issue.get("category", "unknown"),
                "original_severity": issue.get("original_severity", "?"),
                "final_severity": issue.get("severity", "?"),
                "total_retries": retries,
                "flag_reason": issue.get("flag_reason", "?"),
                "timeline": {
                    "flagged": issue.get("flagged_at"),
                    "re_classified": issue.get("re_classified_at"),
                    "escalated": issue.get("escalated_at"),
                    "closed": issue.get("closed_at"),
                },
                "outcome": "unresolved_escalated",
            }
            self.post_mortems.append(post_mortem)

        self.retry_counts[ticket_id] = retries + 1

        result = {
            "action": action,
            "ticket_id": ticket_id,
            "updated_issue": issue,
            "retry_num": retries + 1,
            "timestamp": datetime.now().isoformat(),
        }
        self.iteration_log.append(result)
        return result

    def get_flagged(self) -> Dict[str, Dict[str, Any]]:
        """Return all currently flagged issues."""
        return dict(self.flagged_issues)

    def get_iteration_log(self) -> List[Dict[str, Any]]:
        """Return the full iteration history."""
        return list(self.iteration_log)

    def get_post_mortems(self) -> List[Dict[str, Any]]:
        """Return all post-mortem records."""
        return list(self.post_mortems)

    def get_stats(self) -> Dict[str, Any]:
        """Return engine statistics."""
        statuses = {}
        for issue in self.flagged_issues.values():
            s = issue.get("status", "unknown")
            statuses[s] = statuses.get(s, 0) + 1
        return {
            "total_flagged": len(self.flagged_issues),
            "total_iterations": len(self.iteration_log),
            "total_post_mortems": len(self.post_mortems),
            "status_breakdown": statuses,
        }
