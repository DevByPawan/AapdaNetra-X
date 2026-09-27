from fastapi import APIRouter, Query
from app.models.schemas import RiskResponse
from app.services.risk_engine import compute_risk_state, compute_risk_state_async

router = APIRouter()


@router.get("/risk", response_model=RiskResponse)
async def get_risk(horizon: int = Query(default=0, ge=0, le=3)):
    """
    Returns dynamic ML-driven flood risk state for requested horizon (0=NOW, 1=+10M, 2=+20M, 3=+30M).
    """
    return await compute_risk_state_async(horizon=horizon)
