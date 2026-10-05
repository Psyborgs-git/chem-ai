"""Safe replay rather than BayBE's pickle-backed dataframe serialization."""

from __future__ import annotations

import importlib.metadata
import itertools
from typing import Any

from .contracts import ENGINE_VERSION, CampaignSpec, EngineFailure, Recommendation
from .validation import point, same_point, validate_batch


class BayBEAdapter:
    def recommend(
        self,
        spec: CampaignSpec,
        *,
        batch_size: int,
        request_index: int,
        observations: list[dict[str, str]],
        reserved: list[dict[str, str]],
        pending: list[dict[str, str]],
    ) -> Recommendation:
        requested_batch_size = batch_size
        if isinstance(batch_size, bool) or not 1 <= batch_size <= 16:
            raise EngineFailure("VALIDATION", "batch size must be 1..16")
        if not 0 <= request_index < 2**32:
            raise EngineFailure("VALIDATION", "request index exceeds replay envelope")
        try:
            installed = importlib.metadata.version("baybe")
        except importlib.metadata.PackageNotFoundError as e:
            raise EngineFailure("ENGINE_UNAVAILABLE", "BayBE 0.15.0 is not installed") from e
        if installed != ENGINE_VERSION:
            raise EngineFailure("ENGINE_UNAVAILABLE", "BayBE version differs from tested 0.15.0")
        # No optional science package is imported until an explicit worker request.
        import pandas as pd
        from baybe.acquisition import qLogNoisyExpectedImprovement
        from baybe.campaign import Campaign
        from baybe.constraints import ContinuousLinearConstraint
        from baybe.exceptions import InfeasibilityError, NotEnoughPointsLeftError
        from baybe.objectives import SingleTargetObjective
        from baybe.parameters import (
            CategoricalParameter,
            NumericalContinuousParameter,
            NumericalDiscreteParameter,
        )
        from baybe.recommenders import (
            BotorchRecommender,
            RandomRecommender,
            TwoPhaseMetaRecommender,
        )
        from baybe.searchspace import SearchSpace
        from baybe.targets import NumericalTarget
        from baybe.utils.random import temporary_seed

        names = [p.name for p in spec.parameters]
        existing = [point(spec, p) for p in reserved]
        pending_points = [point(spec, p) for p in pending]

        def numeric_frame(rows: list[dict[str, str]]) -> Any:
            return pd.DataFrame([
                {p.name: r[p.name] if p.kind == "categorical" else float(r[p.name])
                 for p in spec.parameters} for r in rows
            ])

        measured = []
        for row in observations:
            measured_point = point(spec, {n: row[n] for n in names})
            measured.append({
                **{
                    p.name: (
                        measured_point[p.name]
                        if p.kind == "categorical"
                        else float(measured_point[p.name])
                    )
                    for p in spec.parameters
                },
                spec.target.name: float(row[spec.target.name]),
            })
        params: list[Any] = []
        for p in spec.parameters:
            if p.kind == "continuous":
                assert p.bounds is not None  # noqa: S101
                params.append(
                    NumericalContinuousParameter(p.name, bounds=tuple(map(float, p.bounds)))
                )
            elif p.kind == "discrete":
                params.append(
                    NumericalDiscreteParameter(
                        p.name, values=list(map(float, p.values or ())), tolerance=0
                    )
                )
            else:
                params.append(
                    CategoricalParameter(p.name, values=list(p.categories or ()), encoding="OHE")
                )
        continuous = spec.parameters[0].kind == "continuous"
        if continuous:
            constraints: list[Any] = [
                ContinuousLinearConstraint(
                    list(c.parameters), c.operator, list(map(float, c.coefficients)), float(c.rhs)
                )
                for c in spec.constraints
            ]
            if spec.mixture:
                constraints.append(
                    ContinuousLinearConstraint(
                        list(spec.mixture.parameters),
                        "=",
                        [1.0] * len(spec.mixture.parameters),
                        float(spec.mixture.total),
                    )
                )
            space = SearchSpace.from_product(params, constraints=constraints)
        else:
            # Exact decimal enumeration supports discrete linear/mixture constraints.
            # No constraint is delegated to float tolerances or silently discarded.
            feasible: list[dict[str, Any]] = []
            available = 0
            for values in itertools.product(
                *(p.values or p.categories or () for p in spec.parameters)
            ):
                try:
                    checked = point(spec, dict(zip(names, values, strict=True)))
                except ValueError:
                    continue
                if not any(same_point(spec, checked, old) for old in existing):
                    available += 1
                feasible.append(
                        {
                            p.name: checked[p.name]
                            if p.kind == "categorical"
                            else float(checked[p.name])
                            for p in spec.parameters
                        }
                    )
            if not available:
                return Recommendation(
                    status="exhausted" if feasible else "no_feasible_suggestions",
                    suggestions=[],
                    rejected={},
                    seed=spec.seed,
                    recommender="none",
                )
            batch_size = min(batch_size, available)
            space = SearchSpace.from_dataframe(pd.DataFrame(feasible), parameters=params)
        target = spec.target
        if target.mode == "match":
            assert target.match_bounds is not None  # noqa: S101
            mapped_target = NumericalTarget.match_triangular(
                target.name, cutoffs=tuple(map(float, target.match_bounds))
            )
        else:
            mapped_target = NumericalTarget(target.name, minimize=target.mode == "minimize")
        random = RandomRecommender()
        acquisition = None
        chosen = "RandomRecommender"
        recommender: Any = random
        if spec.recommender == "two_phase":
            acquisition = (
                "qLogNoisyExpectedImprovement" if len(measured) >= spec.switch_after else None
            )
            if acquisition:
                chosen = "BotorchRecommender"
            recommender = TwoPhaseMetaRecommender(
                initial_recommender=random,
                recommender=BotorchRecommender(acquisition_function=qLogNoisyExpectedImprovement()),
                switch_after=spec.switch_after,
            )
        campaign = Campaign(space, SingleTargetObjective(mapped_target), recommender=recommender)
        if measured:
            campaign.add_measurements(
                pd.DataFrame(measured), numerical_measurements_must_be_within_tolerance=False
            )
        if not continuous and existing:
            campaign.toggle_discrete_candidates(numeric_frame(existing), exclude=True)
        try:
            with temporary_seed((spec.seed + request_index) % 2**32):
                frame = campaign.recommend(
                    batch_size,
                    pending_experiments=numeric_frame(pending_points) if pending_points else None,
                )
        except (NotEnoughPointsLeftError, InfeasibilityError):
            return Recommendation(
                status="no_feasible_suggestions",
                suggestions=[],
                rejected={},
                seed=spec.seed,
                recommender=chosen,
                acquisition=acquisition,
            )
        # BayBE output is still untrusted, even for the explicitly mapped searchspace.
        accepted, rejected = validate_batch(spec, frame.to_dict(orient="records"), existing)
        return Recommendation(
            status="suggested"
            if len(accepted) == requested_batch_size
            else "partial"
            if accepted
            else "no_feasible_suggestions",
            suggestions=accepted,
            rejected=rejected,
            seed=spec.seed,
            recommender=chosen,
            acquisition=acquisition,
        )
