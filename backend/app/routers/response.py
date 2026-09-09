from fastapi import APIRouter
from datetime import datetime, timezone
from app.models.schemas import ApproveRequest, ApproveResponse
import uuid

router = APIRouter()


@router.post("/response/approve", response_model=ApproveResponse)
async def approve_response(request: ApproveRequest):
    workflow_id = f"WF-{uuid.uuid4().hex[:8].upper()}"
    print(f"[APPROVED] Incident={request.incidentId}  Responder={request.responderId}  Workflow={workflow_id}")
    return ApproveResponse(
        approved=True,
        workflowId=workflow_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
