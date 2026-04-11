---
title: Nexdesk Ticket Triage
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
---

# NexDesk

NexDesk is an OpenEnv environment for training and evaluating agents on a real IT helpdesk workflow: triaging support tickets under time pressure, routing them to the right team, drafting a professional first response, and proposing concrete resolution steps.

The environment is designed around work humans actually do in internal IT and support operations. It includes SLA pressure, queue load, confidence calibration, and a batch crisis mode to make the decision problem feel closer to production helpdesk work than a simple text classifier.

## Why This Benchmark Matters

NexDesk is built to test whether an agent can behave like an operations teammate rather than a label predictor.

In real internal support environments, the hard part is not only identifying the category of a ticket. The agent must decide how urgent the problem is, understand business impact, send the work to the correct team, communicate clearly with stressed users, and stay useful during outages when multiple high-severity tickets arrive at once.

That is the core idea behind NexDesk: evaluate calibrated operational decision-making under SLA pressure.

## Motivation

Many agent benchmarks cover general reasoning, browsing, or coding. Fewer focus on operational support work where the agent must be correct, fast, and appropriately calibrated. Helpdesk triage is a useful evaluation target because it combines:

- classification
- routing
- prioritization under urgency
- structured action generation
- human-facing communication quality

## Tasks

The environment includes 4 tasks with increasing difficulty:

1. `ticket_classify`
Classify a ticket into `priority` and `category`.

2. `ticket_route`
Classify the ticket, route it to the correct team, then identify the primary affected system.

3. `ticket_resolve`
Run a full workflow: classify, route, identify the affected system, draft a first response, and propose resolution steps plus an SLA estimate.

4. `crisis_surge`
Handle a 10-ticket production surge where critical tickets must be prioritized ahead of lower-severity work.

## What Makes It Distinct

- multi-step workflow instead of one-shot classification
- explicit SLA pressure and queue-load context
- confidence calibration bonus and penalty
- user-facing response quality plus backend routing decisions in the same benchmark
- `crisis_surge`, a batch outage scenario that forces prioritization under pressure

## Action Space

Agents send structured actions to `POST /step` using the following fields:

- `session_id`: current episode id
- `priority`: `low | medium | high | critical`
- `category`: `network | hardware | software | access | security | other`
- `team`: `helpdesk | network-ops | sysadmin | security | dev`
- `affected_system`: free-text system or device name
- `first_response`: free-text response to the user
- `resolution_steps`: list of free-text remediation steps
- `sla_hours`: integer estimate from `0` to `168`
- `confidence`: float from `0.0` to `1.0`
- `action_type`: `classify | respond | resolve | delegate | escalate`
- `reasoning`: optional free-text reasoning

Different tasks and steps use different subsets of this schema.

## Observation Space

Each observation contains ticket details and episode state:

- `ticket_id`, `subject`, `description`, `submitter`, `department`, `submitted_at`
- `task`, `step`, `max_steps`, `session_id`
- `last_reward`, `message`
- `sla_deadline_minutes`, `queue_depth`, `stress_level`
- `org_context`
- `similar_tickets`
- `knowledge_hints`
- `batch_info` for crisis mode

The `GET /state` endpoint returns current episode progress, cumulative reward, SLA breach count, and calibration history.

## Reward Design

Rewards are deterministic and strictly bounded inside `(0, 1)` to satisfy OpenEnv validation requirements.

The grader gives partial credit for useful progress rather than only binary success:

- exact and acceptable classification matches
- correct routing and affected-system identification
- response quality and keyword coverage
- resolution-step quality
- SLA estimate accuracy
- confidence calibration bonus or penalty
- time-pressure penalties

This gives dense signal across the trajectory instead of only rewarding the final step.

## Baseline Results

Baseline testing with `Qwen/Qwen2.5-72B-Instruct` produced approximate scores:

- `ticket_classify`: `~0.85`
- `ticket_route`: `~0.78`
- `ticket_resolve`: `~0.65`
- `crisis_surge`: `~0.60`

Random or weak policies score much lower, typically around `0.15–0.25`.

## API

Main endpoints:

- `GET /health`
- `GET /`
- `POST /reset`
- `POST /step`
- `GET /state`
- `GET /tasks`
- `GET /metrics`
- `GET /metrics/roi`
- `GET /schema/action`

Example reset request:

```bash
curl -X POST http://localhost:7860/reset \
  -H "Content-Type: application/json" \
  -d '{"task":"ticket_classify"}'
```

## Setup

### Docker

```bash
docker build -t nexdesk .
docker run -p 7860:7860 nexdesk
```

### Local Development

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn server.app:app --host 0.0.0.0 --port 7860
```

## Baseline Inference

The baseline script is [`inference.py`](/Users/sci_coderamalamicia/Downloads/files-2/inference.py:1). It:

- uses the OpenAI Python client for all LLM calls
- reads `API_BASE_URL` with a default
- reads `MODEL_NAME` with a default
- requires `HF_TOKEN`
- emits the required `[START]`, `[STEP]`, and `[END]` log lines

Run it with:

```bash
export HF_TOKEN=your_token
export ENV_BASE_URL=http://localhost:7860
python3 inference.py
```

Optional overrides:

```bash
export API_BASE_URL=https://router.huggingface.co/v1
export MODEL_NAME=Qwen/Qwen2.5-72B-Instruct
```

## Project Structure

```text
.
├── inference.py
├── models.py
├── client.py
├── openenv.yaml
├── server/
│   ├── app.py
│   ├── environment.py
│   ├── graders.py
│   ├── metrics.py
│   └── tickets.py
└── tests/
```

## Validation

Useful local checks before submission:

```bash
python3 validate_ranges.py
python3 deep_audit.py
python3 validate_deployment.py
python3 -m pytest -q tests/test_score_ranges.py
```

## Why This Is Useful

NexDesk is meant to evaluate whether an agent can do more than classify text. A strong agent must interpret urgency, infer operational impact, route intelligently, communicate clearly with users, and remain calibrated under pressure. That makes it a practical benchmark for enterprise support and workflow automation research.
