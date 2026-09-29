"""
AapdaNetra-X — Simulation API Router

Phase 6.16: Advanced What-If Simulation & Scenario Analysis Endpoints.
Preserves existing POST /api/simulation contract while adding plural endpoints,
lookup by ID, incident history, and scenario comparison.
"""

from typing import List, Optional
import uuid
from fastapi import APIRouter, HTTPException, Query
from app.models.schemas import (
    ScenarioCompareRequest,
    ScenarioCompareResponse,
    SimulationRequest,
    SimulationResponse,
)
from app.services.scenario_service import execute_scenario_analysis, execute_scenario_analysis_async

router = APIRouter()


@router.post("/simulation", response_model=SimulationResponse)
@router.post("/simulations", response_model=SimulationResponse)
async def run_simulation(request: SimulationRequest, incident_id: str = Query(default="INC-2026-DEFAULT")):
    """
    Runs counterfactual disaster scenario simulation against the GBR ML model & spatial risk engine.
    """
    return await execute_scenario_analysis_async(request, incident_id=incident_id)


@router.post("/simulations/compare", response_model=ScenarioCompareResponse)
async def compare_simulations(request: ScenarioCompareRequest):
    """
    Compares two What-If disaster scenarios side-by-side against the same baseline.
    """
    scen_a = execute_scenario_analysis(request.scenario_a, incident_id=request.incident_id)
    scen_b = execute_scenario_analysis(request.scenario_b, incident_id=request.incident_id)

    risk_diff = round(scen_b.scenarioRisk - scen_a.scenarioRisk, 1)
    route_changed = scen_a.routeRecommendation != scen_b.routeRecommendation

    summary = (
        f"Scenario B risk is {scen_b.scenarioRisk:.1f} vs Scenario A risk of {scen_a.scenarioRisk:.1f} "
        f"(delta: {risk_diff:+.1f} points). "
        f"{'Route recommendation changes between scenarios.' if route_changed else 'Route recommendation remains identical.'}"
    )

    return ScenarioCompareResponse(
        scenario_a=scen_a,
        scenario_b=scen_b,
        risk_delta_between_scenarios=risk_diff,
        route_change_between_scenarios=route_changed,
        summary_comparison=summary,
    )


@router.get("/simulations/{simulation_id}", response_model=SimulationResponse)
async def get_simulation_by_id(simulation_id: str):
    """
    Retrieves a persisted simulation record by UUID.
    """
    from app.services.persistence_service import get_persistence_service
    ps = get_persistence_service()

    if not ps.is_enabled or not ps.db_available:
        raise HTTPException(status_code=503, detail="Database persistence unavailable")

    try:
        sim_uuid = uuid.UUID(simulation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid simulation UUID format")

    from app.db.base import get_db_manager
    from app.db.repositories.simulation import SimulationRepository

    db_mgr = get_db_manager()
    async with db_mgr.get_session() as session:
        repo = SimulationRepository(session)
        sim = await repo.get_by_id(sim_uuid)
        if not sim:
            raise HTTPException(status_code=404, detail="Simulation record not found")

        # Convert ORM model to SimulationResponse
        req = SimulationRequest(
            evacuationPace=sim.evacuation_pace,
            rainfallMultiplier=sim.rainfall_multiplier,
            drainageEfficiency=sim.drainage_efficiency,
            routeBlockage=sim.route_blockage,
            rainfallIncrease=sim.rainfall_increase,
            populationMovement=sim.population_movement,
            waterLevelIncrease=sim.water_level_increase,
        )
        res = execute_scenario_analysis(req, incident_id=sim.incident_id)
        res.scenario_id = str(sim.id)
        return res


@router.get("/incidents/{incident_id}/simulations", response_model=List[SimulationResponse])
async def list_incident_simulations(
    incident_id: str,
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Fetches historical simulation runs for a given incident identifier.
    """
    from app.services.persistence_service import get_persistence_service
    ps = get_persistence_service()

    if not ps.is_enabled or not ps.db_available:
        return []

    from app.db.base import get_db_manager
    from app.db.repositories.simulation import SimulationRepository

    db_mgr = get_db_manager()
    async with db_mgr.get_session() as session:
        repo = SimulationRepository(session)
        sims = await repo.get_history_by_incident(incident_id, limit=limit)
        results = []
        for sim in sims:
            req = SimulationRequest(
                evacuationPace=sim.evacuation_pace,
                rainfallMultiplier=sim.rainfall_multiplier,
                drainageEfficiency=sim.drainage_efficiency,
                routeBlockage=sim.route_blockage,
                rainfallIncrease=sim.rainfall_increase,
                populationMovement=sim.population_movement,
                waterLevelIncrease=sim.water_level_increase,
            )
            res = execute_scenario_analysis(req, incident_id=sim.incident_id)
            res.scenario_id = str(sim.id)
            results.append(res)
        return results
