"""
AapdaNetra-X — Decision Support API Router

Phase 6.17: Emergency Decision Support endpoints.
Provides structured AI-assisted decision recommendations and state machine transitions
(RECOMMENDED -> APPROVED / REJECTED) with AuditEvent logging and SSE decision.approved events.
"""

from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from app.events.broker import get_event_broker
from app.events.schemas import EventEnvelope, EventType
from app.models.schemas import (
    DecisionActionRequest,
    DecisionActionResponse,
    DecisionSupportResponse,
)
from app.services.decision_service import (
    STATE_APPROVED,
    STATE_REJECTED,
    compute_emergency_decision,
    get_registered_decision,
    transition_decision,
)
from app.services.persistence_service import get_persistence_service

router = APIRouter()


@router.get("/decision/recommend", response_model=DecisionSupportResponse)
async def get_decision_recommendation(
    incident_id: str = Query(default="INC-2026-DEFAULT"),
    horizon: int = Query(default=0, ge=0, le=4),
):
    """
    Computes an explainable, deterministic emergency decision recommendation synthesizing
    risk prediction, conformal uncertainty, SHAP attributions, spatial hazard exposure,
    route safety, and data freshness.
    """
    res = compute_emergency_decision(incident_id=incident_id, horizon=horizon)
    return DecisionSupportResponse(**res)


@router.post("/decision/approve", response_model=DecisionActionResponse)
async def approve_decision(request: DecisionActionRequest):
    """
    Approves an emergency decision support recommendation.
    Validates state transition (RECOMMENDED -> APPROVED), logs AuditEvent,
    and publishes decision.approved SSE event.
    """
    success, msg, decision = transition_decision(
        decision_id=request.decision_id,
        new_status=STATE_APPROVED,
        responder_id=request.responder_id,
        reason=request.reason,
    )

    if not success:
        raise HTTPException(status_code=400, detail=msg)

    workflow_id = decision.get("workflow_id", f"WF-{request.decision_id}")
    now_iso = datetime.now(timezone.utc).isoformat()
    incident_id = decision.get("incident_id", "INC-2026-DEFAULT")

    # 1. Audit Event Logging
    ps = get_persistence_service()
    audit_logged = False
    try:
        await ps.log_audit_event(
            event_type="DECISION_APPROVED",
            severity="INFO",
            source="DecisionRouter",
            description=f"Decision recommendation '{request.decision_id}' APPROVED by responder {request.responder_id}. Rationale: {request.reason}",
            actor=request.responder_id,
            event_data={
                "decision_id": request.decision_id,
                "workflow_id": workflow_id,
                "responder_id": request.responder_id,
                "reason": request.reason,
                "recommended_action": decision.get("recommended_action"),
            },
            incident_id=incident_id,
        )
        audit_logged = True
    except Exception as exc:
        if ps.mode == "required":
            raise HTTPException(status_code=500, detail=f"Failed to log audit event in required mode: {exc}") from exc

    # 2. SSE Event Publication
    broker = get_event_broker()
    broker.publish(
        EventEnvelope(
            event=EventType.DECISION_APPROVED,
            incident_id=incident_id,
            data={
                "decision_id": request.decision_id,
                "workflow_id": workflow_id,
                "responder_id": request.responder_id,
                "status": STATE_APPROVED,
                "recommended_action": decision.get("recommended_action"),
                "priority": decision.get("priority"),
                "reason": request.reason,
                "timestamp": now_iso,
            },
            persistence_status="persisted" if audit_logged else "in_memory_fallback",
        )
    )

    return DecisionActionResponse(
        decision_id=request.decision_id,
        status=STATE_APPROVED,
        approved=True,
        workflow_id=workflow_id,
        timestamp=now_iso,
        audit_logged=audit_logged,
        sse_published=True,
        message=msg,
    )


@router.post("/decision/reject", response_model=DecisionActionResponse)
async def reject_decision(request: DecisionActionRequest):
    """
    Rejects an emergency decision support recommendation.
    Validates state transition (RECOMMENDED -> REJECTED) and logs AuditEvent.
    Does NOT publish decision.approved SSE event.
    """
    success, msg, decision = transition_decision(
        decision_id=request.decision_id,
        new_status=STATE_REJECTED,
        responder_id=request.responder_id,
        reason=request.reason,
    )

    if not success:
        raise HTTPException(status_code=400, detail=msg)

    workflow_id = decision.get("workflow_id", f"WF-{request.decision_id}")
    now_iso = datetime.now(timezone.utc).isoformat()
    incident_id = decision.get("incident_id", "INC-2026-DEFAULT")

    # Log AuditEvent for Rejection
    ps = get_persistence_service()
    audit_logged = False
    try:
        await ps.log_audit_event(
            event_type="DECISION_REJECTED",
            severity="WARNING",
            source="DecisionRouter",
            description=f"Decision recommendation '{request.decision_id}' REJECTED by responder {request.responder_id}. Reason: {request.reason}",
            actor=request.responder_id,
            event_data={
                "decision_id": request.decision_id,
                "workflow_id": workflow_id,
                "responder_id": request.responder_id,
                "reason": request.reason,
            },
            incident_id=incident_id,
        )
        audit_logged = True
    except Exception as exc:
        if ps.mode == "required":
            raise HTTPException(status_code=500, detail=f"Failed to log audit event in required mode: {exc}") from exc

    return DecisionActionResponse(
        decision_id=request.decision_id,
        status=STATE_REJECTED,
        approved=False,
        workflow_id=workflow_id,
        timestamp=now_iso,
        audit_logged=audit_logged,
        sse_published=False,
        message=msg,
    )
