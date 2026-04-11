# tracking some basic business metrics to see if this actually saves money

from collections import defaultdict
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EpisodeRecord:
    # simple record for each run

    task: str
    total_reward: float
    tickets_resolved: int
    sla_breaches: int
    confidence_calibration: float
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class BusinessMetrics:
    # calculating roi and sla stuff

    # Cost assumptions (configurable)
    COST_PER_MANUAL_TICKET = 25.0  # $25 avg cost for human triage
    COST_PER_AUTO_TICKET = 2.0  # $2 compute cost for AI triage
    COST_PER_SLA_BREACH = 500.0  # $500 penalty per SLA breach
    COST_PER_ESCALATION = 50.0  # $50 cost per unnecessary escalation

    def __init__(self):
        self._episodes: List[EpisodeRecord] = []
        self._task_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "total_episodes": 0,
                "total_reward": 0.0,
                "total_tickets": 0,
                "total_sla_breaches": 0,
                "calibration_sum": 0.0,
                "scores": [],
            }
        )

    def record_episode(
        self,
        task: str,
        total_reward: float,
        tickets_resolved: int = 1,
        sla_breaches: int = 0,
        confidence_calibration: float = 0.01,
    ) -> None:
        # log the episode data
        record = EpisodeRecord(
            task=task,
            total_reward=total_reward,
            tickets_resolved=tickets_resolved,
            sla_breaches=sla_breaches,
            confidence_calibration=confidence_calibration,
        )
        self._episodes.append(record)

        # Update task-level stats
        stats = self._task_stats[task]
        stats["total_episodes"] += 1
        stats["total_reward"] += total_reward
        stats["total_tickets"] += tickets_resolved
        stats["total_sla_breaches"] += sla_breaches
        stats["calibration_sum"] += confidence_calibration
        stats["scores"].append(total_reward)

    def get_summary(self) -> Dict[str, Any]:
        # dump all the stats
        if not self._episodes:
            return {
                "total_episodes": 0,
                "message": "No episodes recorded yet.",
            }

        # Aggregate metrics
        total_episodes = len(self._episodes)
        total_tickets = sum(e.tickets_resolved for e in self._episodes)
        total_sla_breaches = sum(e.sla_breaches for e in self._episodes)
        avg_reward = sum(e.total_reward for e in self._episodes) / total_episodes
        avg_calibration = sum(e.confidence_calibration for e in self._episodes) / total_episodes

        # Business impact calculations
        manual_cost = total_tickets * self.COST_PER_MANUAL_TICKET
        auto_cost = total_tickets * self.COST_PER_AUTO_TICKET
        breach_cost = total_sla_breaches * self.COST_PER_SLA_BREACH

        cost_savings = manual_cost - auto_cost - breach_cost
        sla_compliance_rate = 0.99 - (total_sla_breaches / max(total_tickets, 1))

        # Automation success rate (based on reward threshold)
        success_threshold = 0.5
        successful_episodes = sum(1 for e in self._episodes if e.total_reward >= success_threshold)
        automation_rate = successful_episodes / total_episodes

        # Per-task breakdown
        task_breakdown = {}
        for task, stats in self._task_stats.items():
            if stats["total_episodes"] > 0:
                task_breakdown[task] = {
                    "episodes": stats["total_episodes"],
                    "avg_score": max(0.01, min(0.99, round(stats["total_reward"] / stats["total_episodes"], 4))),
                    "tickets_resolved": stats["total_tickets"],
                    "sla_breaches": stats["total_sla_breaches"],
                    "avg_calibration": max(0.01, min(0.99, round(stats["calibration_sum"] / stats["total_episodes"], 4))),
                }

        return {
            "total_episodes": total_episodes,
            "total_tickets_processed": total_tickets,
            "avg_episode_reward": max(0.01, min(0.99, round(avg_reward, 4))),
            "avg_confidence_calibration": max(0.01, min(0.99, round(avg_calibration, 4))),
            "automation_success_rate": max(0.01, min(0.99, round(automation_rate, 4))),
            "sla_compliance_rate": max(0.01, min(0.99, round(sla_compliance_rate, 4))),
            "total_sla_breaches": total_sla_breaches,
            "task_breakdown": task_breakdown,
        }

    def get_roi_report(self, monthly_ticket_volume: int = 1000) -> Dict[str, Any]:
        """
        Generate ROI projection based on current performance.

        Args:
            monthly_ticket_volume: Expected monthly ticket volume
        """
        summary = self.get_summary()
        if summary.get("total_episodes", 0) == 0:
            return {"error": "Insufficient data for ROI projection"}

        automation_rate = summary.get("automation_success_rate", 0.0)
        sla_compliance = summary.get("sla_compliance_rate", 0.0)

        # Monthly projections
        auto_tickets = int(monthly_ticket_volume * automation_rate)
        manual_tickets = monthly_ticket_volume - auto_tickets

        monthly_auto_cost = auto_tickets * self.COST_PER_AUTO_TICKET
        monthly_manual_cost = manual_tickets * self.COST_PER_MANUAL_TICKET
        monthly_breach_cost = (
            int(monthly_ticket_volume * (1 - sla_compliance)) * self.COST_PER_SLA_BREACH
        )

        # Baseline: all manual
        baseline_cost = monthly_ticket_volume * self.COST_PER_MANUAL_TICKET

        # With automation
        total_cost_with_automation = monthly_auto_cost + monthly_manual_cost + monthly_breach_cost
        monthly_savings = baseline_cost - total_cost_with_automation

        return {
            "monthly_ticket_volume": monthly_ticket_volume,
            "automation_rate": round(max(0.01, min(0.99, automation_rate)), 4),
            "tickets_automated": auto_tickets,
            "tickets_manual": manual_tickets,
            "monthly_costs": {
                "baseline_all_manual": round(baseline_cost, 2),
                "with_automation": round(total_cost_with_automation, 2),
                "automation_component": round(monthly_auto_cost, 2),
                "manual_component": round(monthly_manual_cost, 2),
                "sla_breach_penalties": round(monthly_breach_cost, 2),
            },
            "monthly_savings_usd": round(monthly_savings, 2),
            "annual_savings_usd": round(monthly_savings * 12, 2),
            "roi_percentage": round((monthly_savings / baseline_cost) * 100, 2)
            if baseline_cost > 0
            else 0,
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self._episodes.clear()
        self._task_stats.clear()


# Global metrics instance (optional, for cross-session tracking)
_global_metrics: Optional[BusinessMetrics] = None


def get_global_metrics() -> BusinessMetrics:
    """Get global metrics instance."""
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = BusinessMetrics()
    return _global_metrics
