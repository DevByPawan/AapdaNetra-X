# AapdaNetra-X — Step-by-Step Evaluation & Demo Runbook

**A Reproducible Evaluator Guide for Demonstration & API Verification**

> [!NOTE]
> All commands in this runbook execute against the live FastAPI backend server (`http://localhost:8000`) and React Command Center UI (`http://localhost:5173`). Synthetic or demo payloads are explicitly labeled.

---

## 1. System Startup Prerequisites

### Start Backend API Server
```bash
cd backend
source .venv/bin/activate
PYTHONPATH=backend:. uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Start Frontend Dev Server
```bash
cd frontend
npm run dev
```

---

## 2. Step-by-Step API Evaluation Commands

### Step 1: System Health & Operational Status Check
Verify backend readiness, API version, and environment mode.

```bash
curl -s http://localhost:8000/health | jq
```
**Expected Output**:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "data_mode": "simulated",
  "environment": "development"
}
```

---

### Step 2: Flood Risk Assessment (`NOW` Horizon)
Request the real-time ML risk prediction, operational risk category, and heatmap bounds.

```bash
curl -s "http://localhost:8000/api/risk?horizon=0" | jq
```
**Expected Response**:
```json
{
  "risk_score": 27.1,
  "risk_level": "LOW",
  "reliability": 0.94,
  "horizon_minutes": 0,
  "heatmap_zones": [...]
}
```

---

### Step 3: SHAP Feature Explainability Decision Trace
Inspect the local SHAP feature attributions explaining *why* the risk score was calculated.

```bash
curl -s "http://localhost:8000/api/explainability?horizon=0" | jq
```
**Expected Response**:
```json
{
  "risk_score": 27.1,
  "base_value": 45.2,
  "top_drivers": [
    {
      "feature_name": "Population Exposure",
      "impact_percentage": 42.1,
      "direction": "decreased"
    },
    {
      "feature_name": "Water Level",
      "impact_percentage": 32.5,
      "direction": "increased"
    }
  ]
}
```

---

### Step 4: Evacuation Route Optimization & Blockage Handling
Fetch optimal evacuation routes avoiding flood hazards and road blockages.

```bash
curl -s "http://localhost:8000/api/routes?horizon=0" | jq
```
**Expected Response**:
```json
{
  "recommended_route": {
    "route_id": "route_alpha",
    "name": "North Expressway (Safe Bypass)",
    "travel_time_min": 14.2,
    "distance_km": 8.5,
    "hazard_exposure_score": 12.0,
    "path_nodes": ["A", "B", "C", "D"]
  },
  "alternative_routes": [...]
}
```

---

### Step 5: Counterfactual What-If Scenario Simulation
Execute a scenario simulation escalating rainfall multiplier ($1.8\times$) and enabling route blockage.

```bash
curl -s -X POST "http://localhost:8000/api/simulation" \
  -H "Content-Type: application/json" \
  -d '{
    "evacuationPace": 1.2,
    "rainfallMultiplier": 1.8,
    "drainageEfficiency": 0.7,
    "routeBlockage": true
  }' | jq
```
**Expected Response**:
```json
{
  "baseline_risk": 27.1,
  "scenario_risk": 49.1,
  "risk_delta": 22.0,
  "scenario_category": "MODERATE",
  "rerouted_path": ["A", "F", "G", "H"],
  "narrative": "Rainfall escalation (+80%) and primary route blockage increase risk delta by +22.0 points. Traffic rerouted via South Bypass."
}
```

---

### Step 6: Unsupported-Hazard Safeguard Verification
Verify that requesting decision support for an unsupported hazard type (e.g. `earthquake`) returns a safe disclaimer instead of falling back to flood models.

```bash
curl -s "http://localhost:8000/api/decision/recommend?hazard_type=earthquake" | jq
```
**Expected Response**:
```json
{
  "hazard_type": "earthquake",
  "decision_support_available": false,
  "disclaimers": [
    "UNSUPPORTED_HAZARD: No operational ML model for specified hazard type 'earthquake'. System operates exclusively for flood hazard evaluation."
  ]
}
```

---

### Step 7: Emergency Decision Recommendation & Human-in-the-Loop (HITL) Approval
Generate an emergency response plan recommendation, followed by explicit human responder approval.

1. **Generate Recommendation**:
```bash
curl -s "http://localhost:8000/api/decision/recommend?hazard_type=flood" | jq
```
**Expected Status**: `"status": "RECOMMENDED"`

2. **Authorized Human Approval**:
```bash
curl -s -X POST "http://localhost:8000/api/decision/approve" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer responder-token-secret-456" \
  -d '{
    "decision_id": "dec-rec-flood-01",
    "responder_id": "RESP-DELHI-NORTH-01",
    "reason": "Operational safety verified by Incident Commander"
  }' | jq
```
**Expected Response**:
```json
{
  "decision_id": "dec-rec-flood-01",
  "approved": true,
  "status": "APPROVED",
  "timestamp": "2026-10-10T17:28:00Z"
}
```

---

### Step 8: Real Data Provenance (Yamuna July 2025 Dataset) Validation
Verify that real historical Yamuna flood data preprocessor is accessible.

```bash
curl -s "http://localhost:8000/api/data/freshness" | jq
```
**Expected Response**:
```json
{
  "data_mode": "simulated",
  "sources": {
    "yamuna_2025_pdf": "available",
    "provenance": "CWC Hathnikund Discharge & Old Railway Bridge Water Level PDF Report (July 2025)"
  }
}
```

---

## 3. Command Center UI Walkthrough Guide

1. Open `http://localhost:5173` in a web browser.
2. View real-time risk score ($27.1$, LOW) on the header metric card and Leaflet situational map.
3. Click **APPROVE RESPONSE PLAN** to view the **SHAP Decision Trace** panel.
4. Click **+30 MIN** on the Time Horizon bar. Observe the risk score increase to $42.2$ (MODERATE), heatmap radii expansion, and SHAP feature ranking update (*Water Level* becomes primary driver).
5. Scroll to the **What-If Simulation** controls.
6. Set **Rainfall Multiplier** to `1.8x`, toggle **Route Blockage** to `ON`, and click **RUN SIMULATION**.
7. Observe risk delta ($+22.0$), updated narrative, and NetworkX rerouting via `South Bypass`.
