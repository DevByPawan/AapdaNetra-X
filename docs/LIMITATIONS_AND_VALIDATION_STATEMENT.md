# AapdaNetra-X — Scientific Limitations & Validation Statement



**Formal Disclosure of Model Training, Data Provenance, Testing Scope, and Operational Boundaries**



**Date**: October 10, 2026

**Version**: Phase 6.34 Final Research Package



---



## 1. Machine Learning Model Training Disclosure



> [!IMPORTANT]

> **Synthetic Training Dataset**: The core `scikit-learn` GradientBoostingRegressor (GBR) risk model (`ml/models/risk_gbr.joblib`) was trained exclusively on a **synthetic, physics-informed hydro-meteorological dataset** comprising 1,000 generated samples (fixed random seed `42`).



* **Model Objective**: Predict continuous flood risk scores ($0.0 - 100.0$) from 7 hydro-meteorological inputs.

* **Scope & Bounds**: The model evaluates software architecture, feature contract compliance, and explainability pipelines. It has **not** been retrained or calibrated on real-world historical disaster telemetry for real-time field deployments.

* **Predictive Accuracy Disclaimer**: Any risk prediction or reliability score ($0.50 - 0.98$) produced by the GBR model represents model confidence relative to its synthetic training distribution and **does not constitute a field-validated life-safety probability**.



---



## 2. Explainability & SHAP Attribution Scope



* **Methodology**: Local feature attributions are calculated using `shap.TreeExplainer` on the GBR model artifact.

* **Attribution Scope**: SHAP values quantify the relative marginal contribution of each input feature to the final prediction score (*"How much did Water Level shift the prediction relative to the baseline dataset mean?"*).

* **Non-Causal Disclaimer**: **SHAP feature attributions are non-causal statistical correlations**. High SHAP attribution for a feature (e.g., *Population Exposure*) indicates model sensitivity to that parameter, **not** physical causality or guaranteed ground-truth flooding.



---



## 3. Data Provenance & Real-Data Preprocessing Boundaries



* **Historical Yamuna 2025 PDF Dataset**: AapdaNetra-X includes automated PDF preprocessors (`backend/app/ml/real_data/`) for real historical hydro-meteorological data extracted from the **Yamuna River Flood Report (July 2025 event)** (`Yamuna_2025.pdf`).

* **Ingested Real Data Signals**: CWC Hathnikund dam discharge rates (cusecs), Yamuna Old Railway Bridge gauge levels (meters), Delhi Traffic Police road closure advisories, and IMD rainfall intensity.

* **Historical ERA5 & Traffic Observations**: Historical ERA5 reanalysis and 2020 traffic datasets are used strictly for offline preprocessing and temporal alignment benchmarks. They are **not** live streaming feeds.

* **GHSL & WorldPop Contextual Layers**: WorldPop population density and GHSL built-up infrastructure raster layers serve as static spatial context baselines. They are **not** field-validated sector-level exposure or infrastructure vulnerability labels.



---



## 4. Automated Test Suite Execution History



### Non-PostGIS Backend Test Suite Results

* **Passing Unit & Integration Tests**: **478 passed**

* **Deselected (PostGIS) Tests**: **64 deselected** (`-m "not postgis"`)

* **Deprecation Warnings**: 3 non-blocking framework warnings (Pydantic V2 config class deprecation, Starlette testclient httpx notice)

* **Honest Run Log**: The full test suite executed 478 passing tests over 28m26s before manual interruption. Targeted sub-suites verified 100% pass across Phases 6.22 through 6.32. This is documented as an **interrupted run with 478 verified passing tests**, not a full-suite pass.



### PostGIS Database Spatial Validation Status

* **Status**: **UNVERIFIED / DESELECTED IN SUITE RUN**

* **Details**: 64 PostGIS-tagged spatial database tests were deselected (`-m "not postgis"`) because an active PostgreSQL/PostGIS database container/service was offline during test execution. While GIS data adapter contracts are implemented in code, live spatial SQL queries against a PostGIS daemon remain unverified.



---



## 5. Measured Empirical Subsystem Latencies



Micro-benchmarks executed on the local host environment:



| Subsystem / Engine | Measured Average Latency | Operational SLA Target | Status |

| :--- | :--- | :--- | :--- |

| **ML Risk Prediction** | **0.419 ms / op** | < 50 ms | **PASSED** |

| **ML SHAP Explainability** | **0.516 ms / op** | < 100 ms | **PASSED** |

| **Risk Engine Aggregation** | **0.846 ms / op** | < 100 ms | **PASSED** |

| **Decision Support Recommendation** | **1.794 ms / op** | < 200 ms | **PASSED** |

| **Scenario Simulation Engine** | **3.508 ms / op** | < 500 ms | **PASSED** |



**Total End-to-End Decision Pipeline Execution Time**: **< 10.0 ms**.



---



## 6. Deployment Prerequisites & Future Work



### Production Deployment Prerequisites

1. Active PostgreSQL + PostGIS spatial database instance for GIS query execution.

2. Production security configuration (`auth_enabled=True`, non-empty `api_key`, non-default `secret_key`, explicit `cors_origins`).

3. External live API key provisioning for OpenWeatherMap and CWC telemetry feeds.

4. Model recalibration using field-verified multi-year hydro-meteorological sensor data.



### Future Research Directions

- Calibration of GBR and deep learning risk models on multi-regional historical flood events.

- Real-time WebSockets / SSE synchronization with physical IoT river gauge sensors.

- Integration of live satellite radar (Sentinel-1 SAR) inundation extent rasters.
