from fastapi import APIRouter
from app.data.simulated import ALERTS
from app.models.schemas import AlertsResponse

router = APIRouter()


@router.get("/alerts", response_model=AlertsResponse)
async def get_alerts():
    return AlertsResponse(**ALERTS)
