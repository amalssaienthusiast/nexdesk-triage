"""
NexDesk FastAPI Server
Endpoints: /health, /reset, /step, /state, /tasks, /metrics
"""

import logging
import traceback
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .environment import NexDeskEnv

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="NexDesk — IT Ticket Triage OpenEnv",
    description="OpenEnv environment for training AI agents on IT helpdesk ticket triage.",
    version="1.1.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

env = NexDeskEnv()


# Exception handlers
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


# Request models
class ResetRequest(BaseModel):
    task: Optional[str] = Field(
        "ticket_classify",
        description="Task: ticket_classify, ticket_route, ticket_resolve, crisis_surge",
    )


class StepRequest(BaseModel):
    session_id: str = Field(..., description="Session ID from reset", min_length=1)
    priority: Optional[str] = Field(None, description="low, medium, high, critical")
    category: Optional[str] = Field(
        None, description="network, hardware, software, access, security, other"
    )
    team: Optional[str] = Field(None, description="helpdesk, network-ops, sysadmin, security, dev")
    affected_system: Optional[str] = Field(None, description="Primary affected system")
    first_response: Optional[str] = Field(None, description="First response to user")
    resolution_steps: Optional[List[str]] = Field(None, description="List of resolution steps")
    sla_hours: Optional[int] = Field(None, description="Estimated hours to resolve", ge=0, le=168)
    confidence: Optional[float] = Field(
        None, ge=0.001, le=0.999, description="Agent's confidence (0.001-0.999)"
    )
    action_type: Optional[str] = Field(
        None, description="classify, respond, resolve, delegate, escalate"
    )
    reasoning: Optional[str] = Field(None, description="Optional reasoning")


# Endpoints
@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "env": "nexdesk-ticket-triage",
        "version": "1.1.0",
        "features": [
            "time_pressure",
            "confidence_calibration",
            "crisis_surge_mode",
            "multi_dimensional_scoring",
            "business_metrics",
        ],
    }


@app.post("/reset")
def reset(req: ResetRequest = ResetRequest()) -> Dict[str, Any]:
    try:
        result = env.reset(task=req.task)
        logger.info(f"Reset: task={req.task}, session_id={result.get('session_id', 'unknown')}")
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


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "name": "NexDesk IT Ticket Triage",
        "version": "1.1.0",
        "description": "OpenEnv environment for training AI agents on IT helpdesk tasks",
        "endpoints": {
            "/health": "GET",
            "/reset": "POST",
            "/step": "POST",
            "/state": "GET",
            "/tasks": "GET",
            "/metrics": "GET",
            "/metrics/roi": "GET",
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
        "sla_hours": {"type": "integer", "min": 0, "max": 168},
        "confidence": {"type": "number", "min": 0.001, "max": 0.999},
    }


def main():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7860)


if __name__ == "__main__":
    main()
