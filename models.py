"""
NexDesk Pydantic Models
Typed models for Action, Observation, and State used by the OpenEnv client.
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class NexDeskAction(BaseModel):
    """Action schema for NexDesk environment."""

    session_id: str = Field(..., description="Session ID from reset")

    # Classification fields
    priority: Optional[Literal["low", "medium", "high", "critical"]] = Field(
        None, description="Ticket priority: low, medium, high, critical"
    )
    category: Optional[Literal["network", "hardware", "software", "access", "security", "other"]] = Field(
        None,
        description="Ticket category: network, hardware, software, access, security, other",
    )

    # Routing fields
    team: Optional[Literal["helpdesk", "network-ops", "sysadmin", "security", "dev"]] = Field(
        None,
        description="Assigned team: helpdesk, network-ops, sysadmin, security, dev",
    )
    affected_system: Optional[str] = Field(
        None, description="Primary system affected by the issue", min_length=1
    )

    # Resolution fields
    first_response: Optional[str] = Field(
        None, description="Professional first response to the user", min_length=1
    )
    resolution_steps: Optional[List[str]] = Field(None, description="List of resolution steps")
    sla_hours: Optional[int] = Field(None, description="Estimated hours to resolve", ge=1, le=168)

    # Innovation: Confidence calibration
    confidence: Optional[float] = Field(
        None, description="Agent's confidence in this action (0.0-1.0)", ge=0.01, le=0.99
    )

    # Innovation: Action type for multi-agent scenarios
    action_type: Optional[Literal["classify", "respond", "resolve", "delegate", "escalate"]] = Field(
        None, description="Action type: classify, respond, resolve, delegate, escalate"
    )
    reasoning: Optional[str] = Field(None, description="Optional reasoning for the action", min_length=1)


class NexDeskObservation(BaseModel):
    """Observation schema returned by the environment."""

    # Ticket info
    ticket_id: str
    subject: str
    description: str
    submitter: str
    department: str
    submitted_at: str

    # Episode state
    task: str
    step: int
    max_steps: int
    last_reward: float
    session_id: str
    message: str

    done: bool = Field(default=False)
    reward: Optional[float] = Field(default=None)

    # Innovation: Time pressure fields
    sla_deadline_minutes: Optional[int] = Field(
        None, description="Minutes remaining until SLA breach"
    )
    queue_depth: Optional[int] = Field(None, description="Number of pending tickets in queue")
    stress_level: Optional[float] = Field(
        None, description="Current stress level 0.0-1.0 based on load"
    )

    # Innovation: Organizational context
    org_context: Optional[dict] = Field(
        None, description="Organizational context for richer decision-making"
    )

    # Innovation: Similar historical tickets
    similar_tickets: Optional[List[dict]] = Field(
        None, description="Similar historical tickets for pattern matching"
    )
    knowledge_hints: Optional[Dict[str, List[str]]] = Field(
        None, description="Domain hints that may help the agent troubleshoot faster"
    )
    batch_info: Optional[dict] = Field(
        None, description="Additional batch-processing details for crisis mode"
    )


class NexDeskState(BaseModel):
    """State schema for environment state queries."""

    session_id: str
    task: str
    step: int
    max_steps: int
    done: bool
    total_reward: float
    ticket_id: str
    sla_breaches: Optional[int] = Field(default=None)
    stress_level: Optional[float] = Field(default=None)

    # Innovation: Performance tracking
    confidence_history: Optional[List[float]] = Field(
        None, description="History of confidence scores for calibration"
    )
    accuracy_history: Optional[List[float]] = Field(None, description="History of accuracy scores")


class NexDeskInfo(BaseModel):
    """Additional info returned with step results."""

    step: int
    total_reward: float
    task: str

    # Innovation: Multi-dimensional scores
    score_breakdown: Optional[dict] = Field(None, description="Breakdown of scores by dimension")
    time_penalty: Optional[float] = Field(None, description="Penalty applied due to time pressure")
    confidence_bonus: Optional[float] = Field(
        None, description="Bonus/penalty for confidence calibration"
    )
    sla_penalty: Optional[float] = Field(None, description="Penalty applied after SLA breach")


class StepResult(BaseModel):
    """Complete result from an environment step."""

    observation: NexDeskObservation
    reward: float
    done: bool
    info: NexDeskInfo


class ResetResult(BaseModel):
    """Result from environment reset."""

    observation: NexDeskObservation
    session_id: str


# Enums for validation
VALID_PRIORITIES = ["low", "medium", "high", "critical"]
VALID_CATEGORIES = ["network", "hardware", "software", "access", "security", "other"]
VALID_TEAMS = ["helpdesk", "network-ops", "sysadmin", "security", "dev"]
VALID_ACTION_TYPES = ["classify", "respond", "resolve", "delegate", "escalate"]
