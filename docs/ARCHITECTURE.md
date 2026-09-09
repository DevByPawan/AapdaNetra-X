# AapdaNetra-X — System Architecture & Design Documentation

**Emergency Intelligence Platform — Full-Stack ML Disaster Monitoring & Response System**

> [!NOTE]
> **Research & Prototype Disclaimer**: AapdaNetra-X is currently operating in **Research-Grade Local Prototype Mode** using physics-informed synthetic hydro-meteorological data. Models and route calculations are evaluated for demonstration and software architecture validation, **not** for real-world emergency life-safety deployment.

---

## 1. High-Level Architecture Overview

AapdaNetra-X follows a clean, decoupled full-stack architecture comprising a **FastAPI Intelligence Engine backend** and a **React 19 + Vite + Leaflet Command Center frontend**.

```mermaid
graph TD
    subgraph Client ["Frontend Layer (React 19 + TypeScript)"]
        UI["Command Center Dashboard"]
        Map["Leaflet Situational Map"]
        Controls["Time-Horizon Slider & Quick Buttons"]
        SimUI["What-If Simulation Controls"]
        RecPanel["AI Recommendation & SHAP Trace"]
        Store["Zustand Map & Toast Store"]
        Query["TanStack Query (API Layer)"]
    end

    subgraph Server ["FastAPI API Layer"]
        API["FastAPI REST Router (/api)"]
        Schema["Pydantic v2 Schema Validator"]
    end

    subgraph Service ["Intelligence Services Layer"]
        RiskEng["Risk Engine Service"]
        ExplainEng["SHAP Explainability Service"]
        RouteEng["NetworkX Route Engine"]
    end

    subgraph Core ["ML & Graph Core Layer"]
        GBR["GradientBoostingRegressor Model"]
        TreeExp["SHAP TreeExplainer"]
        RoadGraph["NetworkX DiGraph (Road Network)"]
        Validator["Feature Cleaner & Thresholds"]
    end

    subgraph Data ["Data & Artifacts Layer"]
        ModelArtifact["ml/models/risk_gbr.joblib"]
        ModelMeta["ml/models/model_metadata.json"]
        SimData["app/data/simulated.py"]
    end

    UI --> Query
    Controls --> Store
    Store --> Query
    SimUI --> Query
    Query -->|HTTP REST /api| API
    API --> Schema
    Schema --> Service
    RiskEng --> Validator
    Validator --> GBR
    GBR --> ModelArtifact
    ExplainEng --> TreeExp
    TreeExp --> GBR
    RouteEng --> RoadGraph
    RoadGraph --> RiskEng
    Service -->|JSON Data| API
    API -->|HTTP Response| Query
    Query --> UI
    Query --> Map
    Query --> RecPanel
```

---

## 2. Intelligence Pipeline Flow

The core intelligence pipeline transforms physical hydro-meteorological inputs into explainable risk predictions and safe evacuation routes:

```mermaid
graph TD
    A["1. Environmental / Scenario Inputs<br/>(Rainfall, Water Level, Congestion, Exposure)"] --> B["2. Data Validation & Feature Engineering<br/>(Bounds Clipping & Default Fills)"]
    B --> C["3. ML Risk Prediction<br/>(scikit-learn GradientBoostingRegressor)"]
    C --> D["4. Risk Classification<br/>(LOW / MODERATE / HIGH / CRITICAL Thresholds)"]
    D --> E["5. SHAP Explainability<br/>(shap.TreeExplainer Feature Attributions)"]
    E --> F["6. Risk-Aware NetworkX Routing<br/>(Dijkstra Search & Edge Cost Matrix)"]
    F --> G["7. Emergency Recommendation<br/>(Route Choice + Safety Score + Reasoning)"]
    G --> H["8. Command Center Dashboard<br/>(React UI + Leaflet Polylines + Decision Trace)"]
```

---

## 3. What-If Simulation Pipeline

```mermaid
sequenceDiagram
    autonumber
    actor Operator as Command Center Operator
    participant UI as What-If Simulation UI
    participant API as FastAPI POST /api/simulation
    participant Engine as Risk Engine Service
    participant ML as GBR Model
    participant SHAP as SHAP Explainer
    participant NX as NetworkX Router

    Operator->>UI: Adjusts Sliders (Rainfall x1.8, Blockage=True)
    UI->>API: POST /api/simulation (payload)
    API->>Engine: run_simulation_engine(payload)
    Engine->>ML: predict_risk(scenario_features)
    ML-->>Engine: Scenario Risk = 49.3 (MODERATE)
    Engine->>SHAP: explain_prediction(scenario_features)
    SHAP-->>Engine: Updated Feature Contributions
    Engine->>NX: optimize_routes(predicted_risk=49.3, blockage=True)
    NX-->>Engine: Rerouted Path B → F → G → H (Avoids Checkpoint D)
    Engine-->>API: SimulationResponse Payload
    API-->>UI: JSON (baselineRisk, scenarioRisk, riskDelta, routeRecommendation)
    UI->>Operator: Renders Scenario Delta (+22.2) & Updated Route Badge
```

---

## 4. Time-Horizon Propagation Pipeline

Changing the time horizon recalculates model inferences across the entire system:

```mermaid
graph LR
    subgraph Horizons ["Time Horizons"]
        H0["NOW (0 MIN)"]
        H1["+10 MIN"]
        H2["+20 MIN"]
        H3["+30 MIN"]
    end

    subgraph Processing ["Per-Horizon Propagation"]
        Features["Horizon Feature Progression"]
        MLInference["ML Risk Prediction"]
        SHAPAttr["SHAP Feature Attributions"]
        NXRoute["NetworkX Route Optimization"]
    end

    subgraph Output ["Dashboard UI"]
        MapUI["Leaflet Map Heatmap & Polylines"]
        TraceUI["Decision Trace Panel"]
        StatsUI["Incident Overview Stats"]
    end

    H0 --> Features
    H1 --> Features
    H2 --> Features
    H3 --> Features

    Features --> MLInference
    MLInference --> SHAPAttr
    MLInference --> NXRoute
    SHAPAttr --> TraceUI
    NXRoute --> MapUI
    MLInference --> StatsUI
```

---

## 5. Repository Directory Architecture

```text
AapdaNetra-X/
├── frontend/                     # React 19 + TypeScript Client App
│   ├── src/
│   │   ├── components/           # UI Components (Map, Panels, Header, Charts)
│   │   ├── config/               # Navigation & app config
│   │   ├── data/                 # Client fallback simulated data
│   │   ├── hooks/                # Custom React hooks
│   │   ├── pages/                # CommandCenter & branded stub pages
│   │   ├── services/             # Axios API client functions
│   │   ├── store/                # Zustand global map & toast state
│   │   ├── types/                # TypeScript interface definitions
│   │   └── utils/                # Risk color helpers & formatters
│   ├── index.html                # Entry HTML
│   ├── package.json              # Frontend npm dependencies
│   └── vite.config.ts            # Vite build & API proxy setup
├── backend/                      # FastAPI Backend Application
│   ├── app/
│   │   ├── data/                 # Simulated disaster data sources
│   │   ├── models/               # Pydantic v2 request/response schemas
│   │   ├── routers/              # REST API route handlers
│   │   ├── services/             # Risk & simulation engine services
│   │   ├── config.py             # App environment configuration
│   │   └── main.py               # FastAPI entry point & CORS setup
│   ├── tests/                    # Pytest test suite (30 passed tests)
│   └── requirements.txt          # Python dependencies
├── ml/                           # ML & Explainability Subsystem
│   ├── features/                 # Feature specs, cleaner & risk thresholds
│   ├── training/                 # Data generator & GBR model training script
│   ├── models/                   # Serialized GBR model artifact & metadata
│   ├── inference/                # Model-agnostic risk predictor interface
│   ├── explainability/           # SHAP TreeExplainer service & mapping
│   └── routing/                  # NetworkX graph, cost functions & optimizer
├── docs/                         # Architecture documentation & diagrams
├── reference/                    # Immutable Visual Reference Prototype
└── README.md                     # Research Project README
```

---

## 6. Core Subsystems Specification

### **A. ML Risk Engine (`ml/inference/`, `ml/training/`, `ml/features/`)**
- **Algorithm**: `scikit-learn.ensemble.GradientBoostingRegressor` (120 estimators, max depth 4, learning rate 0.08).
- **Features (7)**: `rainfall_intensity`, `rainfall_trend`, `water_level`, `water_level_trend`, `road_congestion`, `population_exposure`, `infrastructure_vulnerability`.
- **Classification Thresholds**:
  - `LOW`: $[0.0, 30.0)$
  - `MODERATE`: $[30.0, 60.0)$
  - `HIGH`: $[60.0, 85.0)$
  - `CRITICAL`: $[85.0, 100.0]$
- **Reliability Calculation**: `prediction_reliability` ($0.50 - 0.98$) measures feature input completeness and margin distance from synthetic domain training bounds.

### **B. Explainable AI / SHAP Engine (`ml/explainability/`)**
- **Explainer**: `shap.TreeExplainer` on pre-trained GBR model artifact.
- **Additivity**: $\text{Model Prediction} = \text{Base Value} + \sum \text{SHAP}_i$.
- **Feature Attribution**: Maps technical feature keys to emergency-management domain labels and calculates relative contribution percentage:
  $$\text{Contribution \%}_i = \frac{|\text{SHAP}_i|}{\sum |\text{SHAP}_j|} \times 100$$

### **C. NetworkX Route Optimizer (`ml/routing/`)**
- **Graph Topology**: `networkx.DiGraph` representing Yamuna Floodplain road network.
- **Edge Cost Equation**:
  $$\text{Cost}_{u \to v} = w_d \cdot \text{distance} + w_t \cdot \text{time} + w_r \cdot \left(\frac{\text{risk}}{100}\right) \times 15 + w_c \cdot \text{congestion} \times 10 + \text{BlockagePenalty}$$
- **Routing Algorithm**: `networkx.shortest_simple_paths` (Dijkstra search) to compute recommended path and non-duplicate alternative evacuation routes.

---

## 7. API Endpoints Reference

| Method | Endpoint | Query / Body Params | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | None | Returns operational status, API version, and timestamp. |
| `GET` | `/api/incident` | None | Active disaster incident metadata (Sector B Yamuna Floodplain). |
| `GET` | `/api/risk` | `horizon: int` ($0..3$) | Dynamic ML flood risk score, category, reliability, and heatmap zones. |
| `GET` | `/api/forecast` | None | Multi-point hazard risk timeline points ($0..60$ min). |
| `GET` | `/api/routes` | `horizon: int` ($0..3$) | NetworkX risk-optimized evacuation routes & SHAP decision trace. |
| `GET` | `/api/explainability` | `horizon: int` ($0..3$) | Detailed SHAP feature attributions and base value deltas. |
| `GET` | `/api/alerts` | None | Real-time emergency alert logs. |
| `POST` | `/api/response/approve` | `incidentId`, `responderId` | Triggers response plan workflow. |
| `POST` | `/api/simulation` | `evacuationPace`, `rainfallMultiplier`, `drainageEfficiency`, `routeBlockage` | Counterfactual What-If scenario ML simulation. |

---

## 8. Security & Robustness Summary

- **CORS Middleware**: Configured to restrict origins via `settings.cors_origins` (defaults to `http://localhost:5173`).
- **Input Validation**: Pydantic v2 schemas enforce boundary constraints on all incoming requests.
- **Out-of-Bounds Protection**: Feature validator clips extreme feature values to valid physical domain bounds without crashing.
- **Singleton Caching**: ML Model, TreeExplainer, and NetworkX Graph instance are loaded as global singletons to eliminate redundant disk I/O and initialization overhead.
