from fastapi import APIRouter
from datetime import datetime, timezone
from app.models.schemas import ApproveRequest, ApproveResponse
import uuid

router = APIRouter()


@router.post("/response/approve", response_model=ApproveResponse)
async def approve_response(request: ApproveRequest):
    workflow_id = f"WF-{uuid.uuid4().hex[:8].upper()}"
    print(f"[APPROVED] Incident={request.incidentId}  Responder={request.responderId}  Workflow={workflow_id}")

    from app.services.persistence_service import get_persistence_service
    ps = get_persistence_service()
    if ps.is_enabled and ps.db_available:
        await ps.log_audit_event(
            event_type="RESPONSE_WORKFLOW_APPROVED",
            severity="INFO",
            source="ResponseRouter",
            description=f"Emergency response plan approved for incident {request.incidentId}",
            actor=request.responderId,
            event_data={"workflow_id": workflow_id, "incident_id": request.incidentId},
            incident_id=request.incidentId,
        )

    return ApproveResponse(
        approved=True,
        workflowId=workflow_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
