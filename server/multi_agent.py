# server/multi_agent.py
from typing import Any, Dict, List, Optional
from enum import Enum

class EscalationPolicy(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"
    THRESHOLD = "threshold"

class AgentRole:
    def __init__(self, role: str, name: str):
        self.role = role
        self.name = name
        self.actions_taken: List[Dict] = []
        self.tickets_handled = 0
        self.escalations_sent = 0
        self.escalations_received = 0

    def record_action(self, action: Dict[str, Any]):
        self.actions_taken.append(action)
        self.tickets_handled += 1

    def to_dict(self):
        return {
            "role": self.role,
            "name": self.name,
            "tickets_handled": self.tickets_handled,
            "escalations_sent": self.escalations_sent,
            "escalations_received": self.escalations_received,
        }


class MultiAgentOrchestrator:
    MAX_ESCALATIONS = 3
    PINGPONG_PENALTY = 0.15

    def __init__(self):
        self.l1 = AgentRole("l1_dispatcher", "NexDesk-L1")
        self.l2_agents = {
            "network-ops": AgentRole("l2_specialist", "NexDesk-L2-Network"),
            "sysadmin": AgentRole("l2_specialist", "NexDesk-L2-SysAdmin"),
            "security": AgentRole("l2_specialist", "NexDesk-L2-Security"),
            "dev": AgentRole("l2_specialist", "NexDesk-L2-Dev"),
            "helpdesk": AgentRole("l2_specialist", "NexDesk-L2-Helpdesk"),
        }
        self.escalation_history: List[Dict] = []
        self.active_agent = "l1"
        self.bounce_count = 0
        self.total_penalty = 0.0

    def get_current_agent(self) -> AgentRole:
        if self.active_agent == "l1":
            return self.l1
        return self.l2_agents.get(self.active_agent, self.l1)

    def process_action(self, action: Dict[str, Any], ticket: Dict[str, Any]) -> Dict[str, Any]:
        action_type = action.get("action_type")
        category = action.get("category", "")
        team = action.get("team", "")

        current = self.get_current_agent()
        current.record_action(action)

        if action_type in ("escalate", "delegate"):
            return self._handle_escalation(action, ticket, current, team, category)

        # Normal action
        return {
            **action,
            "_multi_agent": {
                "handled_by": current.to_dict(),
                "bounce_count": self.bounce_count,
                "penalty_applied": 0.0,
            }
        }

    def _handle_escalation(self, action: Dict, ticket: Dict, from_agent: AgentRole, target_team: str, category: str) -> Dict:
        correct_l2 = {
            "network": "network-ops",
            "hardware": "sysadmin",
            "software": "dev",
            "access": "sysadmin",
            "security": "security",
            "other": "helpdesk"
        }.get(category, "helpdesk")

        target = target_team or correct_l2

        # Ping-pong detection
        penalty = 0.0
        if self.bounce_count > 0:
            penalty = self.PINGPONG_PENALTY * min(self.bounce_count, 2)
            self.total_penalty += penalty

        self.bounce_count += 1
        from_agent.escalations_sent += 1

        self.escalation_history.append({
            "from": from_agent.role,
            "to": target,
            "category": category,
            "correct_target": correct_l2,
            "was_correct": target == correct_l2,
            "bounce_number": self.bounce_count,
            "penalty": penalty,
        })

        # Switch active agent
        if target in self.l2_agents:
            self.active_agent = target
            self.l2_agents[target].escalations_received += 1
        else:
            self.active_agent = "helpdesk"
            self.l2_agents["helpdesk"].escalations_received += 1

        result = dict(action)
        result["_multi_agent"] = {
            "handled_by": from_agent.to_dict(),
            "escalated_to": self.get_current_agent().to_dict(),
            "bounce_count": self.bounce_count,
            "penalty_applied": round(penalty, 4),
            "correct_escalation": target == correct_l2,
        }
        return result

    def get_reward_modifier(self) -> float:
        if self.bounce_count == 0:
            return 1.0
        if self.bounce_count == 1:
            return 1.0 if all(e["was_correct"] for e in self.escalation_history) else 0.9
        return max(0.3, 1.0 - self.total_penalty)

    def get_summary(self) -> Dict:
        return {
            "l1_dispatcher": self.l1.to_dict(),
            "l2_specialists": {team: agent.to_dict() for team, agent in self.l2_agents.items() if agent.tickets_handled > 0},
            "escalation_history": self.escalation_history,
            "total_bounces": self.bounce_count,
            "total_penalty": round(self.total_penalty, 4),
            "reward_modifier": round(self.get_reward_modifier(), 4),
        }
