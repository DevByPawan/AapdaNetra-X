"""
AapdaNetra-X — Phase 6.25 Risk Engine Production Data Contract
Defines strict input validation, completeness checking, provenance classification,
and inference-eligibility rules at the risk engine boundary.
"""
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from ml.features.schema import FEATURE_ORDER, FEATURE_SPECS


class InferenceEligibilityStatus(str, Enum):
    ELIGIBLE_SIMULATED = "ELIGIBLE_SIMULATED"
    ELIGIBLE_HYBRID = "ELIGIBLE_HYBRID"
    ELIGIBLE_REAL = "ELIGIBLE_REAL"
    INELIGIBLE_INCOMPLETE_EVIDENCE = "INELIGIBLE_INCOMPLETE_EVIDENCE"
    INELIGIBLE_INVALID_INPUT = "INELIGIBLE_INVALID_INPUT"


class FeatureClassification(str, Enum):
    MEASURED = "MEASURED"
    REAL_DERIVED = "REAL_DERIVED"
    HISTORICAL_BASELINE = "HISTORICAL_BASELINE"
    CONTEXTUAL_STATIC = "CONTEXTUAL_STATIC"
    PROVISIONAL = "PROVISIONAL"
    SIMULATED = "SIMULATED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class RiskEngineDataContractResult:
    """
    Structured validation result evaluated at the Risk Engine input boundary.
    """
    is_valid_structure: bool
    all_seven_features_present: bool
    missing_features: List[str]
    invalid_type_features: List[str]
    out_of_range_features: List[str]
    clipping_applied: Dict[str, bool]
    feature_provenance: Dict[str, str]
    feature_freshness: Dict[str, Dict[str, Any]]
    feature_classification: Dict[str, str]
    inference_eligibility: str
    eligibility_reasons: List[str]
    completeness_score: float
    complete_real_evidence_present: bool
    disclaimer: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid_structure": self.is_valid_structure,
            "all_seven_features_present": self.all_seven_features_present,
            "missing_features": self.missing_features,
            "invalid_type_features": self.invalid_type_features,
            "out_of_range_features": self.out_of_range_features,
            "clipping_applied": self.clipping_applied,
            "feature_provenance": self.feature_provenance,
            "feature_freshness": self.feature_freshness,
            "feature_classification": self.feature_classification,
            "inference_eligibility": self.inference_eligibility,
            "eligibility_reasons": self.eligibility_reasons,
            "completeness_score": self.completeness_score,
            "complete_real_evidence_present": self.complete_real_evidence_present,
            "disclaimer": self.disclaimer,
        }


def evaluate_risk_engine_contract(
    raw_features: Dict[str, Any],
    data_mode: str = "simulated",
    provenance: Optional[Dict[str, str]] = None,
    freshness: Optional[Dict[str, Dict[str, Any]]] = None,
) -> RiskEngineDataContractResult:
    """
    Evaluates input vector against Phase 6.25 Risk Engine Data Contract rules.
    """
    is_valid_struct = isinstance(raw_features, dict) and len(raw_features) > 0
    missing_feats: List[str] = []
    invalid_type_feats: List[str] = []
    out_of_range_feats: List[str] = []
    clipping_map: Dict[str, bool] = {}
    classification_map: Dict[str, str] = {}

    prov_map = provenance or {}
    fresh_map = freshness or {}

    if not is_valid_struct:
        missing_feats = list(FEATURE_ORDER)
        for f in FEATURE_ORDER:
            clipping_map[f] = False
            classification_map[f] = FeatureClassification.UNAVAILABLE.value
        return RiskEngineDataContractResult(
            is_valid_structure=False,
            all_seven_features_present=False,
            missing_features=missing_feats,
            invalid_type_features=[],
            out_of_range_features=[],
            clipping_applied=clipping_map,
            feature_provenance=prov_map,
            feature_freshness=fresh_map,
            feature_classification=classification_map,
            inference_eligibility=InferenceEligibilityStatus.INELIGIBLE_INVALID_INPUT.value,
            eligibility_reasons=["Invalid feature payload structure: must be a non-empty dictionary"],
            completeness_score=0.0,
            complete_real_evidence_present=False,
            disclaimer="Invalid input vector. Synthetic GBR model weights require valid 7-feature payload.",
        )

    # 1. Structural, Type, & Bound Validation across exactly 7 required features in order
    valid_count = 0
    for name in FEATURE_ORDER:
        val = raw_features.get(name)
        spec = FEATURE_SPECS[name]

        if val is None:
            missing_feats.append(name)
            clipping_map[name] = False
        else:
            try:
                val_flt = float(val)
                if math.isnan(val_flt) or math.isinf(val_flt):
                    invalid_type_feats.append(name)
                    clipping_map[name] = False
                else:
                    valid_count += 1
                    if val_flt < spec["min"] or val_flt > spec["max"]:
                        out_of_range_feats.append(name)
                        clipping_map[name] = True
                    else:
                        clipping_map[name] = False
            except (ValueError, TypeError):
                invalid_type_feats.append(name)
                clipping_map[name] = False

        # Classification assignment
        p_tag = prov_map.get(name, "")
        if data_mode == "simulated" or p_tag == "simulated":
            classification_map[name] = FeatureClassification.SIMULATED.value
        elif p_tag in ("UNAVAILABLE", "missing:no_fallback") or val is None:
            classification_map[name] = FeatureClassification.UNAVAILABLE.value
        elif name == "infrastructure_vulnerability" or p_tag == "PROVISIONAL":
            classification_map[name] = FeatureClassification.PROVISIONAL.value
        elif name == "population_exposure" or "SEMANTICALLY_INCOMPATIBLE" in p_tag:
            classification_map[name] = FeatureClassification.CONTEXTUAL_STATIC.value
        elif "2020" in p_tag or "2023" in p_tag or "ERA5" in p_tag or "BASELINE" in p_tag or name == "road_congestion" or p_tag == "DERIVED_FROM_REAL":
            classification_map[name] = FeatureClassification.HISTORICAL_BASELINE.value
        elif p_tag.startswith("live:") or p_tag.startswith("live_sensor:"):
            classification_map[name] = FeatureClassification.MEASURED.value
        else:
            classification_map[name] = FeatureClassification.REAL_DERIVED.value

    all_present = len(missing_feats) == 0
    completeness = round(valid_count / 7.0, 2)

    # 2. Eligibility & Reasons
    reasons: List[str] = []
    if len(invalid_type_feats) > 0:
        eligibility = InferenceEligibilityStatus.INELIGIBLE_INVALID_INPUT.value
        reasons.append(f"Non-numeric/NaN/Inf values detected in features: {invalid_type_feats}")
    elif data_mode == "simulated":
        eligibility = InferenceEligibilityStatus.ELIGIBLE_SIMULATED.value
        reasons.append("Simulated benchmark mode: baseline vector evaluated against synthetic GBR model")
    elif data_mode == "hybrid":
        eligibility = InferenceEligibilityStatus.ELIGIBLE_HYBRID.value
        reasons.append("Hybrid mode: partial live feeds merged with fallback defaults")
    elif data_mode == "real":
        eligibility = InferenceEligibilityStatus.ELIGIBLE_REAL.value
        reasons.append("Real-derived data mode: real historical/event inputs evaluated against synthetic-trained GBR model")
        reasons.append("Incomplete real evidence: infrastructure_vulnerability is provisional (0.72) and population_exposure uses schema default (12430.0)")
    else:
        eligibility = InferenceEligibilityStatus.ELIGIBLE_HYBRID.value
        reasons.append(f"Data mode '{data_mode}' evaluated under fallback policy")

    if len(out_of_range_feats) > 0:
        reasons.append(f"Out-of-range features clipped at ML model boundaries: {out_of_range_feats}")

    # 3. Complete Real Evidence Check
    # False for real mode because infrastructure_vulnerability is provisional (0.72) and population_exposure is semantically incompatible WorldPop grid sum.
    complete_real = (
        data_mode == "real"
        and all_present
        and len(invalid_type_feats) == 0
        and all(classification_map[f] in (FeatureClassification.MEASURED.value, FeatureClassification.REAL_DERIVED.value) for f in FEATURE_ORDER)
    )

    disclaimer = (
        "Synthetic-trained GBR model weights. Predictive accuracy and operational validity "
        "have NOT been established on real-world data."
    )

    return RiskEngineDataContractResult(
        is_valid_structure=True,
        all_seven_features_present=all_present,
        missing_features=missing_feats,
        invalid_type_features=invalid_type_feats,
        out_of_range_features=out_of_range_feats,
        clipping_applied=clipping_map,
        feature_provenance=prov_map,
        feature_freshness=fresh_map,
        feature_classification=classification_map,
        inference_eligibility=eligibility,
        eligibility_reasons=reasons,
        completeness_score=completeness,
        complete_real_evidence_present=complete_real,
        disclaimer=disclaimer,
    )
