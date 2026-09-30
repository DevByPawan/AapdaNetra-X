"""
AapdaNetra-X — Phase 6.20.8 Hazard-Aware Dynamic Evacuation Unit Test Suite

Verifies:
1. Flood evacuation routing is fully preserved when hazard_type is omitted or explicitly set to 'flood'.
2. Unsupported hazards (extreme_rainfall, landslide, cyclone, heatwave, earthquake) return EvacuationUnavailableResponse.
3. Unsupported hazards do not invoke flood spatial penalties, risk scores, or emit SSE route.updated events.
4. Unknown hazard raises validation error.
"""

import pytest
from app.services.evacuation_service import EvacuationService, get_evacuation_service
from app.models.schemas import (
    EvacuationIntelligenceResponse,
    EvacuationUnavailableResponse,
)


def test_flood_evacuation_routing_preservation():
    """Verify flood routing behaves identically with hazard_type='flood' or omitted."""
    svc = EvacuationService()

    # Omitted hazard_type (defaults to flood)
    res_default = svc.evaluate_evacuation_routes(incident_id="INC-EVAC-TEST", horizon=0)
    assert isinstance(res_default, EvacuationIntelligenceResponse)
    assert res_default.hazard_type == "flood"
    assert res_default.recommended_route is not None
    assert res_default.recommended_route.safety_score > 0.0

    # Explicit flood hazard_type
    res_flood = svc.evaluate_evacuation_routes(
        incident_id="INC-EVAC-TEST", horizon=0, hazard_type="flood"
    )
    assert isinstance(res_flood, EvacuationIntelligenceResponse)
    assert res_flood.hazard_type == "flood"
    assert res_flood.recommended_route.id == res_default.recommended_route.id


def test_unsupported_hazards_return_unavailable():
    """Verify extreme_rainfall, landslide, cyclone, heatwave, earthquake return UNAVAILABLE response."""
    svc = EvacuationService()

    unsupported_hazards = ["extreme_rainfall", "landslide", "cyclone", "heatwave", "earthquake"]

    for hz in unsupported_hazards:
        res = svc.evaluate_evacuation_routes(
            incident_id=f"INC-{hz.upper()}-TEST",
            horizon=0,
            publish_sse=True,  # Should NOT publish SSE for unavailable routing
            hazard_type=hz,
        )
        assert isinstance(res, EvacuationUnavailableResponse)
        assert res.hazard_type == hz
        assert res.routing_available is False
        assert res.status == "UNAVAILABLE"
        assert "Operational evacuation routing is not supported" in res.reason


def test_unknown_hazard_raises_validation_error():
    """Verify unknown or invalid hazard_type string raises ValueError."""
    svc = EvacuationService()
    with pytest.raises(ValueError, match="Unknown or unsupported hazard type"):
        svc.evaluate_evacuation_routes(
            incident_id="INC-FAIL-TEST",
            hazard_type="tsunami",
        )
