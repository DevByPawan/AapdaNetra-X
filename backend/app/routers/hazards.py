"""
AapdaNetra-X — Multi-Hazard Architecture API Router

Phase 6.20.5: Exposes hazard capability registry, multi-hazard matrix,
hazard definitions, and composite risk aggregation endpoints.
"""

from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, Query

from app.hazards.types import HazardType, HazardDefinition
from app.hazards.registry import get_hazard_registry
from app.hazards.aggregation import MultiHazardRiskAggregator

router = APIRouter()


@router.get("/hazards", response_model=Dict[str, HazardDefinition])
async def get_all_hazards():
    """
    Returns definitions and capability metadata for all registered system hazards.
    """
    registry = get_hazard_registry()
    return registry.get_all()


@router.get("/hazards/matrix", response_model=List[Dict[str, Any]])
async def get_hazard_capability_matrix():
    """
    Returns structured capability matrix summary across all registered hazards.
    """
    registry = get_hazard_registry()
    return registry.capability_matrix()


@router.get("/hazards/aggregate")
async def get_multi_hazard_aggregate():
    """
    Returns multi-hazard composite risk aggregate.
    """
    aggregator = MultiHazardRiskAggregator()
    return aggregator.aggregate()


@router.get("/hazards/{hazard_type}", response_model=HazardDefinition)
async def get_hazard_definition(hazard_type: str):
    """
    Returns definition and capability metadata for a specific hazard type.
    """
    try:
        ht_enum = HazardType(hazard_type.strip().lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown or unsupported hazard_type: '{hazard_type}'"
        ) from exc

    registry = get_hazard_registry()
    return registry.get_definition(ht_enum)
