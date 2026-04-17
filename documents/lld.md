# Low Level Design (LLD)

## 1. State Management & Sessions

State within `NexDeskEnv` avoids physical database persistence to prioritize RAM speed during extensive LLM loop training. 

**Memory Signature of a Session:**
```python
{
    "session_id": "uuid4_string",
    "task": "ticket_route",
    "tickets": [{...}],
    "current_ticket_idx": 0,
    "ticket": {...},              # The active ticket data payload
    "step": 0,                    # Current step int inside the multi-step flow
    "max_steps": 2,               # Configuration pulled from TASK_CONFIGS
    "done": False,                # Evaluation complete bool
    "total_reward": 0.01,
    "rewards": [],
    "accumulated": {},            # Crucial: Maps dict of aggregated action states across steps
    "start_time": 1713330685.0,   # Epoch time used for elapsed_minutes check
    "last_activity": 1713330685.0,# Used by Garbage Collector
    "sla_deadline_minutes": 30,
    "queue_depth": 14,
    "stress_level": 0.46,
    "confidence_history": [0.85],
    "accuracy_history": [0.80],
    "tickets_resolved": 0,
    "sla_breaches": 0
}
```

The `accumulated` dictionary plays a pivotal role in tasks like `ticket_resolve`. The user LLM only passes Step 1 JSON in step 1, and Step 2 JSON in step 2. The `environment.py` `step()` function artificially patches together `action` inputs over historical steps so that `grade_resolve_step3` receives an `accumulated` dict containing the priority, affected system, first response, and resolution steps together.

## 2. Advanced Mathematical Handlers

### 2.1 Bound Enforcement (`_strict_clamp`)
The OpenEnv validator aggressively crashes if environment float outputs hit exact constraints of `0.0` or `1.0`. All mathematical scoring logic passes through:
```python
def _strict_clamp(score: float) -> float:
    return float(round(max(0.01, min(0.99, float(score))), 4))
```
Rewards strictly reside in the `[0.01, 0.99]` range. At runtime, mathematical ceilings are also applied step by step:
`max_allowed_reward = 0.99 - sess["total_reward"] - (steps_remaining * _EPS)`
This logic ensures that an agent cannot exceed `0.99` across multi-step accumulation.

### 2.2 Confidence Calibration Algorithms
The `_compute_confidence_bonus` measures Mean Absolute Error (MAE) between the user's reported confidence and their actual accuracy. If `MAE <= 0.1`, the response receives a `0.05` float addition. If `MAE > 0.3` and the agent was overconfident (confidence heavily exceeded correctness), a severe penalty evaluates.

### 2.3 SLA Time Mechanics
`_compute_time_penalty(elapsed_minutes, deadline, stress)` applies a gradual penalty logic:
- `elapsed < 50%`: `0` penalty.
- `50% - 100%`: Linear mathematical scaling `0.0` to `0.2`.
- `> 100%`: Breach condition. Applies `20-30%` penalty coupled with the multiplier from the `stress` float. 
Furthermore, the `step()` function permanently debits `0.05` base multiplier from the final payload sequence for every SLA breach recorded in `sess["sla_breaches"]`.

## 3. Background Thread Daemon (Garbage Collector)
Rather than letting broken or incomplete client HTTP calls leak memory globally by building up UUIDs in `_sessions`, the module runs `_start_cleanup_thread()` on instantiation:
```python
t = threading.Thread(target=_loop, daemon=True, name="nexdesk-session-gc")
```
It iterates every 300 real-world seconds. Leveraging standard list-comprehension inside a tight lock `with self._lock:`, it prunes UUIDs where `current_time - sess["last_activity"] > 3600`.

## 4. MCP Server & Validation Endpoints
To satisfy external compliance validators cleanly, the FastAPI `app.py` has statically mocked structures for OpenEnv schema validators. 
- `/metadata` injects specific hardcoded schema documentation definitions.
- `/mcp` hooks an interceptor parsing JSON-RPC `tools/list` schema definitions, satisfying remote inference tests natively.
