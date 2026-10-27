# AapdaNetra-X — Final Artifact & File Inventory



**Comprehensive Inventory of System Modules, Datasets, Test Suites, and Documentation**



**Date**: October 10, 2026

**Phase**: Phase 6.34 Final Research Package



---



## 1. Documentation & Validation Reports (`docs/`, root)



| File Path | Description / Purpose |

| :--- | :--- |

| [`README.md`](file:///Users/pawanagrahari/Desktop/AapdaNetra-X/README.md) | Primary repository overview, key capabilities, architecture diagrams, and quickstart guide. |

| [`docs/ARCHITECTURE.md`](file:///Users/pawanagrahari/Desktop/AapdaNetra-X/docs/ARCHITECTURE.md) | Technical system architecture, intelligence pipeline, state diagrams, and security design. |

| [`docs/DEMO_RUNBOOK.md`](file:///Users/pawanagrahari/Desktop/AapdaNetra-X/docs/DEMO_RUNBOOK.md) | Reproducible step-by-step evaluator runbook with API curl examples and UI guide. |

| [`docs/LIMITATIONS_AND_VALIDATION_STATEMENT.md`](file:///Users/pawanagrahari/Desktop/AapdaNetra-X/docs/LIMITATIONS_AND_VALIDATION_STATEMENT.md) | Formal scientific integrity statement, synthetic model disclosures, and test scope. |

| [`docs/PHASE_6_33_VALIDATION_REPORT.md`](file:///Users/pawanagrahari/Desktop/AapdaNetra-X/docs/PHASE_6_33_VALIDATION_REPORT.md) | Detailed Phase 6.33 system validation and empirical benchmarking report. |

| [`docs/FILE_INVENTORY.md`](file:///Users/pawanagrahari/Desktop/AapdaNetra-X/docs/FILE_INVENTORY.md) | This document — final repository artifact and file inventory. |



---



## 2. Backend Engine Subsystem (`backend/app/`)



### Core & Infrastructure (`backend/app/core/`, `backend/app/config.py`, `backend/app/main.py`)

- `backend/app/main.py`: FastAPI entry point, CORS middleware, API router mounting, rate limit initialization.

- `backend/app/config.py`: Centralized environment settings, secret validation, production security rules.

- `backend/app/core/security.py`: Token authentication, API key verification, RBAC permissions.

- `backend/app/core/rate_limit.py`: Sliding window IP rate limiter middleware.



### API Routers (`backend/app/routers/`)

- `backend/app/routers/routes.py`: Evacuation pathfinding & routing endpoints.

- `backend/app/routers/simulation.py`: Counterfactual What-If scenario simulation endpoint.

- `backend/app/routers/decision.py`: Emergency decision recommendation & HITL approval/rejection endpoints.

- `backend/app/routers/events.py`: Real-time SSE streaming endpoint (`/api/events/stream`).

- `backend/app/routers/explainability.py`: SHAP feature attribution & decision trace endpoint.

- `backend/app/routers/alerts.py`: Intelligent emergency alert log endpoint.



### Business Logic Services (`backend/app/services/`)

- `backend/app/services/risk_engine.py`: Core risk aggregation & simulation execution engine.

- `backend/app/services/decision_service.py`: Emergency recommendation engine & HITL lifecycle manager.

- `backend/app/services/scenario_service.py`: Counterfactual scenario simulation engine.

- `backend/app/services/persistence_service.py`: Decision state persistence & audit trail logger.

- `backend/app/services/risk_contract.py`: Risk response schema contracts & normalization.



### Data Adapters & Real-Data Preprocessors (`backend/app/data/`, `backend/app/ml/`)

- `backend/app/data/providers/base.py`: Base abstract data provider adapter interface.

- `backend/app/data/providers/data_adapter.py`: Hybrid data mode coordinator.

- `backend/app/data/providers/weather_adapter.py`: OpenWeatherMap live & fallback weather adapter.

- `backend/app/data/providers/water_level_adapter.py`: Gauge water level data provider.

- `backend/app/data/providers/traffic_adapter.py`: Road traffic congestion provider.

- `backend/app/data/providers/population_adapter.py`: Population density & exposure adapter.

- `backend/app/data/providers/infrastructure_adapter.py`: Asset vulnerability adapter.

- `backend/app/ml/real_data/provenance.py`: Historical Yamuna July 2025 PDF preprocessor & data aligner.

- `backend/app/ml/real_data/cwc_pdf_extractor.py`: PDF table extractor for CWC Hathnikund discharge data.



### Pub/Sub Event Broker (`backend/app/events/`)

- `backend/app/events/broker.py`: In-process & PostgreSQL NOTIFY cross-worker event broker.

- `backend/app/events/schemas.py`: Event envelope and event type schemas.



---



## 3. Machine Learning & Explainability Subsystem (`ml/`)



- `ml/features/schema.py`: 7-feature schema definitions, bounds validation, default fills, risk categorizer.

- `ml/training/train.py`: Synthetic data generator & GradientBoostingRegressor training pipeline.

- `ml/models/risk_gbr.joblib`: Trained GBR model binary artifact.

- `ml/models/model_metadata.json`: Model version, hyperparameter specifications, and training metadata.

- `ml/inference/predictor.py`: Model-agnostic risk predictor interface & reliability calculator.

- `ml/explainability/explainer.py`: SHAP TreeExplainer service & feature attribution label mapping.

- `ml/routing/optimizer.py`: NetworkX risk-aware Dijkstra pathfinder & blockage cost optimizer.

- `ml/routing/models.py`: Evacuation path request and response data structures.



---



## 4. Data Storage & Real Datasets (`data/`, root)



- `Yamuna_2025.pdf`: Real historical CWC & IMD Yamuna River Flood Report (July 2025 event).

- `pdf_text.txt`: Raw text extracted from Yamuna_2025.pdf.

- `data/raw/`: Raw telemetry files and historical data extracts.

- `data/simulated/risk_history.json`: Baseline simulated risk trajectory logs.

- `data/simulated/alerts.json`: Baseline simulated emergency alerts.



---



## 5. Automated Test Suite (`backend/tests/`)



- `backend/tests/test_phase6_22_3_real_data_preprocessing.py`: Yamuna 2025 PDF preprocessing tests.

- `backend/tests/test_phase6_22_4_alignment.py`: Temporal alignment and trend calculation tests.

- `backend/tests/test_phase6_22_5_real_data_validation.py`: Real data bounds validation tests.

- `backend/tests/test_phase6_22_6_event_validation.py`: Event closure and payload validation.

- `backend/tests/test_phase6_22_7_closure.py`: Phase closure integrity verification.

- `backend/tests/test_phase6_23_real_data_runtime.py`: Real data runtime adapter tests.

- `backend/tests/test_phase6_24_data_freshness.py`: Telemetry freshness & stale data fallback tests.

- `backend/tests/test_phase6_25_risk_engine_contract.py`: 7-feature risk engine contract tests.

- `backend/tests/test_phase6_26_real_data_explainability.py`: SHAP attribution tests on real datasets.

- `backend/tests/test_phase6_27_dynamic_evacuation_contract.py`: NetworkX route optimizer contract tests.

- `backend/tests/test_phase6_28_multihazard_runtime.py`: Multi-hazard capability & unsupported hazard safeguard tests.

- `backend/tests/test_phase6_29_scenario_engine.py`: Counterfactual What-If scenario simulation tests.

- `backend/tests/test_phase6_30_e2e_pipeline.py`: End-to-end intelligence pipeline tests.

- `backend/tests/test_phase6_31_resilience.py`: Circuit breaker & fallback resilience tests.

- `backend/tests/test_phase6_32_security_hardening.py`: Authentication, RBAC, rate limiting, CORS, and error sanitization tests.



---



## 6. Frontend Client Application (`frontend/`)



- `frontend/src/pages/CommandCenter.tsx`: Main Command Center UI dashboard.

- `frontend/src/components/bottom/WhatIfSimulation.tsx`: Counterfactual scenario simulation controls.

- `frontend/src/components/bottom/HazardForecastChart.tsx`: Multi-horizon risk timeline chart.

- `frontend/src/store/index.ts`: Zustand global state store for map, risk, and toast alerts.

- `frontend/src/services/`: Axios HTTP API client integration functions.
