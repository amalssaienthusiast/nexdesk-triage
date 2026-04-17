import datetime
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class TriageFlagEngine:
    """
    Advanced flagging & alerting system for NexDesk.
    Detects SLA breaches, priority mismatches, multi-agent bounce loops,
    confidence gaps, and anomalies.
    """

    def __init__(self):
        self._flags = []

    def evaluate(self, session: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Evaluate session state and return any active flags.
        This modifies the session object by injecting an 'active_flags' list.
        """
        active_flags = []
        ticket = session.get("ticket", {})
        session_id = session.get("session_id", "unknown")
        task = session.get("task", "unknown")
        
        # 1. SLA Breach Alert (Critical)
        elapsed_minutes = (datetime.datetime.now(datetime.timezone.utc).timestamp() - session.get("start_time", 0)) / 60.0
        sla_deadline = session.get("sla_deadline_minutes", 60)
        
        if elapsed_minutes > sla_deadline:
            active_flags.append(self._create_flag(
                session_id=session_id,
                ticket_id=ticket.get("id"),
                flag_type="SLA_BREACH",
                severity="critical",
                message=f"SLA deadline exceeded by {int(elapsed_minutes - sla_deadline)} minutes.",
                recommended_action="Expedite ticket resolution or auto-escalate to Level 3."
            ))
        elif elapsed_minutes > (sla_deadline * 0.8):
            active_flags.append(self._create_flag(
                session_id=session_id,
                ticket_id=ticket.get("id"),
                flag_type="SLA_WARNING",
                severity="warn",
                message="SLA deadline approaching (80% consumed).",
                recommended_action="Prioritize ticket in queue."
            ))

        # 2. Priority Mismatch (Warn / Critical)
        # Assuming the agent made a classification and it's stored in accumulated
        accumulated = session.get("accumulated", {})
        agent_priority = accumulated.get("priority")
        gt_priority = ticket.get("gt_priority")
        
        if agent_priority and gt_priority:
            if gt_priority == "critical" and agent_priority in ["low", "medium"]:
                active_flags.append(self._create_flag(
                    session_id=session_id,
                    ticket_id=ticket.get("id"),
                    flag_type="PRIORITY_MISMATCH_SEVERE",
                    severity="critical",
                    message="Agent incorrectly classified a CRITICAL ticket as low/medium. High risk of SLA failure.",
                    recommended_action="Manual human review required immediately."
                ))
            elif agent_priority != gt_priority and gt_priority not in ticket.get("gt_priority_ok", []):
                # Standard mismatch
                active_flags.append(self._create_flag(
                    session_id=session_id,
                    ticket_id=ticket.get("id"),
                    flag_type="PRIORITY_MISMATCH",
                    severity="warn",
                    message=f"Agent priority '{agent_priority}' does not match ground truth '{gt_priority}'.",
                    recommended_action="Review classification logic."
                ))

        # 3. Bounce Alert (Multi-Agent Escalation Loop)
        bounce_count = session.get("bounce_count", 0)
        if bounce_count > 1:
            active_flags.append(self._create_flag(
                session_id=session_id,
                ticket_id=ticket.get("id"),
                flag_type="BOUNCE_LOOP",
                severity="critical" if bounce_count > 2 else "warn",
                message=f"Ticket bounced {bounce_count} times between teams.",
                recommended_action="Force manual routing by Dispatch Manager."
            ))

        # 4. Confidence Gap
        conf_history = session.get("confidence_history", [])
        acc_history = session.get("accuracy_history", [])
        if conf_history and acc_history:
            last_conf = conf_history[-1]
            last_acc = acc_history[-1]
            if (last_conf - last_acc) > 0.4:
                active_flags.append(self._create_flag(
                    session_id=session_id,
                    ticket_id=ticket.get("id"),
                    flag_type="OVERCONFIDENT_AGENT",
                    severity="warn",
                    message=f"Agent is highly confident ({last_conf:.2f}) but accuracy is poor ({last_acc:.2f}).",
                    recommended_action="Trigger model calibration protocol."
                ))

        # 5. Anomaly: Extremely low reward early in resolution
        if session.get("step", 0) > 0 and session.get("total_reward", 1.0) < 0.15 and not session.get("done", False):
             active_flags.append(self._create_flag(
                session_id=session_id,
                ticket_id=ticket.get("id"),
                flag_type="LOW_REWARD_ANOMALY",
                severity="info",
                message="Agent is struggling to accumulate reward on this ticket.",
                recommended_action="Provide KB search hint."
            ))
             
        session["active_flags"] = active_flags
        return active_flags

    def _create_flag(self, session_id: str, ticket_id: str, flag_type: str, severity: str, message: str, recommended_action: str) -> Dict[str, Any]:
        """Helper to standardize flag formatting."""
        return {
            "session_id": session_id,
            "ticket_id": ticket_id,
            "type": flag_type,
            "severity": severity,
            "message": message,
            "recommended_action": recommended_action,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
