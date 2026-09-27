from fastapi import APIRouter
from app.models.schemas import SimulationRequest, SimulationResponse
from app.services.risk_engine import run_simulation_engine, run_simulation_engine_async

router = APIRouter()


@router.post("/simulation", response_model=SimulationResponse)
async def run_simulation(request: SimulationRequest):
    """
    Runs counterfactual disaster simulation against the trained scikit-learn ML model.
    """
    return await run_simulation_engine_async(
        evacuationPace=request.evacuationPace,
        rainfallMultiplier=request.rainfallMultiplier,
        drainageEfficiency=request.drainageEfficiency,
        routeBlockage=request.routeBlockage,
        rainfallIncrease=request.rainfallIncrease,
        populationMovement=request.populationMovement,
        waterLevelIncrease=request.waterLevelIncrease,
    )
