# NexDesk Ticket Triage - Architecture & UML

## Architectural Overview

The NexDesk Ticket Triage project encapsulates a robust, stateful simulation environment enclosed within a FastAPI web service, structured to be tightly compliant with the OpenEnv specifications for RLHF (Reinforcement Learning from Human Feedback) agent training.

The system is split into two logical halves:
1. **The Server-side Engine (`server/`)**: A stateless-to-the-outside API that securely locks episodes within a stateful Python object (`NexDeskEnv`). It houses the environment logic, graders, and datasets.
2. **The Client-side Protocol (`client.py`, `inference.py`)**: Responsible for acting as the LLM orchestration layer that retrieves tasks and dispatches JSON schema actions dynamically via the LLM API.

## Core Component Interactions

- **FastAPI Layer (`app.py`)**: Exposes RESTful endpoints (`/reset`, `/step`, `/state`, `/mcp`, `/metrics`) to interact with the environment. It translates HTTP requests validated via Pydantic (`models.py`) down into the simulation logic.
- **Engine Layer (`environment.py`)**: Core game-loop server. Manages the episodic history, tracks the ticking SLA timers, manages stress multipliers dynamically, and updates the step status.
- **Grader Layer (`graders.py`)**: Encapsulates deterministic evaluation logic. These scripts grant partial credit in bounded ranges `(0.01, 0.99)` based on accurate dictionary and keyword hits on the `TICKETS` dataset ground truth.
- **Metrics Engine Layer (`metrics.py`)**: Processes all historical episodic interactions to calculate global platform health, overall SLA breach counts, LLM calibration MAE (Mean Absolute Error), and simulated ROI logic. 

## UML Structure

### 1. System Context Diagram (Mermaid)

```mermaid
graph TD
    A[AI Agent / LLM] -->|HTTP POST JSON Actions| B(NexDesk FastAPI Web Service)
    B -->|Schema Validations| C[Pydantic Models]
    B -->|Triggers Reset/Step| D[NexDeskEnv State Machine]
    D -->|Validates Actions| E[Deterministic Graders]
    E -->|Ground Truth Checks| F[(Tickets Dataset)]
    D -->|SLA & Time Multipliers| D
    D -->|Logs Interactions| G[Business Metrics Store]
    B -->|Returns Observation/Rewards| A
```

### 2. Class Diagram (Mermaid)

```mermaid
classDiagram
    class NexDeskEnv {
        - _sessions : dict
        - _session_timeout_seconds : int
        - _metrics : BusinessMetrics
        + reset(task: str) dict
        + step(session_id: str, action: dict) dict
        + state(session_id: str) dict
        - _compute_reward() float
        - _build_observation() dict
        - _cleanup_expired_sessions()
    }
    
    class Graders {
        + grade_classify(action, ticket) float
        + grade_route_step1(action, ticket) float
        + grade_crisis_ticket(action, ticket, step) float
        + get_score_breakdown(...) dict
        + _compute_time_penalty(...) float
        + _compute_confidence_bonus(...) float
    }

    class BusinessMetrics {
        - _episodes : list
        - _lock : Lock
        + record_episode(...)
        + get_summary() dict
        + get_roi_report(...) dict
    }

    class FastAPIApp {
        <<endpoints>>
        + reset()
        + step()
        + state()
        + mcp()
    }
    
    FastAPIApp --> NexDeskEnv : manages
    NexDeskEnv --> Graders : uses
    NexDeskEnv --> BusinessMetrics : logs state
```

### 3. Episode State Machine UML (Mermaid)

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> ActiveSession : POST /reset (Task Initialize)
    ActiveSession --> ProcessingStep : POST /step (Action Submitted)
    ProcessingStep --> ActiveSession : Action graded, Max Steps not reached
    ProcessingStep --> Terminal : Max Steps reached OR Done=True
    Terminal --> Idle : Metrics logged, episode ended
    ActiveSession --> GarbageCollected : Time Timeout (60 mins idle)
```
