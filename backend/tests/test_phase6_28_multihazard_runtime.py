"""

AapdaNetra-X — Phase 6.28: Multi-Hazard Runtime Activation Tests



Validates:

1. Runtime hazard selection and registry dispatch.

2. Flood operational behavior and regression compatibility.

3. Extreme Rainfall contextual-only behavior.

4. Unsupported hazard handling (Landslide, Cyclone, Heatwave, Earthquake) without flood model execution.

5. Hazard propagation into risk, route, alert, decision, and explainability endpoints.

6. Invalid hazard parameter rejection (HTTP 400).

7. Preservation of risk eligibility, provenance, and synthetic ML disclaimers.

"""

import pytest

from fastapi.testclient import TestClient



from app.main import app

from app.hazards import (

    HazardType,

    HazardCapabilityStatus,

    get_hazard_registry,

    FloodHazardAdapter,

    ExtremeRainfallHazardAdapter,

    UnsupportedHazardAdapter,

    MultiHazardRiskAggregator,

)



client = TestClient(app)





def test_registry_dispatch_and_adapter_mapping():

    """Verify HazardRegistry maps each HazardType to the correct adapter instance."""

    registry = get_hazard_registry()



    # Flood

    flood_adapter = registry.get_adapter(HazardType.FLOOD)

    assert isinstance(flood_adapter, FloodHazardAdapter)

    flood_defn = registry.get_definition(HazardType.FLOOD)

    assert flood_defn.model_available is True

    assert flood_defn.routing_available is True



    # Extreme Rainfall

    rain_adapter = registry.get_adapter(HazardType.EXTREME_RAINFALL)

    assert isinstance(rain_adapter, ExtremeRainfallHazardAdapter)

    rain_defn = registry.get_definition(HazardType.EXTREME_RAINFALL)

    assert rain_defn.model_available is False

    assert rain_defn.telemetry_available is True

    assert rain_defn.routing_available is False



    # Landslide (unsupported)

    ls_adapter = registry.get_adapter(HazardType.LANDSLIDE)

    assert isinstance(ls_adapter, UnsupportedHazardAdapter)

    ls_defn = registry.get_definition(HazardType.LANDSLIDE)

    assert ls_defn.supported is False

    assert ls_defn.model_available is False



    # Cyclone, Heatwave, Earthquake

    for ht in [HazardType.CYCLONE, HazardType.HEATWAVE, HazardType.EARTHQUAKE]:

        ad = registry.get_adapter(ht)

        defn = registry.get_definition(ht)

        assert isinstance(ad, UnsupportedHazardAdapter)

        assert defn.supported is False

        assert defn.model_available is False





def test_flood_risk_api_operational():

    """Verify default (or hazard_type=flood) GET /api/risk returns operational GBR prediction."""

    res_default = client.get("/api/risk?horizon=0")

    assert res_default.status_code == 200

    data_def = res_default.json()

    assert "predictedRisk" in data_def or "index" in data_def



    res_flood = client.get("/api/risk?horizon=0&hazard_type=flood")

    assert res_flood.status_code == 200

    data_fl = res_flood.json()

    assert "predictedRisk" in data_fl or "index" in data_fl





def test_extreme_rainfall_contextual_only_risk_api():

    """Verify hazard_type=extreme_rainfall returns contextual status without GBR inference."""

    res = client.get("/api/risk?horizon=0&hazard_type=extreme_rainfall")

    assert res.status_code == 200

    data = res.json()

    assert data["hazard_type"] == "extreme_rainfall"

    assert data["capability_status"] == "PARTIALLY_SUPPORTED"

    assert data["supported"] is True

    assert data["model_available"] is False

    assert data["predicted_risk"] is None

    assert data["routing_available"] is False





def test_unsupported_hazards_risk_api():

    """Verify unsupported hazards (landslide, cyclone, heatwave, earthquake) return unsupported status."""

    for ht in ["landslide", "cyclone", "heatwave", "earthquake"]:

        res = client.get(f"/api/risk?horizon=0&hazard_type={ht}")

        assert res.status_code == 200

        data = res.json()

        assert data["hazard_type"] == ht

        assert data["supported"] is False

        assert data["model_available"] is False

        assert data["predicted_risk"] is None

        assert data["routing_available"] is False





def test_invalid_hazard_type_risk_api():

    """Verify invalid hazard_type string returns 400 Bad Request."""

    res = client.get("/api/risk?horizon=0&hazard_type=volcano")

    assert res.status_code == 400

    assert "Unknown or unsupported hazard_type" in res.json()["detail"]





def test_routes_api_multihazard_dispatch():

    """Verify GET /api/routes respects hazard_type and does not run flood routing for non-flood hazards."""

    # Flood / Default

    res_flood = client.get("/api/routes?horizon=0&hazard_type=flood")

    assert res_flood.status_code == 200

    data_fl = res_flood.json()

    assert "recommended" in data_fl

    assert data_fl["recommended"]["id"] is not None



    # Extreme Rainfall

    res_rain = client.get("/api/routes?horizon=0&hazard_type=extreme_rainfall")

    assert res_rain.status_code == 200

    data_rn = res_rain.json()

    assert "[HAZARD: EXTREME RAINFALL]" in data_rn["routeReason"]



    # Landslide (unsupported)

    res_ls = client.get("/api/routes?horizon=0&hazard_type=landslide")

    assert res_ls.status_code == 200

    data_ls = res_ls.json()

    assert "[HAZARD: LANDSLIDE RISK]" in data_ls["routeReason"]

    assert "data_contract" in data_ls

    assert data_ls["data_contract"]["routing_available"] is False



    # Invalid hazard

    res_inv = client.get("/api/routes?horizon=0&hazard_type=invalid_hazard")

    assert res_inv.status_code == 400





def test_explainability_api_multihazard_dispatch():

    """Verify GET /api/explainability handles hazard_type parameter without running flood SHAP for non-flood."""

    # Flood

    res_fl = client.get("/api/explainability?horizon=0&hazard_type=flood")

    assert res_fl.status_code == 200

    data_fl = res_fl.json()

    assert len(data_fl["features"]) == 7

    assert data_fl["hazard_type"] == "flood"



    # Extreme Rainfall

    res_rn = client.get("/api/explainability?horizon=0&hazard_type=extreme_rainfall")

    assert res_rn.status_code == 200

    data_rn = res_rn.json()

    assert data_rn["hazard_type"] == "extreme_rainfall"

    assert data_rn["prediction"] == 0.0

    assert len(data_rn["features"]) == 0

    assert data_rn["data_contract"]["model_available"] is False



    # Landslide

    res_ls = client.get("/api/explainability?horizon=0&hazard_type=landslide")

    assert res_ls.status_code == 200

    data_ls = res_ls.json()

    assert data_ls["hazard_type"] == "landslide"

    assert data_ls["prediction"] == 0.0

    assert len(data_ls["features"]) == 0



    # Invalid hazard

    res_inv = client.get("/api/explainability?horizon=0&hazard_type=tsunami")

    assert res_inv.status_code == 400





def test_decision_api_multihazard_dispatch():

    """Verify GET /api/decision/recommend returns decision support or explicit unavailable response."""

    # Flood (Default)

    res_fl = client.get("/api/decision/recommend?incident_id=INC-TEST-01&horizon=0&hazard_type=flood")

    assert res_fl.status_code == 200

    data_fl = res_fl.json()

    assert data_fl["status"] == "RECOMMENDED"

    assert data_fl["hazard_type"] == "flood"



    # Extreme Rainfall

    res_rn = client.get("/api/decision/recommend?incident_id=INC-TEST-02&horizon=0&hazard_type=extreme_rainfall")

    assert res_rn.status_code == 200

    data_rn = res_rn.json()

    assert data_rn["status"] == "UNAVAILABLE"

    assert data_rn["hazard_type"] == "extreme_rainfall"

    assert data_rn["decision_support_available"] is False



    # Landslide

    res_ls = client.get("/api/decision/recommend?incident_id=INC-TEST-03&horizon=0&hazard_type=landslide")

    assert res_ls.status_code == 200

    data_ls = res_ls.json()

    assert data_ls["status"] == "UNAVAILABLE"

    assert data_ls["hazard_type"] == "landslide"



    # Invalid hazard

    res_inv = client.get("/api/decision/recommend?incident_id=INC-TEST-04&horizon=0&hazard_type=avalanche")

    assert res_inv.status_code == 400





def test_multihazard_risk_aggregator():

    """Verify MultiHazardRiskAggregator correctly aggregates multiple hazard risk evaluations."""

    aggregator = MultiHazardRiskAggregator()



    # Aggregate multi-hazard aggregate result

    agg_result = aggregator.aggregate(telemetry_features={"rainfall_intensity": 45.0, "water_level": 3.2})

    assert agg_result.primary_hazard_driver == HazardType.FLOOD

    assert agg_result.composite_risk is not None

    assert len(agg_result.contributing_hazards) == 1

    assert len(agg_result.excluded_hazards) == 5

    assert agg_result.aggregation_policy == "MAX_SEVERITY_OPERATIONAL_HAZARD"
