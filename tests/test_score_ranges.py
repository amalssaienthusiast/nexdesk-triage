from server.environment import NexDeskEnv
from server.graders import (
    grade_classify,
    grade_crisis,
    grade_full_episode,
    grade_resolve,
    grade_route,
)
from server.tickets import TICKETS


TASKS = ["ticket_classify", "ticket_route", "ticket_resolve", "crisis_surge"]


def test_task_level_graders_stay_strictly_in_range():
    ticket = TICKETS[0]
    action = {
        "priority": "high",
        "category": "network",
        "team": "network-ops",
        "affected_system": "laptop",
        "first_response": "We are looking into this now and will update you shortly.",
        "resolution_steps": ["Check the adapter", "Refresh DHCP lease"],
        "sla_hours": 4,
        "confidence": 0.8,
    }

    scores = [
        grade_classify(action, ticket),
        grade_route(action, ticket),
        grade_resolve(action, ticket),
        grade_crisis(action, ticket),
    ]

    assert all(0.0 < score < 1.0 for score in scores)


def test_environment_rewards_and_metrics_stay_strictly_in_range():
    env = NexDeskEnv()
    action = {
        "priority": "medium",
        "category": "other",
        "team": "helpdesk",
        "affected_system": "unknown",
        "first_response": "Thank you for the report. We are investigating now.",
        "resolution_steps": ["Investigate", "Mitigate", "Verify"],
        "sla_hours": 8,
        "confidence": 0.5,
    }

    for task in TASKS:
        reset_result = env.reset(task)
        assert 0.0 < reset_result["observation"]["last_reward"] < 1.0

        for _ in range(reset_result["observation"]["max_steps"]):
            step_result = env.step(reset_result["session_id"], action)
            assert 0.0 < step_result["reward"] < 1.0
            assert 0.0 < step_result["info"]["total_reward"] < 1.0
            if step_result["done"]:
                break

    summary = env.get_metrics()
    assert 0.0 < summary["avg_episode_reward"] < 1.0
    assert 0.0 < summary["automation_success_rate"] < 1.0


def test_grade_full_episode_metadata_stays_strictly_in_range():
    result = grade_full_episode(
        "ticket_resolve",
        rewards=[0.4, 0.3, 0.28],
        metadata={
            "time_penalties": [0.4, 0.4, 0.4],
            "confidence_bonuses": [-0.08, 0.05, -0.08],
            "sla_breaches": 2,
            "confidence_history": [1.0, 0.9, 0.1],
            "accuracy_history": [0.0, 0.7, 0.4],
        },
    )

    def assert_float_range(obj):
        if isinstance(obj, dict):
            for value in obj.values():
                assert_float_range(value)
        elif isinstance(obj, list):
            for value in obj:
                assert_float_range(value)
        elif isinstance(obj, float):
            assert 0.0 < obj < 1.0

    assert_float_range(result)
