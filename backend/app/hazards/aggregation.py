"""
AapdaNetra-X — Multi-Hazard Risk Aggregation Service

Phase 6.20.3: Domain-level multi-hazard aggregation service.
Obtains hazard definitions and adapters through the central HazardRegistry.
Calculates composite risk via operational max-severity aggregation without
fabricating fake risk scores, multi-hazard conformal bounds, or composite SHAP attributions.
"""
from typing import Dict, List, Optional, Any
from app.hazards.types import (
    HazardType,
    HazardCapabilityStatus,
    HazardDefinition,
    HazardEvaluationResult,
    HazardContributionSummary,
    ExcludedHazardSummary,
    MultiHazardRiskAggregate,
)
from app.hazards.registry import HazardRegistry, get_hazard_registry


class MultiHazardRiskAggregator:
    """
    Pure domain-level multi-hazard risk aggregation service.
    Aggregates risk across registered hazards based on capability status and operational validity.
    """

    def __init__(self, registry: Optional[HazardRegistry] = None) -> None:
        self._registry = registry or get_hazard_registry()

    def aggregate(
        self,
        telemetry_features: Optional[Dict[str, float]] = None,
        hazard_evaluations: Optional[Dict[Any, HazardEvaluationResult]] = None,
    ) -> MultiHazardRiskAggregate:
        """
        Aggregates multi-hazard risk across all registered hazard types.

        Policy:
        composite_risk = max(risk values from hazards that are operationally supported,
                             have a real numerical risk value, and are permitted to contribute)
        Current operational contributor: FLOOD ONLY.
        """
        # Validate any explicit hazard_evaluations passed
        validated_evaluations: Dict[HazardType, HazardEvaluationResult] = {}
        if hazard_evaluations:
            for key, eval_res in hazard_evaluations.items():
                if isinstance(key, str):
                    h_type = HazardType(key.lower())
                elif isinstance(key, HazardType):
                    h_type = key
                else:
                    raise ValueError(f"Unknown or unsupported hazard type: '{key}'")

                # Verify registry knows this hazard
                self._registry.get_definition(h_type)
                validated_evaluations[h_type] = eval_res

        contributing_hazards: List[HazardContributionSummary] = []
        excluded_hazards: List[ExcludedHazardSummary] = []
        hazard_breakdown: Dict[str, Any] = {}
        primary_uncertainty: Optional[Dict[str, Any]] = None
        explanation_hazard: Optional[HazardType] = None

        # Process all registered hazards in canonical order
        all_definitions = self._registry.get_all()
        for h_str, defn in all_definitions.items():
            h_type = defn.hazard_type
            adapter = self._registry.get_adapter(h_type)

            # Evaluate or retrieve pre-evaluated result
            if h_type in validated_evaluations:
                eval_res = validated_evaluations[h_type]
            else:
                eval_res = adapter.evaluate_risk(telemetry_features)

            hazard_breakdown[h_str] = eval_res.model_dump()

            # Capability check: only supported hazards with real numerical predictions can contribute
            if (
                defn.supported
                and defn.model_available
                and eval_res.supported
                and eval_res.model_available
                and eval_res.predicted_risk is not None
            ):
                risk_val = float(eval_res.predicted_risk)
                contributing_hazards.append(
                    HazardContributionSummary(
                        hazard_type=h_type,
                        capability_status=defn.capability_status,
                        contributed=True,
                        risk=risk_val,
                        reason="Operational supported flood risk model prediction.",
                        provenance=eval_res.provenance,
                    )
                )
                explanation_hazard = h_type
                # Preserve flood uncertainty metadata if present in details
                if "uncertainty" in eval_res.details:
                    primary_uncertainty = eval_res.details["uncertainty"]
                elif "interval_lower" in eval_res.details:
                    primary_uncertainty = {
                        "interval_lower": eval_res.details.get("interval_lower"),
                        "interval_upper": eval_res.details.get("interval_upper"),
                        "reliability_score": eval_res.details.get("reliability_score"),
                    }
            else:
                # Determine explicit exclusion reason
                if h_type == HazardType.EXTREME_RAINFALL:
                    reason = "Contextual hydro-meteorological telemetry only; no independent validated numerical risk model exists."
                elif defn.capability_status == HazardCapabilityStatus.DEMONSTRATION_ONLY:
                    reason = f"{defn.display_name} capability is demonstration only; numerical model unavailable."
                elif defn.capability_status == HazardCapabilityStatus.FUTURE_EXTENSION:
                    reason = f"{defn.display_name} is a future extension; numerical model unavailable."
                else:
                    reason = f"{defn.display_name} model unavailable or unsupported."

                excluded_hazards.append(
                    ExcludedHazardSummary(
                        hazard_type=h_type,
                        capability_status=defn.capability_status,
                        risk=None,  # MUST NEVER BE CONVERTED TO 0.0
                        reason=reason,
                    )
                )

        # Compute composite risk via max operational supported hazard risk
        if contributing_hazards:
            max_contrib = max(contributing_hazards, key=lambda c: c.risk if c.risk is not None else -1.0)
            composite_risk = max_contrib.risk
            primary_hazard_driver = max_contrib.hazard_type
        else:
            composite_risk = None
            primary_hazard_driver = None

        return MultiHazardRiskAggregate(
            composite_risk=composite_risk,
            primary_hazard_driver=primary_hazard_driver,
            contributing_hazards=contributing_hazards,
            excluded_hazards=excluded_hazards,
            hazard_breakdown=hazard_breakdown,
            aggregation_policy="MAX_SEVERITY_OPERATIONAL_HAZARD",
            provenance="Multi-hazard decision-support aggregation service",
            disclaimer=(
                "Multi-hazard composite risk reflects operational supported hazard risk models only. "
                "Unsupported or proxy hazard capabilities are explicitly excluded and not converted to zero risk."
            ),
            explanation_hazard=explanation_hazard,
            primary_hazard_uncertainty=primary_uncertainty,
            details={
                "operational_contributor_count": len(contributing_hazards),
                "excluded_hazard_count": len(excluded_hazards),
            },
        )
