# simple fastapi wrapper for the environment

import asyncio
import logging
import os
import time
import traceback
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .environment import NexDeskEnv
from .knowledge_base import MockKnowledgeBase
from .innovation import AEDIEngine, IterationEngine, HelpdeskNotifier
from .automation import AutomationEngine

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="NexDesk — IT Ticket Triage OpenEnv",
    description="OpenEnv environment for training AI agents on IT helpdesk ticket triage.",
    version="2.0.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

env = NexDeskEnv()
kb = MockKnowledgeBase()

# AEDI Innovation Engine — Autonomous Error Discovery
_aedi = AEDIEngine()
_iterator = IterationEngine()
_notifier: Optional[HelpdeskNotifier] = None  # initialized after _emit_event is defined
_automation = AutomationEngine()

# Dashboard event feed (ring buffer of last 200 events)
_dashboard_events: deque = deque(maxlen=200)


def _emit_event(event_type: str, message: str, extra: Optional[Dict] = None) -> None:
    """Push an event into the dashboard feed."""
    event = {
        "id": len(_dashboard_events) + 1,
        "type": event_type,
        "message": message,
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
    }
    if extra:
        event.update(extra)
    _dashboard_events.appendleft(event)

# Now initialize the notifier with the emit function
_notifier = HelpdeskNotifier(emit_fn=lambda event_type, detail: _emit_event(event_type, detail))


# Mount dashboard static files
_dashboard_dir = Path(__file__).resolve().parent.parent / "dashboard"
if _dashboard_dir.is_dir():
    app.mount("/dashboard", StaticFiles(directory=str(_dashboard_dir), html=True), name="dashboard")
    logger.info(f"Dashboard mounted from {_dashboard_dir}")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "detail": exc.errors(),
            "message": "Invalid request format.",
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    logger.warning(f"Value error: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Bad request", "detail": str(exc)},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unexpected error: {str(exc)}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "detail": "An unexpected error occurred"},
    )


# request shapes
class ResetRequest(BaseModel):
    task: Optional[str] = Field(
        default="ticket_classify",
        description="Task: ticket_classify, ticket_route, ticket_resolve, crisis_surge",
    )


class StepRequest(BaseModel):
    session_id: str = Field(..., description="Session ID from reset", min_length=1)
    priority: Optional[Literal["low", "medium", "high", "critical"]] = Field(
        None, description="low, medium, high, critical"
    )
    category: Optional[
        Literal["network", "hardware", "software", "access", "security", "other"]
    ] = Field(None, description="network, hardware, software, access, security, other")
    team: Optional[Literal["helpdesk", "network-ops", "sysadmin", "security", "dev"]] = Field(
        None, description="helpdesk, network-ops, sysadmin, security, dev"
    )
    affected_system: Optional[str] = Field(
        None, description="Primary affected system", min_length=1
    )
    first_response: Optional[str] = Field(None, description="First response to user", min_length=1)
    resolution_steps: Optional[List[str]] = Field(None, description="List of resolution steps")
    sla_hours: Optional[int] = Field(None, description="Estimated hours to resolve", ge=1, le=168)
    confidence: Optional[float] = Field(
        None, description="Agent's confidence (0.0-1.0)", ge=0.01, le=0.99
    )
    action_type: Optional[Literal["classify", "respond", "resolve", "delegate", "escalate"]] = (
        Field(None, description="classify, respond, resolve, delegate, escalate")
    )
    reasoning: Optional[str] = Field(None, description="Optional reasoning", min_length=1)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "env": "nexdesk-ticket-triage",
        "version": "2.0.0",
        "features": [
            "time_pressure",
            "confidence_calibration",
            "crisis_surge",
            "multi_dimensional_scoring",
            "business_metrics",
        ],
    }


@app.post("/reset")
def reset(req: ResetRequest = ResetRequest()) -> Dict[str, Any]:
    try:
        result = env.reset(task=req.task)
        sid = result.get('session_id', 'unknown')
        logger.info(f"Reset: task={req.task}, session_id={sid}")
        _emit_event("reset", f"New episode started: {req.task} (session {sid[:8]}…)")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Reset error: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.post("/step")
def step(req: StepRequest) -> Dict[str, Any]:
    if not req.session_id or not req.session_id.strip():
        raise HTTPException(status_code=400, detail="session_id is required")

    action: Dict[str, Any] = {
        "priority": req.priority,
        "category": req.category,
        "team": req.team,
        "affected_system": req.affected_system,
        "first_response": req.first_response,
        "resolution_steps": req.resolution_steps,
        "sla_hours": req.sla_hours,
        "confidence": req.confidence,
        "action_type": req.action_type,
        "reasoning": req.reasoning,
    }

    try:
        result = env.step(session_id=req.session_id, action=action)
        reward = result.get("reward", 0)
        done = result.get("done", False)
        step_num = result.get("info", {}).get("step", "?")
        if done:
            total = result.get("info", {}).get("total_reward", reward)
            _emit_event("done", f"Episode complete — total reward: {total:.4f}", {"reward": total})
        else:
            _emit_event("step", f"Step {step_num} — reward: {reward:.4f}", {"reward": reward})
        # Check SLA breach
        sla_b = result.get("info", {}).get("score_breakdown", {}).get("sla_breaches", 0)
        if sla_b and sla_b > 0:
            _emit_event("breach", f"⚠ SLA breach #{sla_b} detected")
        return result
    except ValueError as e:
        error_msg = str(e).lower()
        if "unknown session" in error_msg or "session_id" in error_msg:
            raise HTTPException(status_code=404, detail=str(e))
        elif "episode already done" in error_msg:
            raise HTTPException(status_code=400, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Step error: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/state")
def state(session_id: str) -> Dict[str, Any]:
    if not session_id or not session_id.strip():
        raise HTTPException(status_code=400, detail="session_id parameter is required")
    try:
        return env.state(session_id=session_id)
    except ValueError as e:
        if "unknown" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"State error: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/tasks")
def list_tasks() -> Dict[str, Any]:
    return {
        "tasks": [
            {
                "id": "ticket_classify",
                "difficulty": "easy",
                "max_steps": 1,
                "description": "Classify ticket priority and category",
                "sla_minutes": 60,
            },
            {
                "id": "ticket_route",
                "difficulty": "medium",
                "max_steps": 2,
                "description": "Classify + route to correct team",
                "sla_minutes": 30,
            },
            {
                "id": "ticket_resolve",
                "difficulty": "hard",
                "max_steps": 3,
                "description": "Full resolution pipeline",
                "sla_minutes": 20,
            },
            {
                "id": "crisis_surge",
                "difficulty": "hard",
                "max_steps": 10,
                "description": "Handle 10-ticket surge under pressure",
                "sla_minutes": 5,
                "is_batch": True,
            },
        ]
    }


@app.get("/metrics")
def get_metrics() -> Dict[str, Any]:
    try:
        return env.get_metrics()
    except Exception as e:
        logger.error(f"Metrics error: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@app.get("/metrics/roi")
def get_roi(monthly_volume: int = 1000) -> Dict[str, Any]:
    if monthly_volume <= 0:
        raise HTTPException(status_code=400, detail="monthly_volume must be positive")
    if monthly_volume > 1000000:
        raise HTTPException(status_code=400, detail="monthly_volume exceeds reasonable limit")
    try:
        return env._metrics.get_roi_report(monthly_ticket_volume=monthly_volume)
    except Exception as e:
        logger.error(f"ROI error: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to calculate ROI: {str(e)}")


@app.get("/api/report/generate")
def generate_report() -> Dict[str, Any]:
    """Generates a complete snapshot of performance, SLA metrics, and ROI calculation."""
    try:
        summary = env.get_metrics()
        roi = env._metrics.get_roi_report(monthly_ticket_volume=1000)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "complete",
            "performance_summary": summary,
            "roi_analysis": roi
        }
    except Exception as e:
        logger.error(f"Generate report error: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "name": "NexDesk IT Ticket Triage",
        "version": "2.0.0",
        "description": (
            "OpenEnv environment for training AI agents on real-world IT helpdesk "
            "ticket triage with time pressure, confidence calibration, and crisis surge scenarios."
        ),
        "author": "amalscicoder",
        "endpoints": {
            "/health": "GET",
            "/metadata": "GET",
            "/schema": "GET",
            "/reset": "POST",
            "/step": "POST",
            "/state": "GET",
            "/mcp": "POST",
            "/tasks": "GET",
            "/metrics": "GET",
            "/metrics/roi": "GET",
        },
    }


@app.get("/metadata")
def metadata() -> Dict[str, Any]:
    """Required by openenv-core validator: GET /metadata returns name and description."""
    return {
        "name": "NexDesk IT Ticket Triage",
        "description": (
            "OpenEnv environment for training AI agents on real-world IT helpdesk "
            "ticket triage with time pressure, confidence calibration, and crisis surge scenarios."
        ),
        "version": "2.0.0",
        "author": "amalscicoder",
        "readme_content": None,
        "documentation_url": "https://huggingface.co/spaces/amalscicoder/nexdesk-triage",
    }


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> JSONResponse:
    """
    MCP JSON-RPC 2.0 endpoint required by openenv-core validator.

    Handles tools/list and basic session lifecycle calls so that the
    openenv-core runtime validator criterion 'mcp_endpoint' passes.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    method = body.get("method", "")
    request_id = body.get("id", 1)

    # tools/list — return the environment's available tools
    if method == "tools/list":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "reset",
                            "description": "Reset the environment and start a new episode.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "task": {
                                        "type": "string",
                                        "enum": [
                                            "ticket_classify",
                                            "ticket_route",
                                            "ticket_resolve",
                                            "crisis_surge",
                                        ],
                                        "description": "Task type to run",
                                    }
                                },
                            },
                        },
                        {
                            "name": "step",
                            "description": "Take a step in the environment.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "session_id": {"type": "string"},
                                    "priority": {
                                        "type": "string",
                                        "enum": ["low", "medium", "high", "critical"],
                                    },
                                    "category": {
                                        "type": "string",
                                        "enum": [
                                            "network",
                                            "hardware",
                                            "software",
                                            "access",
                                            "security",
                                            "other",
                                        ],
                                    },
                                    "team": {
                                        "type": "string",
                                        "enum": [
                                            "helpdesk",
                                            "network-ops",
                                            "sysadmin",
                                            "security",
                                            "dev",
                                        ],
                                    },
                                    "confidence": {
                                        "type": "number",
                                        "minimum": 0.01,
                                        "maximum": 0.99,
                                    },
                                },
                                "required": ["session_id"],
                            },
                        },
                    ]
                },
            }
        )

    # openenv session create
    if method == "openenv/session/create":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"session_id": "http-session"},
            }
        )

    # openenv session close
    if method == "openenv/session/close":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"closed": True},
            }
        )

    # Default: return server capabilities (initialize / unknown methods)
    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "nexdesk-ticket-triage",
                    "version": "2.0.0",
                },
            },
        }
    )


@app.get("/schema")
def schema() -> Dict[str, Any]:
    """Required by openenv-core validator: GET /schema returns action, observation, and state schemas."""
    return {
        "action": {
            "type": "object",
            "required": ["session_id"],
            "properties": {
                "session_id": {"type": "string", "description": "Session ID from reset"},
                "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "category": {
                    "type": "string",
                    "enum": ["network", "hardware", "software", "access", "security", "other"],
                },
                "team": {
                    "type": "string",
                    "enum": ["helpdesk", "network-ops", "sysadmin", "security", "dev"],
                },
                "affected_system": {"type": "string"},
                "first_response": {"type": "string"},
                "resolution_steps": {"type": "array", "items": {"type": "string"}},
                "sla_hours": {"type": "integer", "minimum": 1, "maximum": 168},
                "confidence": {"type": "number", "minimum": 0.01, "maximum": 0.99},
                "action_type": {
                    "type": "string",
                    "enum": ["classify", "respond", "resolve", "delegate", "escalate"],
                },
                "reasoning": {"type": "string"},
            },
        },
        "observation": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "subject": {"type": "string"},
                "description": {"type": "string"},
                "submitter": {"type": "string"},
                "department": {"type": "string"},
                "submitted_at": {"type": "string"},
                "task": {"type": "string"},
                "step": {"type": "integer"},
                "max_steps": {"type": "integer"},
                "last_reward": {"type": "number"},
                "session_id": {"type": "string"},
                "message": {"type": "string"},
                "sla_deadline_minutes": {"type": "integer"},
                "queue_depth": {"type": "integer"},
                "stress_level": {"type": "number"},
                "org_context": {"type": "object"},
                "similar_tickets": {"type": "array"},
                "knowledge_hints": {"type": "object"},
            },
        },
        "state": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "task": {"type": "string"},
                "step": {"type": "integer"},
                "max_steps": {"type": "integer"},
                "done": {"type": "boolean"},
                "total_reward": {"type": "number"},
                "ticket_id": {"type": "string"},
                "sla_breaches": {"type": "integer"},
                "stress_level": {"type": "number"},
                "confidence_history": {"type": "array"},
                "accuracy_history": {"type": "array"},
            },
        },
    }


@app.get("/schema/action")
def action_schema() -> Dict[str, Any]:
    return {
        "session_id": {"type": "string", "required": True},
        "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "category": {
            "type": "string",
            "enum": ["network", "hardware", "software", "access", "security", "other"],
        },
        "team": {
            "type": "string",
            "enum": ["helpdesk", "network-ops", "sysadmin", "security", "dev"],
        },
        "affected_system": {"type": "string"},
        "first_response": {"type": "string"},
        "resolution_steps": {"type": "array", "items": {"type": "string"}},
        "sla_hours": {"type": "integer", "min": 1, "max": 168},
        "confidence": {"type": "number", "min": 0.01, "max": 0.99},
    }


# ═══════════════════════════════════════════════════════════════
# Dashboard & Enhancement API endpoints
# ═══════════════════════════════════════════════════════════════


@app.get("/api/dashboard")
def dashboard_data() -> Dict[str, Any]:
    """Live session data for the Mission Control dashboard."""
    sessions = []
    active_alerts = []
    kb_usage = {"searches": 0}
    escalation_flows = []
    
    with env._lock:
        for sid, sess in list(env._sessions.items()):
            ticket = sess.get("ticket", {})
            elapsed = (time.time() - sess.get("start_time", time.time())) / 60.0
            done = sess.get("done", False)
            
            # Reconstruct pipeline stage
            step = sess.get("step", 0)
            if done:
                stage = "Closed"
            elif step == 0:
                stage = "Received"
            elif step == 1:
                stage = "Classification"
            elif step == 2:
                stage = "Routing"
            else:
                stage = "Resolution"
            
            if sess.get("bounce_count", 0) > 0:
                stage = "Escalation Check"
            
            sessions.append({
                "session_id": sid,
                "task": sess.get("task", "—"),
                "ticket_id": ticket.get("id", "—"),
                "subject": ticket.get("subject", "—"),
                "priority": ticket.get("gt_priority", "—"),
                "category": ticket.get("gt_category", "—"),
                "team": ticket.get("gt_team", "—"),
                "step": step,
                "max_steps": sess.get("max_steps", 1),
                "done": done,
                "total_reward": round(sess.get("total_reward", 0), 4),
                "stress_level": round(sess.get("stress_level", 0), 2),
                "sla_deadline_minutes": sess.get("sla_deadline_minutes", 60),
                "elapsed_minutes": round(elapsed, 1),
                "sla_breaches": sess.get("sla_breaches", 0),
                "queue_depth": sess.get("queue_depth", 0),
                "stage": stage,
                "current_role": sess.get("current_agent_role", "L1_Dispatcher"),
            })
            
            active_alerts.extend(sess.get("active_flags", []))
            kb_usage["searches"] += sess.get("kb_searches_performed", 0)
            
            for esc in sess.get("escalation_history", []):
                escalation_flows.append({"session_id": sid, "ticket_id": ticket.get("id"), **esc})
                
    # Collect multi-agent orchestrator summaries
    multi_agent_summaries = {}
    with env._lock:
        for sid in env._multi_agent_orchestrators:
            try:
                multi_agent_summaries[sid] = env._multi_agent_orchestrators[sid].get_summary()
            except Exception:
                pass

    return {
        "sessions": sessions,
        "total_active": sum(1 for s in sessions if not s["done"]),
        "total_complete": sum(1 for s in sessions if s["done"]),
        "recent_events": list(_dashboard_events)[:30],
        "alerts": active_alerts,
        "kb_usage": kb_usage,
        "escalation_flows": escalation_flows,
        "multi_agent": multi_agent_summaries,
    }

@app.get("/api/dashboard/ticket/{session_id}")
def get_ticket_details(session_id: str) -> Dict[str, Any]:
    """Detailed drill-down for a specific ticket session."""
    with env._lock:
        if session_id not in env._sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        sess = env._sessions[session_id]
        ticket = sess.get("ticket", {})
        
        return {
            "session_id": session_id,
            "ticket_id": ticket.get("id"),
            "subject": ticket.get("subject"),
            "description": ticket.get("description"),
            "submitter": ticket.get("submitter"),
            "department": ticket.get("department"),
            "ground_truth": {
                "priority": ticket.get("gt_priority"),
                "category": ticket.get("gt_category"),
                "team": ticket.get("gt_team")
            },
            "accumulated_actions": sess.get("accumulated", {}),
            "step_rewards": sess.get("rewards", []),
            "total_reward": round(sess.get("total_reward", 0), 4),
            "escalation_history": sess.get("escalation_history", []),
            "kb_searches": sess.get("kb_searches_performed", 0),
            "active_flags": sess.get("active_flags", []),
            "current_role": sess.get("current_agent_role", "L1_Dispatcher"),
            "done": sess.get("done", False)
        }

@app.get("/api/dashboard/heatmap")
def get_heatmap() -> Dict[str, Any]:
    """Returns priority x category matrix density of all active tickets."""
    matrix = {}
    with env._lock:
        for sid, sess in env._sessions.items():
            ticket = sess.get("ticket", {})
            pri = ticket.get("gt_priority", "medium")
            cat = ticket.get("gt_category", "other")
            if pri not in matrix:
                matrix[pri] = {}
            matrix[pri][cat] = matrix[pri].get(cat, 0) + 1
    return matrix


@app.get("/api/events")
async def event_stream(request: Request):
    """Server-Sent Events stream for real-time dashboard updates."""
    async def generate():
        last_id = 0
        while True:
            if await request.is_disconnected():
                break
            new_events = [e for e in _dashboard_events if e["id"] > last_id]
            for event in reversed(new_events):
                yield f"data: {__import__('json').dumps(event)}\n\n"
                last_id = max(last_id, event["id"])
            await asyncio.sleep(1)
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/kb/search")
def kb_search(q: str = "", top_k: int = 3) -> Dict[str, Any]:
    """Search the mock knowledge base. Each search costs SLA time."""
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")
    results = kb.search(q.strip(), top_k=min(top_k, 10))
    return {
        "query": q,
        "results": results,
        "count": len(results),
        "search_cost_minutes": kb.get_search_cost(),
    }


@app.get("/api/kb/stats")
def kb_stats() -> Dict[str, Any]:
    """Knowledge base statistics."""
    return kb.get_stats()


# ── AEDI Innovation Endpoints ──


class IngestRequest(BaseModel):
    source: str = Field(..., description="Source type: 'log' or 'ticket'")
    text: str = Field(..., description="Raw log line or ticket text")


class IterateRequest(BaseModel):
    ticket_id: str = Field(..., description="AEDI ticket ID to iterate on")
    reason: Optional[str] = Field(None, description="Flag reason (only for first flag)")


@app.get("/innovation/status")
def innovation_status() -> Dict[str, Any]:
    """Full AEDI pipeline status: discovery, iteration, and alert stats."""
    return {
        "discovery": _aedi.get_stats(),
        "discoveries": _aedi.get_discoveries()[-10:],
        "iteration": _iterator.get_stats(),
        "flagged_issues": {k: v.get("status") for k, v in _iterator.get_flagged().items()},
        "post_mortems": _iterator.get_post_mortems(),
        "alerts": _notifier.get_alerts(20) if _notifier else [],
        "alert_stats": _notifier.get_stats() if _notifier else {},
    }


@app.post("/innovation/ingest")
def innovation_ingest(req: IngestRequest) -> Dict[str, Any]:
    """Ingest a log line or ticket text into the AEDI discovery engine."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    event = _aedi.ingest(req.source, req.text)
    if event:
        alert = _notifier.notify_new_issue(event) if _notifier else {}
        return {
            "status": "novel_discovered",
            "discovery": event,
            "alert": alert,
        }
    return {
        "status": "known_or_duplicate",
        "message": "Pattern already known or previously seen.",
    }


@app.post("/innovation/iterate")
def innovation_iterate(req: IterateRequest) -> Dict[str, Any]:
    """Iterate on a flagged AEDI issue (escalation ladder)."""
    # Auto-flag if not yet flagged
    if req.ticket_id not in _iterator.flagged_issues:
        # Find the discovery to flag
        target = None
        for d in _aedi.get_discoveries():
            if d.get("id") == req.ticket_id:
                target = d
                break
        if not target:
            raise HTTPException(status_code=404, detail=f"Discovery '{req.ticket_id}' not found")
        _iterator.flag(req.ticket_id, target, reason=req.reason or "manual_flag")

    result = _iterator.iterate(req.ticket_id)
    if _notifier:
        _notifier.notify_iteration(req.ticket_id, result)
    return result


# ── Automation Engine Endpoints ──


class AutomationTicket(BaseModel):
    id: str = Field(..., description="Ticket ID")
    category: str = Field("other", description="Ticket category")
    priority: str = Field("medium", description="Ticket priority")
    status: str = Field("new", description="Ticket status")
    assigned_team: Optional[str] = Field(None, description="Currently assigned team")
    ack_sent: bool = Field(False)
    sla_breach_notified: bool = Field(False)


class AutomationContext(BaseModel):
    elapsed_minutes: int = Field(0, description="Minutes since ticket creation")
    days_since_last_response: int = Field(0, description="Days since last user response")


class ProcessRequest(BaseModel):
    ticket: AutomationTicket
    context: Optional[AutomationContext] = None


@app.post("/automation/process")
def automation_process(req: ProcessRequest) -> Dict[str, Any]:
    """Run all automation rules against a ticket."""
    ticket_dict = req.ticket.model_dump()
    ctx_dict = req.context.model_dump() if req.context else {}
    actions = _automation.process_ticket(ticket_dict, ctx_dict)
    _emit_event("automation", f"Processed {req.ticket.id}: {len(actions)} actions taken")
    return {
        "ticket_id": req.ticket.id,
        "actions_taken": actions,
        "updated_ticket": ticket_dict,
    }


@app.get("/automation/rules")
def automation_rules() -> Dict[str, Any]:
    """List all registered automation rules with execution stats."""
    return {
        "rules": _automation.get_rules(),
        "stats": _automation.get_stats(),
    }


@app.get("/automation/audit")
def automation_audit(limit: int = 50) -> Dict[str, Any]:
    """Return the automation audit log for traceability."""
    return {
        "audit_log": _automation.get_audit_log(limit),
        "total_entries": len(_automation.audit_log),
    }


@app.get("/automation/config")
def automation_config() -> Dict[str, Any]:
    """Return SLA thresholds and reply templates."""
    return {
        "sla_thresholds": _automation.get_sla_thresholds(),
        "reply_templates": _automation.get_reply_templates(),
        "team_routing": {
            "network": "network-ops",
            "hardware": "sysadmin",
            "software": "dev",
            "access": "sysadmin",
            "security": "security",
            "database": "dev",
            "other": "helpdesk",
        },
    }


def main():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7860)


if __name__ == "__main__":
    main()
