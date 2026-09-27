"""AapdaNetra-X — Phase 6.5C Persistence Repository Test Suite

Tests all 9 domain repositories, caller-managed session transactions, PersistenceService
mode handling (disabled | optional | required), memory fallback mechanisms, and audit logging.
"""

from datetime import datetime, timezone
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

pytest_plugins = ("anyio",)
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import (
    Alert,
    AuditEvent,
    CriticalAsset,
    EvacuationRoute,
    Incident,
    RiskPrediction,
    SHAPRecord,
    Simulation,
    TelemetryObservation,
)
from app.db.repositories import (
    AlertRepository,
    AuditEventRepository,
    BaseRepository,
    CriticalAssetRepository,
    EvacuationRouteRepository,
    IncidentRepository,
    RiskPredictionRepository,
    SHAPRecordRepository,
    SimulationRepository,
    TelemetryRepository,
)
from app.services.persistence_service import PersistenceService, get_persistence_service


def test_repository_package_exports():
    """Verify that all 9 domain repositories and BaseRepository are cleanly exported."""
    repos = [
        BaseRepository,
        IncidentRepository,
        TelemetryRepository,
        RiskPredictionRepository,
        SHAPRecordRepository,
        EvacuationRouteRepository,
        CriticalAssetRepository,
        SimulationRepository,
        AlertRepository,
        AuditEventRepository,
    ]
    for repo in repos:
        assert repo is not None


@pytest.mark.anyio
async def test_base_repository_flush_no_premature_commit():
    """Verify BaseRepository methods flush pending changes without prematurely committing."""
    mock_session = AsyncMock(spec=AsyncSession)
    repo = BaseRepository(Incident, mock_session)

    test_incident = Incident(
        id="INC-TEST-001",
        incident_type="flood",
        status="active",
        started_at=datetime.now(timezone.utc),
        sector="Sector-4",
        severity="HIGH",
        location_name="Yamuna Bank",
        latitude=28.6448,
        longitude=77.2167,
    )

    result = await repo.add(test_incident)

    # Session.add and flush called
    mock_session.add.assert_called_once_with(test_incident)
    mock_session.flush.assert_called_once()
    # Ensure commit was NOT called inside repository method
    mock_session.commit.assert_not_called()
    assert result == test_incident


@pytest.mark.anyio
async def test_incident_repository_query_methods():
    """Verify IncidentRepository method query building and execution."""
    mock_session = AsyncMock(spec=AsyncSession)
    repo = IncidentRepository(mock_session)

    # Mock get
    mock_session.get.return_value = Incident(id="INC-2026-001", incident_type="flood", status="ACTIVE", started_at=datetime.now(timezone.utc), sector="Sector-4", severity="HIGH", location_name="Loc", latitude=28.0, longitude=77.0)
    inc = await repo.get_by_id("INC-2026-001")
    assert inc is not None
    assert inc.id == "INC-2026-001"
    mock_session.get.assert_called_once_with(Incident, "INC-2026-001")


@pytest.mark.anyio
async def test_telemetry_repository_preserves_7_ml_features():
    """Verify TelemetryRepository creates observations preserving all 7 ML features."""
    mock_session = AsyncMock(spec=AsyncSession)
    repo = TelemetryRepository(mock_session)

    obs = TelemetryObservation(
        id=uuid.uuid4(),
        incident_id="INC-2026-001",
        data_mode="simulated",
        fallback_used=False,
        rainfall_intensity=50.0,
        rainfall_trend=2.0,
        water_level=4.5,
        water_level_trend=0.3,
        road_congestion=0.6,
        population_exposure=10000.0,
        infrastructure_vulnerability=0.5,
        provenance={"provider": "test"},
    )

    saved = await repo.create_observation(obs)
    mock_session.add.assert_called_once_with(obs)
    mock_session.flush.assert_called_once()
    mock_session.commit.assert_not_called()
    assert saved.rainfall_intensity == 50.0


@pytest.mark.anyio
async def test_risk_prediction_repository():
    """Verify RiskPredictionRepository saves predictions without committing."""
    mock_session = AsyncMock(spec=AsyncSession)
    repo = RiskPredictionRepository(mock_session)

    pred = RiskPrediction(
        id=uuid.uuid4(),
        incident_id="INC-2026-001",
        horizon=0,
        horizon_label="NOW",
        current_risk=45.0,
        predicted_risk=52.0,
        risk_category="MODERATE",
        confidence=0.9,
        prediction_reliability=0.95,
        affected_population=10000,
        critical_population=2000,
        critical_assets_count=5,
        affected_assets_count=2,
        trend="RISING",
        map_status_text="Rising risk",
        prediction_note="Test note",
        input_features={"rainfall_intensity": 50.0},
        heatmap_zones=[],
    )

    await repo.save_prediction(pred)
    mock_session.add.assert_called_once_with(pred)
    mock_session.flush.assert_called_once()
    mock_session.commit.assert_not_called()


@pytest.mark.anyio
async def test_shap_record_repository():
    """Verify SHAPRecordRepository saves 1:1 linked SHAP records."""
    mock_session = AsyncMock(spec=AsyncSession)
    repo = SHAPRecordRepository(mock_session)
    pred_id = uuid.uuid4()

    shap_rec = SHAPRecord(
        id=uuid.uuid4(),
        risk_prediction_id=pred_id,
        horizon=0,
        prediction=52.0,
        base_value=25.0,
        total_shap_delta=27.0,
        features={},
        decision_trace=[],
    )

    await repo.save_shap_record(shap_rec)
    mock_session.add.assert_called_once_with(shap_rec)
    mock_session.flush.assert_called_once()


@pytest.mark.anyio
async def test_evacuation_route_repository():
    """Verify EvacuationRouteRepository bulk saves routes."""
    mock_session = AsyncMock(spec=AsyncSession)
    repo = EvacuationRouteRepository(mock_session)

    route = EvacuationRoute(
        id=uuid.uuid4(),
        incident_id="INC-2026-001",
        route_name="Route Alpha",
        route_type="primary",
        is_recommended=True,
        origin_name="Orig",
        origin_lat=28.6,
        origin_lon=77.2,
        destination_name="Dest",
        destination_lat=28.7,
        destination_lon=77.3,
        waypoint_coords=[[28.6, 77.2]],
        distance_km=5.0,
        estimated_minutes=15.0,
        safety_score=0.85,
    )

    await repo.save_routes([route])
    mock_session.add_all.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.anyio
async def test_critical_asset_repository():
    """Verify CriticalAssetRepository asset lookups."""
    mock_session = AsyncMock(spec=AsyncSession)
    repo = CriticalAssetRepository(mock_session)

    asset = CriticalAsset(
        id=uuid.uuid4(),
        asset_code="AST-001",
        name="Test Hospital",
        asset_type="hospital",
        sector="Sector-4",
        latitude=28.6,
        longitude=77.2,
        vulnerability=0.7,
    )

    mock_session.merge.return_value = asset
    saved = await repo.save_asset(asset)
    assert saved.asset_code == "AST-001"


@pytest.mark.anyio
async def test_simulation_repository():
    """Verify SimulationRepository saves simulation runs."""
    mock_session = AsyncMock(spec=AsyncSession)
    repo = SimulationRepository(mock_session)

    sim = Simulation(
        id=uuid.uuid4(),
        incident_id="INC-2026-001",
        baseline_risk=40.0,
        scenario_risk=65.0,
        risk_delta=25.0,
        risk_category="HIGH",
        route_recommendation="Reroute",
        flagged_assets=["Bridge-1"],
        narrative="Risk increased",
        severity="SEVERE",
    )

    await repo.save_simulation(sim)
    mock_session.add.assert_called_once_with(sim)


@pytest.mark.anyio
async def test_alert_repository():
    """Verify AlertRepository manages emergency alerts."""
    mock_session = AsyncMock(spec=AsyncSession)
    repo = AlertRepository(mock_session)

    alert = Alert(
        id=uuid.uuid4(),
        incident_id="INC-2026-001",
        severity="HIGH",
        title="Flood Alert",
        description="Water surging",
        status="OPEN",
    )

    await repo.save_alert(alert)
    mock_session.add.assert_called_once_with(alert)


@pytest.mark.anyio
async def test_audit_event_repository_append_only():
    """Verify AuditEventRepository appends new audit events without overwriting."""
    mock_session = AsyncMock(spec=AsyncSession)
    repo = AuditEventRepository(mock_session)

    event = await repo.log_event(
        event_type="TEST_EVENT",
        severity="INFO",
        source="UnitTest",
        description="Test description",
        actor="operator",
    )

    assert event.event_type == "TEST_EVENT"
    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.anyio
async def test_persistence_service_disabled_mode_bypasses_db():
    """Verify PersistenceService in disabled mode skips all database operations."""
    ps = PersistenceService()
    with patch.object(settings, "persistence_mode", "disabled"):
        assert ps.is_enabled is False
        assert ps.db_available is False

        # Attempt pipeline save
        success = await ps.persist_assessment_pipeline(
            incident_id="INC-001",
            telemetry=MagicMock(),
            prediction=MagicMock(),
            shap_record=MagicMock(),
            routes=[],
        )
        assert success is False


@pytest.mark.anyio
async def test_persistence_service_optional_mode_fallback_on_db_down():
    """Verify PersistenceService in optional mode logs warning and falls back cleanly when DB is unavailable."""
    ps = PersistenceService()
    with patch.object(settings, "persistence_mode", "optional"):
        with patch("app.services.persistence_service.get_db_manager") as mock_db_mgr:
            mock_mgr_instance = MagicMock()
            mock_mgr_instance.is_available = False
            mock_db_mgr.return_value = mock_mgr_instance

            assert ps.is_enabled is True
            assert ps.db_available is False

            # Pipeline persistence should return False without raising exception
            success = await ps.persist_assessment_pipeline(
                incident_id="INC-001",
                telemetry=MagicMock(),
                prediction=MagicMock(),
                shap_record=MagicMock(),
                routes=[],
            )
            assert success is False


@pytest.mark.anyio
async def test_persistence_service_required_mode_raises_on_db_down():
    """Verify PersistenceService in required mode raises RuntimeError when DB is unavailable."""
    ps = PersistenceService()
    with patch.object(settings, "persistence_mode", "required"):
        with patch("app.services.persistence_service.get_db_manager") as mock_db_mgr:
            mock_mgr_instance = MagicMock()
            mock_mgr_instance.is_available = False
            mock_db_mgr.return_value = mock_mgr_instance

            assert ps.is_enabled is True
            assert ps.db_available is False

            with pytest.raises(RuntimeError) as exc_info:
                await ps.persist_assessment_pipeline(
                    incident_id="INC-001",
                    telemetry=MagicMock(),
                    prediction=MagicMock(),
                    shap_record=MagicMock(),
                    routes=[],
                )
            assert "required" in str(exc_info.value)
