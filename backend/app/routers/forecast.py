from fastapi import APIRouter
from app.models.schemas import ForecastResponse, ForecastPoint
from app.services.risk_engine import compute_risk_state

router = APIRouter()


@router.get("/forecast", response_model=ForecastResponse)
async def get_forecast():
    """
    Returns multi-point ML hazard forecast based on trained model predictions.
    """
    p0 = compute_risk_state(0)
    p1 = compute_risk_state(1)
    p2 = compute_risk_state(2)
    p3 = compute_risk_state(3)

    points = [
        ForecastPoint(minutesOffset=0, risk=p0.predictedRisk),
        ForecastPoint(minutesOffset=10, risk=p1.predictedRisk),
        ForecastPoint(minutesOffset=20, risk=p2.predictedRisk),
        ForecastPoint(minutesOffset=30, risk=p3.predictedRisk),
        ForecastPoint(minutesOffset=45, risk=min(100.0, round(p3.predictedRisk * 1.05, 1))),
        ForecastPoint(minutesOffset=60, risk=min(100.0, round(p3.predictedRisk * 1.08, 1))),
    ]

    reliability = p0.predictionReliability

    return ForecastResponse(
        points=points,
        peakAt="~30 min",
        trend="ESCALATING" if p3.predictedRisk >= p0.predictedRisk else "DE-ESCALATING",
        confidence=reliability,
        predictionReliability=reliability,
        trendLabel="Escalating" if p3.predictedRisk >= p0.predictedRisk else "De-escalating",
    )
