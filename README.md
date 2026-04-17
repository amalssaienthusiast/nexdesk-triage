

# NexDesk — Agentic RAG-Powered IT Ticket Triage System

> **"Every misrouted ticket costs 4 hours. Every SLA breach costs trust. Every hallucinated fix costs credibility."**

A production-grade OpenEnv environment for training AI agents on real-world IT helpdesk triage — featuring **Retrieval-Augmented Generation (RAG)**, **Multi-Agent Escalation Orchestration**, time pressure, confidence calibration, chain-of-thought planning, and crisis surge scenarios that mirror actual helpdesk chaos.

---

## Table of Contents

- [Why NexDesk?](#why-nexdesk)
- [Architecture Overview](#architecture-overview)
- [Key Innovations](#key-innovations)
- [Tasks](#tasks)
- [RAG Knowledge Base Integration](#rag-knowledge-base-integration)
- [Multi-Agent Orchestrator](#multi-agent-orchestrator)
- [Reward & Grading System](#reward--grading-system)
- [API Reference](#api-reference)
- [Observation Space](#observation-space)
- [Action Space](#action-space)
- [Dashboard & Monitoring](#dashboard--monitoring)
- [Setup & Deployment](#setup--deployment)
- [Project Structure](#project-structure)
- [Baseline Results](#baseline-results)
- [Evaluation Criteria](#evaluation-criteria)
- [License & Author](#license--author)

---

## Why NexDesk?

### The Problem

Working in IT support, I noticed a pattern: 30-40% of tickets get bounced between teams before reaching the right person. A "simple" password reset becomes a 6-hour odyssey. A critical server outage sits in the wrong queue while revenue bleeds at $12,000/minute.

### The Gap

No OpenEnv environment addresses IT operations. Customer support, ticket triage, SLA management — these are real problems affecting millions of workers daily. NexDesk fills this gap with a complete simulation of enterprise helpdesk workflows.

### The Innovation

Unlike simple classification tasks, NexDesk simulates the *pressure* and *intelligence* of real helpdesk work:

| Feature | What It Does |
|---------|-------------|
| **RAG Knowledge Base** | Agent searches a 55-article IT knowledge base before resolving tickets — grounding answers in real procedures instead of hallucinating |
| **Multi-Agent Escalation** | L1 Dispatcher → L2 Specialist handoff with ping-pong penalty detection and correct-routing validation |
| **Chain-of-Thought Planning** | Agent must reason about priority, impact, and affected systems before proposing actions |
| **Time Pressure** | Ticking SLA clocks that penalize slow decisions with stress multipliers |
| **Crisis Surge** | 10 tickets flood in during an outage — tests prioritization under real pressure |
| **Confidence Calibration** | Agents report confidence (0-1). Well-calibrated = bonus. Overconfident + wrong = penalty |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     NexDesk Agentic System                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  LLM Agent   │───▶│  RAG Search  │───▶│  Knowledge Base  │  │
│  │  (Qwen 72B)  │    │  (TF-IDF)    │    │  (55 Articles)   │  │
│  │  + CoT Plan  │    └──────────────┘    └──────────────────┘  │
│  └──────┬───────┘                                               │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  Environment │───▶│  Multi-Agent │───▶│  L2 Specialists  │  │
│  │  (NexDeskEnv)│    │ Orchestrator │    │  network-ops     │  │
│  │  SLA + Time  │    │  L1 → L2     │    │  sysadmin        │  │
│  │  Pressure    │    │  Ping-pong   │    │  security        │  │
│  └──────┬───────┘    │  Detection   │    │  dev             │  │
│         │            └──────────────┘    │  helpdesk        │  │
│         ▼                                └──────────────────┘  │
│  ┌──────────────┐    ┌──────────────┐                          │
│  │   Graders    │───▶│  Dashboard   │                          │
│  │  Deterministic│    │  Live TUI +  │                          │
│  │  (0.01-0.99) │    │  REST API    │                          │
│  └──────────────┘    └──────────────┘                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Data Flow:**
1. Agent receives ticket observation with context (SLA, queue depth, similar tickets)
2. Agent optionally searches the Knowledge Base (RAG) for grounded resolution procedures
3. Agent reasons via Chain-of-Thought and produces a structured JSON action
4. Environment grades the action using deterministic graders with partial credit
5. Multi-Agent Orchestrator tracks escalation quality and applies reward modifiers
6. Dashboard displays real-time session metrics, heatmaps, and escalation flows

---

## Key Innovations

### 1. RAG Knowledge Base Integration

The agent doesn't hallucinate — it **searches a 55-article IT knowledge base** before proposing resolution steps. This is a true RAG (Retrieval-Augmented Generation) pipeline:

**Search Engine:** TF-IDF with multi-signal boosting:
- **Term Frequency**: Standard TF-IDF scoring across tokenized article content
- **Title Match Boost** (+2.0): Direct match on article title
- **Category Match Boost** (+1.0): Article category matches query context
- **Tag Overlap Boost** (+0.8 per tag): Keyword tag intersection

**KB Coverage** (55 articles across 6 domains):

| Category | Articles | Example Topics |
|----------|----------|---------------|
| Network | 12 | DNS troubleshooting, VPN configuration, firewall rules |
| Hardware | 8 | Printer repair, laptop diagnostics, dock setup |
| Software | 10 | Office 365 issues, browser crashes, OS updates |
| Access | 9 | Password resets, MFA setup, SSO configuration |
| Security | 8 | Phishing response, malware containment, incident playbooks |
| General | 8 | Onboarding, escalation procedures, SLA guidelines |

**Reward Integration:**
- Searching KB deducts 2 minutes from SLA (realistic cost of knowledge lookup)
- Resolution steps that reference KB article titles receive a **+0.03 grading bonus**
- KB results are injected directly into the LLM prompt with relevance scores

---

### 2. Multi-Agent Escalation Orchestrator

Enterprise IT doesn't have one agent — it has **tiers**. NexDesk simulates this with a full L1→L2 topology:

```
┌────────────────────┐
│   L1 Dispatcher    │  ← All tickets start here
│   NexDesk-L1       │
└────────┬───────────┘
         │ escalate/delegate
         ▼
┌────────────────────────────────────────────┐
│              L2 Specialists                 │
├──────────┬──────────┬──────────┬───────────┤
│ network- │ sysadmin │ security │    dev    │
│   ops    │          │          │           │
└──────────┴──────────┴──────────┴───────────┘
```

**Correct Routing Map:**

| Ticket Category | Correct L2 Team |
|----------------|-----------------|
| network | network-ops |
| hardware | sysadmin |
| software | dev |
| access | sysadmin |
| security | security |
| other | helpdesk |

**Ping-Pong Detection:**
- First escalation: No penalty (if routed correctly)
- Second escalation (bounce): **-15% reward penalty**
- Third+ escalation: **-30% cumulative penalty** (max)
- Reward modifier floor: 0.3 (never fully zeroed out)

**Metrics Tracked:**
- Escalation accuracy (was the right L2 team selected?)
- Bounce count per session
- Per-agent tickets handled and escalation rates

---

### 3. Chain-of-Thought (CoT) Planning

The agent is required to **think before acting**. Every response must begin with a `plan` field:

```json
{
  "plan": "This ticket describes a VPN disconnection issue affecting a remote worker. Impact: single user blocked. No revenue impact mentioned but user is frustrated. Priority should be MEDIUM (workaround exists - can use local resources). Category: NETWORK (VPN infrastructure). Team: NETWORK-OPS (VPN tunnel management).",
  "priority": "medium",
  "category": "network",
  "team": "network-ops"
}
```

The plan field is stripped before environment submission — it's purely for reasoning quality improvement.

---

### 4. Time Pressure System

```
Elapsed Time    │  Penalty Applied
────────────────┼──────────────────
< 10% of SLA   │  0% (grace period)
10-50% of SLA  │  0-4% (gentle ramp)
50-100% of SLA │  4-20% (accelerating)
> 100% of SLA  │  20-35% + stress multiplier
```

**Stress multiplier:** High queue depth increases time penalty by up to 50%.

---

### 5. Confidence Calibration

Agents optionally report confidence. The system uses Expected Calibration Error (ECE) inspired scoring:

| Calibration | Bonus/Penalty |
|-------------|---------------|
| confidence ≈ accuracy (±0.1) | +5% bonus |
| Slightly off (±0.2) | +2% bonus |
| Overconfident (confidence >> accuracy) | -8% penalty |
| Underconfident (accuracy >> confidence) | -3% penalty |

**Why:** Knowing *when* to escalate is as important as knowing *what* to do.

---

### 6. Crisis Surge Mode

10 tickets flood in during a simulated production outage:
- Tickets arrive sorted by severity (critical first)
- Stress level (0.0-1.0) decreases as you resolve tickets
- 30% chance of a new ticket arriving each step
- **Bonus for handling critical tickets in steps 1-3** (+0.02)
- **Bonus for handling high tickets in steps 4-6** (+0.01)

---

### 7. Autonomous Error Discovery & Iterative Escalation (AEDI)

> *"Most helpdesk systems wait for users to report problems. AEDI proactively detects unknown error patterns from logs and tickets, auto-classifies them, raises new issues, notifies the helpdesk, and iteratively re-handles unresolved ones."*

**Architecture:**

```
  Logs + Tickets
       │
       ▼
  ┌──────────────────────┐
  │  Anomaly Detector    │  Fingerprint + dedup + known-pattern filter
  │  (12 known patterns) │  → only NOVEL errors pass through
  └──────────┬───────────┘
             │
             ▼
  ┌──────────────────────┐
  │  Heuristic Classifier│  Category (6 types) + Severity (4 levels)
  │  (zero LLM cost)     │  + auto-generated title + suggested action
  └──────────┬───────────┘
             │
             ▼
  ┌──────────────────────┐
  │  Iteration Engine    │  4-cycle escalation ladder:
  │                      │  1. Re-classify (bump severity)
  │                      │  2. Retry (alternative strategy)
  │                      │  3. Escalate to human
  │                      │  4. Close + post-mortem
  └──────────┬───────────┘
             │
             ▼
  ┌──────────────────────┐
  │  Helpdesk Notifier   │  Dashboard alerts + event feed
  │  (ring buffer)       │  + real-time TUI banners
  └──────────────────────┘
```

**Run the standalone demo:**

```bash
python demo_innovation.py
```

**Sample output:**

```
  PHASE 1: ERROR DISCOVERY
  [NOVEL] AEDI-5d72298b — CRITICAL kernel panic detected
  [KNOWN/SKIP] disk full (already in KB)
  [NOVEL] AEDI-d368237c — WiFi issue on Floor 3

  PHASE 3: ITERATIVE ESCALATION
  [1] RE-CLASSIFY (severity: MEDIUM → HIGH)
  [2] RETRY (alternative L2 diagnostic)
  [3] ESCALATE TO HUMAN
```

**API Endpoints:**

```bash
# Ingest a log line
curl -X POST http://localhost:7860/innovation/ingest \
  -d '{"source": "log", "text": "FATAL: kernel panic at 0xDEAD"}'

# Check pipeline status
curl http://localhost:7860/innovation/status

# Iterate on a flagged issue
curl -X POST http://localhost:7860/innovation/iterate \
  -d '{"ticket_id": "AEDI-5d72298b", "reason": "agent_low_confidence"}'
```

---

### 8. Business Rule Automation Engine

> *"Automation is a powerful capability in ticket management. Configuring business rules and automated workflows eliminates repetitive manual tasks, reduces errors, and speeds up response."*

The system includes a fully auditable automation rules engine (`server/automation.py`) with 6 built-in rules that orchestrate the IT ticket lifecycle without human intervention:

1. **Auto-Assignment by Category:** Automatically routes tickets to the correct L2 team on creation.
2. **Workload Balancing:** If a team is overloaded (>5 active tickets), new issues are dynamically re-routed to the least-loaded team.
3. **Auto-Escalation:** Identifies stale tickets exceeding safe thresholds and bumps their priority.
4. **SLA Breach Alerts:** Triggers high-priority notifications when critical or high tickets pass their open-time limits.
5. **Auto-Closure (Inactive):** Closes low/medium priority tickets inactive for 7+ days.
6. **Auto-Reply Acknowledgment:** Synthesizes context-aware first responses based on ticket priority and expected SLA.

Every automated action is captured in an audit log with tracking of the entity state before and after execution.

**API Endpoints:**

```bash
# Process a ticket through the automation rules
curl -X POST http://localhost:7860/automation/process \
  -H "Content-Type: application/json" \
  -d '{"ticket": {"id": "TKT-001", "category": "network", "priority": "high", "status": "new", "ack_sent": false, "sla_breach_notified": false}}'

# View active rules and execution statistics
curl http://localhost:7860/automation/rules

# Retrieve the automation audit log
curl http://localhost:7860/automation/audit
```

---

## Tasks

### Task 1: `ticket_classify` (Easy, 1 step)

**Goal:** Classify priority and category.

```json
Input:  "URGENT: VPN keeps disconnecting every 5 minutes"
Output: { "priority": "medium", "category": "network", "confidence": 0.85 }
```

**Scoring:** priority (0.5) + category (0.5) = 0.99 max

---

### Task 2: `ticket_route` (Medium, 2 steps)

**Goal:** Classify + route to correct team + identify affected system.

| Step | Fields | Max Score |
|------|--------|-----------|
| 1 | priority, category, team | 0.81 |
| 2 | affected_system | 0.15 |

---

### Task 3: `ticket_resolve` (Hard, 3 steps)

**Goal:** Full resolution pipeline with RAG-grounded answers.

| Step | Fields | Max Score | RAG |
|------|--------|-----------|-----|
| 1 | priority, category, team | 0.41 | — |
| 2 | affected_system, first_response | 0.31 | — |
| 3 | resolution_steps, sla_hours | 0.26 + 0.03 KB bonus | ✅ KB search before this step |

**Response Quality Rubric:**
- **Empathy** (20%): Acknowledgment, apology, understanding
- **Clarity** (30%): Structured formatting, numbered steps, appropriate length
- **Actionability** (50%): Concrete next steps, technical specificity

---

### Task 4: `crisis_surge` (Hard, 10 steps) — *Novel*

**Goal:** Handle 10-ticket surge during production outage.

**Unique mechanics:**
- Tickets arrive sorted by severity (critical first)
- Stress level decreases as you resolve tickets
- 30% chance of new ticket arriving each step
- Bonus for correct crisis prioritization

---

## RAG Knowledge Base Integration

### How It Works

```
Agent                    Environment                Knowledge Base
  │                          │                           │
  │ action_type: search_kb   │                           │
  │ query: "VPN disconnect"  │                           │
  │─────────────────────────▶│                           │
  │                          │  TF-IDF + title/tag boost │
  │                          │──────────────────────────▶│
  │                          │                           │
  │                          │◀──────────────────────────│
  │                          │  Top 3 results            │
  │                          │  (title, snippet, score)  │
  │◀─────────────────────────│                           │
  │                          │                           │
  │  Uses KB results in      │                           │
  │  resolution_steps        │                           │
  │─────────────────────────▶│                           │
  │                          │  +0.03 bonus if KB-       │
  │                          │  grounded resolution      │
```

### Example KB Search Result

```json
{
  "id": "KB-NET-003",
  "title": "VPN Tunnel Troubleshooting Guide",
  "category": "network",
  "content_snippet": "Step 1: Verify VPN client version matches server requirements. Step 2: Check MTU settings (recommended: 1400). Step 3: Flush DNS cache...",
  "relevance_score": 0.87,
  "tags": ["vpn", "network", "tunnel"]
}
```

---

## Multi-Agent Orchestrator

### Escalation Flow

1. All tickets start at **L1 Dispatcher**
2. If the agent determines L2 expertise is needed, it sends `action_type: "escalate"`
3. The orchestrator validates the routing against the correct-routing map
4. If the ticket bounces back (ping-pong), a **15% reward penalty** is applied
5. Reward modifier is applied to the final step score

### API Fields

```json
{
  "action_type": "escalate",
  "team": "network-ops",
  "category": "network",
  "reason": "Complex VPN tunnel issue requiring infrastructure access"
}
```

### Dashboard Data

The `/api/dashboard` endpoint includes live multi-agent state:

```json
{
  "multi_agent": {
    "session-id": {
      "l1_dispatcher": { "tickets_handled": 5, "escalations_sent": 2 },
      "l2_specialists": {
        "network-ops": { "tickets_handled": 1, "escalations_received": 1 }
      },
      "total_bounces": 0,
      "total_penalty": 0.0,
      "reward_modifier": 1.0
    }
  }
}
```

---

## Reward & Grading System

### Deterministic Graders

All scores are strictly clamped to `(0.01, 0.99)` to comply with OpenEnv validator requirements.

**Scoring Components:**

| Component | Weight | Description |
|-----------|--------|-------------|
| Field Accuracy | ~60% | Exact match = full credit, acceptable alternative = partial |
| Response Quality | ~20% | Empathy + Clarity + Actionability rubric |
| Keyword Coverage | ~15% | TF-IDF-based resolution keyword matching |
| SLA Accuracy | ~5% | Predicted vs expected SLA hours |

**Advanced Modifiers:**

| Modifier | Effect |
|----------|--------|
| Time Penalty | -0% to -35% based on SLA deadline proximity |
| Confidence Bonus | -8% to +5% based on calibration quality |
| Multi-Agent Modifier | 0.3x to 1.0x based on escalation accuracy |
| KB Adoption Bonus | +0.03 when resolution references KB articles |
| Anti-Stuffing | 0.3x to 1.0x penalty for keyword-dump responses |

### Final Reward Formula

```
reward = base_reward × (1 - time_penalty) × multi_agent_modifier + confidence_bonus
```

---

## API Reference

### Core Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Environment info and version |
| GET | `/health` | Health check with feature list |
| GET | `/metadata` | OpenEnv metadata manifest |
| GET | `/schema` | Full action schema documentation |
| POST | `/reset` | Start episode: `{"task": "ticket_classify"}` |
| POST | `/step` | Take action with `session_id` |
| GET | `/state?session_id=...` | Episode state |
| GET | `/tasks` | List all 4 tasks with configs |
| GET | `/metrics` | Aggregated business metrics |
| GET | `/metrics/roi?monthly_volume=N` | ROI projection |

### Dashboard Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dashboard` | Live session data + multi-agent state |
| GET | `/api/dashboard/ticket/{session_id}` | Detailed drill-down |
| GET | `/api/dashboard/heatmap` | Category × Priority heatmap |
| GET | `/api/report/generate` | Full performance + ROI report |

### RAG & Multi-Agent Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/step` | `action_type: "search_kb"` triggers KB search |
| POST | `/step` | `action_type: "escalate"` triggers L1→L2 handoff |

### AEDI Innovation Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/innovation/status` | Full AEDI pipeline status: discoveries, iterations, alerts |
| POST | `/innovation/ingest` | Ingest a log line or ticket text for anomaly detection |
| POST | `/innovation/iterate` | Run the next escalation cycle on a flagged AEDI issue |

### Example Flow

```bash
# 1. Reset
curl -X POST http://localhost:7860/reset \
  -H "Content-Type: application/json" \
  -d '{"task": "ticket_resolve"}'

# 2. Step 1: Classify
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc-123",
    "priority": "high",
    "category": "network",
    "team": "network-ops",
    "confidence": 0.85
  }'

# 3. RAG Search (optional, before step 3)
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc-123",
    "action_type": "search_kb",
    "query": "VPN disconnection troubleshooting"
  }'

# 4. Step 3: Resolution with KB-grounded answer
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc-123",
    "resolution_steps": ["Per KB-NET-003: Check VPN client version", "Verify MTU=1400", "Flush DNS"],
    "sla_hours": 4
  }'
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
  "task": "ticket_resolve",
  "step": 2,
  "max_steps": 3,
  "last_reward": 0.35,
  "session_id": "uuid-...",
  "message": "Step 2 done. Reward: 0.3500. SLA remaining: ~18 min.",

  "sla_deadline_minutes": 20,
  "queue_depth": 15,
  "stress_level": 0.42,
  "current_agent_role": "L1_Dispatcher",

  "org_context": {
    "total_employees": 500,
    "teams": { "network-ops": { "capacity": 4 }, "sysadmin": { "capacity": 6 } },
    "current_oncall": "network-ops",
    "recent_incidents": ["database-slowness", "vpn-issues"]
  },
  "similar_tickets": [
    { "id": "TKT-010", "subject": "VPN disconnects", "category": "network", "priority": "medium", "team": "network-ops" }
  ],
  "knowledge_hints": {
    "common_causes": ["DNS misconfiguration", "DHCP lease expiry", "VPN tunnel instability"],
    "recommended_checks": ["Check connectivity scope", "Review router status", "Inspect VPN logs"]
  },
  "knowledge_results": [
    { "id": "KB-NET-003", "title": "VPN Troubleshooting Guide", "relevance_score": 0.87, "content_snippet": "..." }
  ],
  "multi_agent": {
    "l1_dispatcher": { "tickets_handled": 3 },
    "total_bounces": 0,
    "reward_modifier": 1.0
  }
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
  "resolution_steps": ["step1", "step2", "..."],
  "sla_hours": 4,
  "confidence": 0.85,
  "action_type": "search_kb|escalate|delegate (optional)"
}
```

---

## Dashboard & Monitoring

### Rich TUI (Terminal Interface)

The `rich_inference.py` script provides a professional monochrome terminal dashboard with:

- Real-time ticket panel with SLA countdown
- Step-by-step reward breakdown with visual bars
- KB search results with relevance scores
- Task summary tables with pass/fail gates
- Final scoreboard and report generation

### Live Dashboard API

The `/api/dashboard` endpoint streams live data for frontend visualization:

- Active/completed session counts
- Per-session reward curves
- SLA breach tracking
- Multi-agent escalation flow graphs
- KB usage statistics

### Auto-Generated Reports

After each run, `final_report.json` is automatically generated with:

```json
{
  "timestamp": "2026-04-17T...",
  "performance_summary": { "total_episodes": 4, "avg_reward": 0.72 },
  "roi_analysis": { "monthly_savings_usd": 18500, "sla_compliance_rate": 0.94 }
}
```

---

## Ticket Dataset

30 diverse tickets covering real IT scenarios:

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
| TKT-011–030 | Additional scenarios (20 more variants) | various | various |

Each ticket includes:
- Ground truth labels with acceptable alternatives (partial credit)
- Expected keywords for response and resolution scoring
- Realistic SLA expectations based on priority
- Anti-stuffing detection to penalize keyword dumps

---

## Setup & Deployment

### Docker (Recommended for HF Spaces)

```bash
docker build -t nexdesk .
docker run -p 7860:7860 nexdesk
curl http://localhost:7860/health
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start the environment server
uvicorn server.app:app --host 0.0.0.0 --port 7860

# In a separate terminal, run the agent
export HF_TOKEN=your_huggingface_token
export ENV_BASE_URL=http://localhost:7860
python3 rich_inference.py
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `HF_TOKEN` | Yes | — | Hugging Face API token for LLM inference |
| `API_BASE_URL` | No | `https://router.huggingface.co/v1` | LLM API base URL |
| `ENV_BASE_URL` | No | `http://localhost:7860` | NexDesk environment URL |

---

## Project Structure

```
nexdesk-ticket-triage/
├── server/
│   ├── __init__.py           # Package exports
│   ├── app.py                # FastAPI (18+ endpoints, dashboard, SSE, AEDI)
│   ├── environment.py        # Core env logic + RAG/multi-agent integration
│   ├── graders.py            # Deterministic graders with KB bonus
│   ├── metrics.py            # Business metrics & ROI projections
│   ├── tickets.py            # Dataset (30 tickets with ground truth)
│   ├── knowledge_base.py     # 55-article KB with TF-IDF search engine
│   ├── multi_agent.py        # L1/L2 orchestrator + ping-pong detection
│   ├── automation.py         # Business rules engine, auto-assignment, auto-escalation
│   ├── flagging.py           # Alert/flag rule engine
│   └── innovation/           # AEDI Innovation Module
│       ├── __init__.py       # Package exports
│       ├── discovery.py      # Anomaly detection + fingerprinting + classification
│       ├── iteration.py      # 4-cycle escalation ladder (re-classify → escalate → post-mortem)
│       └── notifier.py       # Alert ring-buffer + dashboard event integration
├── dashboard/                # Static dashboard files
├── models.py                 # Pydantic schemas
├── client.py                 # Typed Python client
├── inference.py              # Basic inference script
├── rich_inference.py         # Production TUI with RAG + CoT + reporting
├── demo_innovation.py        # Standalone AEDI demo (no server needed)
├── openenv.yaml              # OpenEnv manifest
├── pyproject.toml            # Package config
├── requirements.txt          # Dependencies
├── Dockerfile                # Container build
├── docker-compose.yml        # Compose config
└── README.md                 # This file
```

---

## Baseline Results

Tested with `Qwen/Qwen2.5-72B-Instruct` via Hugging Face Inference API:

| Task | Avg Reward | Total Reward | Result |
|------|-----------|-------------|--------|
| ticket_classify | ~0.26–0.51 | 0.02–0.51 | ✅ PASS |
| ticket_route | ~0.22–0.36 | 0.45–0.72 | ✅ PASS |
| ticket_resolve | ~0.05–0.14 | 0.15–0.43 | ✅ PASS |
| crisis_surge | ~0.06–0.08 | 0.63–0.79 | ✅ PASS |

**Key observations:**
- Category and team classification: ~95% accuracy (0.99 scores)
- Priority classification: ~60% accuracy (variance across ticket types)
- RAG-grounded resolutions score higher than hallucinated ones
- Multi-agent escalation improves routing accuracy on ambiguous tickets

---

## Evaluation Criteria

| Criterion | How NexDesk Addresses It |
|-----------|--------------------------|
| **Real-world utility** | IT triage is a $10B+ industry pain point |
| **Task progression** | Easy → Medium → Hard → Crisis (4 difficulty levels) |
| **Dense rewards** | Partial credit at every step with multi-dimensional scoring |
| **Deterministic grading** | All graders return scores in (0.01, 0.99) — strictly compliant |
| **Novel mechanics** | Time pressure, confidence calibration, crisis surge |
| **RAG integration** | True knowledge-grounded resolution (not hallucination) |
| **Multi-agent** | L1→L2 escalation with ping-pong penalty and routing validation |
| **Business value** | ROI metrics, cost projections, SLA compliance tracking |
| **Production quality** | Docker deployment, live dashboard, automated reporting |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Environment Server | FastAPI + Uvicorn |
| LLM Inference | Qwen2.5-72B-Instruct (HF Inference API) |
| Knowledge Base | Custom TF-IDF search engine (zero dependencies) |
| Terminal UI | Rich (Python) |
| Deployment | Docker + Hugging Face Spaces |
| Dashboard | Static HTML + REST API + SSE |

---

## License

MIT

---

## Author

Built by **amalscicoder** for the OpenEnv Competition.

*"The best helpdesk agent isn't the one who knows everything — it's the one who knows what they don't know, and searches the knowledge base before guessing."*
