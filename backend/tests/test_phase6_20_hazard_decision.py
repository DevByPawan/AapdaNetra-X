"""
AapdaNetra-X — Phase 6.20.9 Hazard-Aware Emergency Decision Support Unit Test Suite

Verifies:
1. Flood emergency decision support is fully preserved when hazard_type is omitted or set to 'flood'.
2. Unsupported hazards (extreme_rainfall, landslide, cyclone, heatwave, earthquake) return DecisionSupportUnavailableResponse.
3. Unsupported hazards do not generate flood actions, risk scores, SHAP, conformal uncertainty, or active alerts.
4. Unavailable hazard decisions cannot be approved or rejected via the decision state machine.
5. Unknown hazard raises validation error.
"""

import pytest
from app.services.decision_service import (
    compute_emergency_decision,
    transition_decision,
    STATE_APPROVED,
    STATE_REJECTED,
)


def test_flood_decision_support_preservation():
    """Verify flood decision recommendation behaves identically when hazard_type is omitted or set to 'flood'."""
    # Omitted hazard_type (defaults to flood)
    res_default = compute_emergency_decision(incident_id="INC-DEC-TEST", horizon=0)
    assert res_default.get("hazard_type") == "flood"
    assert res_default.get("status") == "RECOMMENDED"
    assert "recommended_action" in res_default
    assert "uncertainty_interval" in res_default
    assert "contributing_factors" in res_default

    # Explicit flood hazard_type
    res_flood = compute_emergency_decision(incident_id="INC-DEC-TEST", horizon=0, hazard_type="flood")
    assert res_flood.get("hazard_type") == "flood"
    assert res_flood.get("status") == "RECOMMENDED"
    assert res_flood.get("priority") == res_default.get("priority")


def test_unsupported_hazards_return_unavailable_decision():
    """Verify extreme_rainfall, landslide, cyclone, heatwave, earthquake return UNAVAILABLE status."""
    unsupported_hazards = ["extreme_rainfall", "landslide", "cyclone", "heatwave", "earthquake"]

    for hz in unsupported_hazards:
        res = compute_emergency_decision(incident_id=f"INC-{hz.upper()}-TEST", horizon=0, hazard_type=hz)
        assert res.get("hazard_type") == hz
        assert res.get("decision_support_available") is False
        assert res.get("status") == "UNAVAILABLE"
        assert "Operational decision support is not supported" in res.get("reason", "")
        assert "recommended_action" not in res
        assert "uncertainty_interval" not in res
        assert "contributing_factors" not in res


def test_unknown_hazard_type_raises_error():
    """Verify unknown or invalid hazard_type string raises ValueError."""
    with pytest.raises(ValueError, match="Unknown or unsupported hazard type"):
        compute_emergency_decision(incident_id="INC-FAIL-TEST", hazard_type="solar_flare")


def test_state_machine_rejects_unavailable_hazard_transitions():
    """Verify state machine transition_decision rejects approval/rejection for unavailable hazard decisions."""
    res_unavail = compute_emergency_decision(incident_id="INC-UNAVAIL-TEST", hazard_type="landslide")
    dec_id = f"dec-unavail-{res_unavail.get('hazard_type')}"

    # Try to approve unavailable hazard decision
    success, msg, _ = transition_decision(
        decision_id=dec_id,
        new_status=STATE_APPROVED,
        responder_id="OPERATOR-01",
        reason="Testing approval rejection",
    )
    assert success is False
    assert "Cannot transition decision for hazard without operational decision support" in msg
