# NexDesk IT Ticket Triage: Comprehensive A-Z Documentation

> **Project Mission:** NexDesk transforms IT Helpdesk operations from a reactive, manual chokepoint into a proactive, intelligent, and autonomous system. Built as a production-grade OpenEnv environment, it trains and evaluates AI agents using advanced concepts such as Retrieval-Augmented Generation (RAG), Multi-Agent Escalation, and Autonomous Discovery.

This document serves as the complete technical manual for the NexDesk codebase mapping to the `files-2` directory structure.

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [Directory Structure Explained](#2-directory-structure-explained)
3. [The Core Environment (OpenEnv)](#3-the-core-environment)
4. [The 4 Evaluation Tasks](#4-the-4-evaluation-tasks)
5. [The Grading & Reward System](#5-the-grading--reward-system)
6. [Core System Modules](#6-core-system-modules)
   - [Retrieval-Augmented Generation (RAG) Knowledge Base](#61-rag-knowledge-base)
   - [Multi-Agent Orchestrator](#62-multi-agent-orchestrator)
   - [Business Automation Engine](#63-business-automation-engine)
7. [The Innovation Module: AEDI](#7-the-innovation-module-aedi)
8. [Inference Clients & Dashboards](#8-inference-clients--dashboards)
9. [Deployment & Setup](#9-deployment--setup)

---

## 1. High-Level Architecture

The system follows a standard Client-Server reinforcement learning architecture via REST APIs, fully supporting the OpenEnv validation spec.

```text
┌─────────────────────────────────┐           ┌────────────────────────────────┐
│           CLIENT                │           │           SERVER               │
│                                 │           │                                │
│  ┌──────────────────────┐       │   HTTP    │  ┌──────────────────────────┐  │
│  │ Qwen-72B LLM Base    │       │──────────▶│  │ FastAPI App (app.py)     │  │
│  └──────────────────────┘       │           │  └────────────┬─────────────┘  │
│  ┌──────────────────────┐       │           │               │                │
│  │ Prompt Builder (CoT) │       │◀──────────│               ▼                │
│  └──────────────────────┘       │           │  ┌──────────────────────────┐  │
│  ┌──────────────────────┐       │           │  │ NexDesk Environment      │  │
│  │ Rich TUI Dashboard   │       │           │  │ (environment.py)         │  │
│  └──────────────────────┘       │           │  └──────┬───────┬──────┬────┘  │
└─────────────────────────────────┘           │         │       │      │       │
                                              │         ▼       ▼      ▼       │
                                              │    ┌──────┐ ┌──────┐ ┌───────┐ │
                                              │    │ RAG  │ │ L1►L2│ │ Rules │ │
                                              │    └──────┘ └──────┘ └───────┘ │
                                              └────────────────────────────────┘
```

---

## 2. Directory Structure Explained

A guided tour of what every file in your repository does:

### Root Level
- **`openenv.yaml`**: The canonical definition file for evaluation environments. Declares to validators that this is a valid environment.
- **`inference.py`**: A minimal baseline agent runner that solves the environment via Hugging Face inference.
- **`rich_inference.py`**: The fully-featured, production-grade agent runner boasting a beautiful multi-panel terminal interface, Chain-of-Thought (CoT) tracking, and live grading.
- **`demo_innovation.py`**: A self-contained simulation proving the standalone capability of the AEDI module.
- **`client.py`**: Typed python client logic for hitting the FastAPI server natively.
- **`models.py`**: The Pydantic data schemas defining expected states and JSON payloads across the system. 
- **`requirements.txt` / `pyproject.toml` / `uv.lock`**: Dependency management chains and lock files.
- **`Dockerfile` / `docker-compose.yml`**: Deployment encapsulation for Hugging Face Spaces.

### `server/` Directory (The Brains)
- **`app.py`**: The FastAPI controller exposing 18+ endpoints defining the environment loops, dashboards, automated metrics, and RAG ingestion.
- **`environment.py`**: The core logic engine (`NexDeskEnv`) that ties grading, progression, ticket transitions, rewards, and SLA time-pressure rules together. 
- **`graders.py`**: Pure, deterministic mathematical evaluation logic to grade each response on a strictly clamped float range from 0.01 to 0.99.
- **`tickets.py`**: The database of mock ticket scenarios and ground-truths evaluating the LLM's performance.
- **`knowledge_base.py`**: The 55-article KB utilizing a custom TF-IDF semantic query engine. 
- **`multi_agent.py`**: Orchestrates state handling for L1 Dispatchers routing to L2 Specialists.
- **`automation.py`**: The Business rules engine automatically triggering escalations, assigning tasks, closing stale tickets, and warning SLA breaches. 
- **`metrics.py` & `flagging.py`**: Business ROI calculators and diagnostic telemetry extractors.

### `server/innovation/` (The AEDI Module)
Autonomous Error Discovery & Iterative Escalation module. 
- **`discovery.py`**: Anomaly detection logic to identify novel vs. known errors dynamically. 
- **`iteration.py`**: A 4-stage unblocking engine designed to retry or escalate deadlocked problems.
- **`notifier.py`**: Hooks telemetry and warnings out to dashboards and UIs.

---

## 3. The Core Environment

The underlying OpenEnv mechanics defined in `server/environment.py`:
- **Step Transitions**: A ticket steps through multiple states (e.g., in a 3-step resolution: *classify* -> *route* -> *resolve*). 
- **State Space**: Information served per step to the agent. Includes ticket descriptions, active SLA timers, queue depth (stress multiplier), similar existing tickets, and organizational capacity.
- **Dynamic Penalties**: `time_penalty` and `sla_breaches` mathematically decay step rewards if the agent relies on excessive routing bounces or fails to solve before SLAs trigger.

---

## 4. The 4 Evaluation Tasks

To prove scalability and emergent reasoning, NexDesk presents the agent with 4 increasing difficulties tracked via `/tasks`:

| Task ID | Difficulty | Steps | Objective |
|---------|---------|-------|-----------|
| `ticket_classify` | Easy | 1 | Accurately label ticket `category` and `priority`. |
| `ticket_route` | Medium | 2 | Same as Task 1, but dynamically routing to an L2 `team` based on the classification and identifying the `affected_system`. |
| `ticket_resolve` | Hard | 3 | Full cycle: Requires searching the RAG KB and generating a multi-step structured resolution with empathy to the user. |
| `crisis_surge` | Very Hard | 10 | Handles 10 overlapping tickets out of order during an evolving outage. Evaluates dynamic prioritization under stress. |

---

## 5. The Grading & Reward System

Located in `server/graders.py`. 
To comply strictly with OpenEnv validation mechanisms, NexDesk does **NOT** use binary `0.0` or `1.0` scores. All scores are bounded between `0.01` and `0.99`. 

**Reward Formula Breakdown:**
1. Base Action Grade (Keyword matching, schema validation)
2. **Time Penalty** (Subtracts percentage if SLA approaches deadline)
3. **Multi-Agent Penalty** (Subtracts 15% to 30% if the ticket ping-pongs between wrong L2 teams repeatedly)
4. **Confidence Calibration Bonus** (Adds ~3% if the LLM accurately expresses its certainty on a given action)
5. **RAG Grounding Bonus** (Adds ~3% if the LLM utilizes specific titles from the KB search into its resolution steps)

---

## 6. Core System Modules

### 6.1 RAG Knowledge Base
**File**: `server/knowledge_base.py`
Instead of hallucinating answers, the agent triggers an `action_type: search_kb`. 
- **Mechanic**: The Environment suspends progression, runs a TF-IDF match with keyword boosting over 55 embedded markdown IT instructions, and feeds snippets back to the prompt schema. The system tracks KB hits for rewarding grounded accuracy.

### 6.2 Multi-Agent Orchestrator
**File**: `server/multi_agent.py`
Simulates realistic enterprise tiering logic natively in code.
- **Mechanic**: L1 acts as dispatcher. Emits `action_type: escalate`. 
If routed to the incorrect team (e.g., Network to Sysadmin), it ping-pongs and creates a negative multiplier penalty.

### 6.3 Business Automation Engine
**File**: `server/automation.py`
Validates that not all resolutions need LLM calls. Built directly into `app.py`.
- **Mechanic**: Automatically parses state to verify rules: _Is load high? Re-balance queue. Is the ticket 7 days old? Auto-close. Is a vital SLA ticking? Emit a Warning template._ 

---

## 7. The Innovation Module (AEDI)

**Location**: `server/innovation/`
The crown jewel of the system.
**Autonomous Error Discovery and Iterative Escalation (AEDI)** acts independently of direct ticket interactions. 

1. **Ingest Engine**: Sucks in raw system `.log` files or generic user errors without formatting.
2. **Anomaly Fingerprinter**: Compares the log against 12 known generic patterns using normalized regex IDs.
3. **Heuristic Filter**: Classifies if the issue is a novel zero-day fault or just a known warning.
4. **Iterative Escalation Ladder**: Takes flagged complex issues, tries re-classifying them -> retrying them via distinct actions -> escalating to humans -> formally closing them with post-mortem logs.

---

## 8. Inference Clients & Dashboards

**The Terminal TUI (`rich_inference.py`)**
A highly synchronized CLI execution model utilizing the `Rich` UI library to draw a live-streaming panel structure. 
- **Chain-of-Thought Enforcement**: Demands the LLM generates a `"plan": "thinking..."` string explaining its action before making state changes. 
- Automatically creates `final_report.json` with ROI metrics and task compliance validation upon completion.

**The FastAPI API Dashboard**
The `/api/dashboard` stream dynamically hooks to frontend components for real-time visualization of queue depth metrics and rule triggers.

---

## 9. Deployment & Setup

For validation and assessment on open platforms like **Hugging Face Spaces**.

### Run Natively
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server.app:app --host 0.0.0.0 --port 7860
```
Run the client against it in another window:
```bash
export HF_TOKEN="your_hugging_face_key"
python3 rich_inference.py
```

### Run using Docker (Preferred for production/Spaces)
```bash
docker build -t nexdesk .
docker run -p 7860:7860 nexdesk
```

Verify the environment is healthy via:
```bash
curl http://localhost:7860/health
```

---

_This comprehensive document confirms the architecture, integrity, scope, and technical superiority of the NexDesk environment for grading enterprise autonomous agents._
