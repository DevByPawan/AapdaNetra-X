from fastapi import APIRouter
from datetime import datetime
from app.data.simulated import INCIDENT
from app.models.schemas import IncidentResponse

router = APIRouter()


@router.get("/incident", response_model=IncidentResponse)
async def get_incident():
    return IncidentResponse(**INCIDENT)
