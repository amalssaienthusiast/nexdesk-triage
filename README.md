---
title: Nexdesk Ticket Triage
emoji: 🚀
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
---

# NexDesk — IT Ticket Triage OpenEnv Environment

> **"Every misrouted ticket costs 4 hours. Every SLA breach costs trust."**

A production-grade OpenEnv environment for training AI agents on real-world IT helpdesk triage — featuring time pressure, confidence calibration, and crisis surge scenarios that mirror actual helpdesk chaos.

---

## Why NexDesk?

**The Problem I Saw:**
Working in IT support, I noticed a pattern: 30-40% of tickets get bounced between teams before reaching the right person. A "simple" password reset becomes a 6-hour odyssey. A critical server outage sits in the wrong queue while revenue bleeds.

**The Gap:**
No OpenEnv environment addresses IT operations. Customer support, ticket triage, SLA management — these are real problems affecting millions of workers daily. NexDesk fills this gap.

**The Innovation:**
Unlike simple classification tasks, NexDesk simulates the *pressure* of real helpdesk work:
- Ticking SLA clocks that penalize slow decisions
- Crisis surges where 10 tickets flood in during an outage
- Confidence calibration that rewards honest self-assessment

---

## What Makes NexDesk Different

| Feature | Why It Matters |
|---------|----------------|
| **Time Pressure** | Real helpdesks have SLAs. Agents learn speed-accuracy tradeoffs. |
| **Crisis Surge Mode** | 10-ticket batch during simulated outage. Tests prioritization under stress. |
| **Confidence Calibration** | Agents report confidence (0-1). Well-calibrated = bonus. Overconfident + wrong = penalty. |
| **Multi-Dimensional Scoring** | Not just "right/wrong" — scores for empathy, clarity, technical accuracy. |
| **Business Metrics** | ROI projections: "This agent saves $X/month, reduces SLA breaches by Y%." |

---

## Tasks

### Task 1: `ticket_classify` (Easy, 1 step)
**Goal:** Classify priority and category.

```
Input:  "URGENT: VPN keeps disconnecting every 5 minutes"
Output: { "priority": "medium", "category": "network", "confidence": 0.85 }
```

**Scoring:** priority (0.5) + category (0.5) = 1.0 max

---

### Task 2: `ticket_route` (Medium, 2 steps)
**Goal:** Classify + route to correct team + identify affected system.

| Step | Fields | Max Score |
|------|--------|-----------|
| 1 | priority, category, team | 0.85 |
| 2 | affected_system | 0.15 |

---

### Task 3: `ticket_resolve` (Hard, 3 steps)
**Goal:** Full resolution pipeline.

| Step | Fields | Max Score |
|------|--------|-----------|
| 1 | priority, category, team | 0.45 |
| 2 | affected_system, first_response | 0.30 |
| 3 | resolution_steps, sla_hours | 0.25 |

**Response Quality:** Scored on keyword coverage (empathy words, technical terms).

---

### Task 4: `crisis_surge` (Hard, 10 steps) — *Novel*
**Goal:** Handle 10-ticket surge during production outage.

**Unique mechanics:**
- Tickets arrive sorted by severity (critical first)
- Stress level (0.0-1.0) decreases as you resolve tickets
- 30% chance of new ticket arriving each step
- Bonus for handling critical tickets in steps 1-3

**Why this matters:** Real outages don't come one ticket at a time.

---

## Innovations Deep Dive

### Time Pressure System

```python
# Penalty increases as SLA deadline approaches
if elapsed < 50% of SLA:  penalty = 0%
if elapsed 50-100%:       penalty = 0-20% (linear)
if elapsed > 100%:        penalty = 20-30% + stress multiplier
```

**Business reality:** A ticket resolved in 5 minutes vs 55 minutes has the same "correctness" but vastly different business value.

### Confidence Calibration

Agents can optionally report confidence:
```json
{ "priority": "high", "category": "network", "confidence": 0.9 }
```

| Calibration | Bonus/Penalty |
|-------------|---------------|
| confidence ≈ accuracy (±0.1) | +5% bonus |
| confidence >> accuracy (overconfident) | -10% penalty |
| accuracy >> confidence (underconfident) | -3% penalty |

**Why:** Knowing *when* to escalate is as important as knowing *what* to do.

### Business Metrics Endpoint

```bash
GET /metrics/roi?monthly_volume=1000
```

Returns:
```json
{
  "monthly_savings_usd": 18500,
  "automation_rate": 0.78,
  "sla_compliance_rate": 0.94,
  "roi_percentage": 74.2
}
```

---

## Ticket Dataset

10 diverse tickets covering real scenarios:

| ID | Scenario | Priority | Category |
|----|----------|----------|----------|
| TKT-001 | Laptop can't connect to WiFi before presentation | high | network |
| TKT-002 | Software install request (Figma) | low | software |
| TKT-003 | Email account locked out | medium | access |
| TKT-004 | Wireless mouse stopped working | low | hardware |
| TKT-005 | **PRODUCTION SERVER DOWN** | critical | network |
| TKT-006 | Suspicious login attempts from Tor exit node | critical | security |
| TKT-007 | Floor 3 printer offline (40 users affected) | high | hardware |
| TKT-008 | Database queries extremely slow | high | software |
| TKT-009 | New employee laptop setup | medium | hardware |
| TKT-010 | VPN disconnects every 5 minutes | medium | network |

Each ticket includes:
- Ground truth labels
- Acceptable alternatives (partial credit)
- Expected keywords for response/resolution scoring
- Realistic SLA expectations

---

## API Reference

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Environment info |
| GET | `/health` | Health check with feature list |
| POST | `/reset` | Start episode: `{"task": "ticket_classify"}` |
| POST | `/step` | Take action with `session_id` |
| GET | `/state?session_id=...` | Episode state |
| GET | `/tasks` | List all tasks |
| GET | `/metrics` | Aggregated business metrics |
| GET | `/metrics/roi?monthly_volume=N` | ROI projection |
| GET | `/schema/action` | Action schema documentation |

### Example Flow

```bash
# 1. Reset
curl -X POST http://localhost:7860/reset \
  -H "Content-Type: application/json" \
  -d '{"task": "ticket_classify"}'

# Response includes session_id and ticket observation

# 2. Step
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc-123",
    "priority": "high",
    "category": "network",
    "confidence": 0.85
  }'

# Response includes reward, done flag, score breakdown
```

---

## Observation Space

```json
{
  "ticket_id": "TKT-001",
  "subject": "Cannot connect to the internet",
  "description": "My laptop suddenly stopped connecting...",
  "submitter": "Sarah Johnson",
  "department": "Marketing",
  "submitted_at": "2025-04-07T09:15:00Z",
  "task": "ticket_classify",
  "step": 0,
  "max_steps": 1,
  "last_reward": 0.001,
  "session_id": "uuid-...",
  "message": "Instructions...",
  
  // Innovation fields
  "sla_deadline_minutes": 60,
  "queue_depth": 15,
  "stress_level": 0.42,
  "org_context": { "current_oncall": "network-ops", ... },
  "similar_tickets": [{ "id": "TKT-010", "subject": "VPN issues", "team": "network-ops" }]
}
```

---

## Action Space

```json
{
  "session_id": "required",
  "priority": "low|medium|high|critical",
  "category": "network|hardware|software|access|security|other",
  "team": "helpdesk|network-ops|sysadmin|security|dev",
  "affected_system": "string",
  "first_response": "string (30+ chars for quality scoring)",
  "resolution_steps": ["step1", "step2", ...],
  "sla_hours": 4,
  "confidence": 0.85,  // Optional, between 0 and 1
  "reasoning": "string"  // Optional, for debugging
}
```

---

## Setup

### Docker (Recommended)

```bash
docker build -t nexdesk .
docker run -p 7860:7860 nexdesk
curl http://localhost:7860/health
```

### Local Development

```bash
pip install -r requirements.txt
uvicorn server.app:app --host 0.0.0.0 --port 7860
```

### Run Baseline Inference

```bash
export HF_TOKEN=your_token
export ENV_BASE_URL=http://localhost:7860
python inference.py
```

---

## Baseline Results

Tested with `Qwen/Qwen2.5-72B-Instruct`:

| Task | Score | Notes |
|------|-------|-------|
| ticket_classify | ~0.85 | Strong on clear-cut tickets |
| ticket_route | ~0.78 | Team routing adds complexity |
| ticket_resolve | ~0.65 | Response quality is challenging |
| crisis_surge | ~0.60 | Prioritization under pressure |

Random baseline: 0.15-0.25 per task.

---

## Project Structure

```
nexdesk-ticket-triage/
├── server/
│   ├── __init__.py       # Package exports
│   ├── app.py            # FastAPI (9 endpoints)
│   ├── environment.py    # Core logic + innovations
│   ├── graders.py        # Deterministic graders
│   ├── metrics.py        # Business metrics
│   └── tickets.py        # Dataset (10 tickets)
├── models.py             # Pydantic schemas
├── client.py             # Typed Python client
├── inference.py          # Baseline script
├── openenv.yaml          # Manifest
├── pyproject.toml        # Package config
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Evaluation Criteria Met

| Criterion | How NexDesk Addresses It |
|-----------|--------------------------|
| **Real-world utility** | IT triage is a $10B+ industry pain point |
| **Task progression** | Easy → Medium → Hard → Crisis (4 levels) |
| **Dense rewards** | Partial credit at every step |
| **Deterministic grading** | All graders return scores in (0.001, 0.999) |
| **Novel mechanics** | Time pressure, confidence calibration, crisis surge |
| **Business value** | ROI metrics, cost projections |

---

## Future Extensions

- **Ambiguous tickets** requiring clarifying questions
- **Multi-agent mode** with delegation between specialists
- **Knowledge base construction** from resolved tickets
- **Sentiment analysis** for frustrated users

---

## License

MIT

---

## Author

Built by **amalscicoder** for the OpenEnv Competition.

*"The best helpdesk agent isn't the one who knows everything — it's the one who knows what they don't know."*
