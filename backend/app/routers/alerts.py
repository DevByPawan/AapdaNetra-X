"""
AapdaNetra-X — Phase 6.15 / Phase 6.20.7 Intelligent Alert System API Router
Exposes active alerts, trigger evaluation, acknowledgement, and resolution endpoints.
"""
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Path, Body, Query

from app.data.simulated import ALERTS
from app.models.schemas import AlertsResponse
from app.services.alert_engine import get_alert_engine, STATUS_OPEN, STATUS_ACKNOWLEDGED, STATUS_RESOLVED
from app.services.risk_engine import compute_risk_state
from app.routers.history import validate_optional_hazard_type

router = APIRouter(tags=["Alerts"])


@router.get("/alerts", response_model=AlertsResponse)
async def get_alerts(hazard_type: Optional[str] = Query(None, description="Optional hazard filter")):
    """Returns active deduplicated emergency warnings and data quality alerts."""
    h_val = validate_optional_hazard_type(hazard_type)

    engine = get_alert_engine()
    # Trigger an evaluation cycle if active alerts list is empty
    if not engine._active_alerts:
        risk_res = compute_risk_state(horizon=0)
        engine.evaluate_all_rules(
            incident_id="INC-2026-DEFAULT",
            predicted_risk=risk_res.predictedRisk,
            current_risk=risk_res.currentRisk,
            uncertainty=risk_res.predictionInterval.model_dump() if risk_res.predictionInterval else {},
            hazard_type=h_val or "flood",
        )

    active_list = list(engine._active_alerts.values())
    if h_val:
        active_list = [a for a in active_list if a.hazard_type == h_val]

    formatted_alerts = []
    for a in active_list:
        formatted_alerts.append({
            "id": a.id,
            "severity": a.severity,
            "title": a.title,
            "description": a.description,
            "timestamp": a.created_at,
            "status": a.status,
            "source": a.source,
            "hazard_type": a.hazard_type,
            "metadata": a.metadata,
        })

    if not formatted_alerts:
        if h_val and h_val != "flood":
            return AlertsResponse(open=0, alerts=[])
        return AlertsResponse(**ALERTS)

    return AlertsResponse(
        open=len(formatted_alerts),
        alerts=formatted_alerts,
    )


@router.post("/alerts/evaluate")
async def evaluate_alerts_now(hazard_type: Optional[str] = Query("flood", description="Hazard type to evaluate")):
    """Explicitly triggers an alert engine evaluation cycle."""
    h_val = validate_optional_hazard_type(hazard_type) or "flood"
    risk_res = compute_risk_state(horizon=0)
    engine = get_alert_engine()
    try:
        active_alerts = engine.evaluate_all_rules(
            incident_id="INC-2026-DEFAULT",
            predicted_risk=risk_res.predictedRisk,
            current_risk=risk_res.currentRisk,
            uncertainty=risk_res.predictionInterval.model_dump() if risk_res.predictionInterval else {},
            hazard_type=h_val,
        )
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err)) from val_err

    return {
        "success": True,
        "active_count": len(active_alerts),
        "alerts": [a.to_dict() for a in active_alerts],
    }


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str = Path(..., description="Alert UUID or ID")):
    """Acknowledges an active alert (OPEN -> ACKNOWLEDGED)."""
    engine = get_alert_engine()
    try:
        updated = engine.acknowledge_alert(alert_id)
        if not updated:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found in active alerts")
        return {"success": True, "alert": updated.to_dict()}
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str = Path(..., description="Alert UUID or ID")):
    """Resolves an active or acknowledged alert (OPEN/ACKNOWLEDGED -> RESOLVED)."""
    engine = get_alert_engine()
    try:
        updated = engine.resolve_alert(alert_id)
        if not updated:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found in active alerts")
        return {"success": True, "alert": updated.to_dict()}
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
