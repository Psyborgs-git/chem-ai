"""Property-model readiness over frozen dataset snapshots (CS-0604).

The service answers one question — "is there enough *real, in-scope*
evidence to train a property predictor?" — and answers it with a
capability report, never a predictor. It does not invent minimums:
the only structural requirements are labeled examples, at least the
caller-declared minimum, at least two distinct lineage groups (so a
held-out partition can exist), and an assignable ``final`` partition.

Coverage and exclusions come from the signed snapshot manifest and
the live source records — counts and reasons, never fabricated.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from chem_studio_policy.capabilities import CAP_MANAGE_MODELS
from sqlalchemy.orm import Session
from workers.optimization.property_models.readiness import assess_readiness

from studio.auth.context import ServiceContext
from studio.domain.learning.datasets import DatasetService
from studio.domain.learning.splits import SplitRecord
from studio.domain.provenance import (
    ORIGIN_UNKNOWN,
    REAL_EVIDENCE_ORIGINS,
    measurement_chain,
    measurement_origin,
)
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import LabBatch, LabSample, Measurement


class PropertyModelService:
    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    def readiness(
        self,
        snapshot_id: uuid.UUID,
        *,
        target: dict[str, str],
        min_labeled_examples: int = 1,
        seed: int = 0,
    ) -> dict[str, Any]:
        """AT-0604-3: insufficient real data → ``not_ready`` with the
        coverage/exclusion report. A frozen, drift-free snapshot whose
        in-scope examples are too few or too grouped reports the same
        — it never becomes a silent training run."""
        self.ctx.require(CAP_MANAGE_MODELS)
        ds = DatasetService(self.db, self.ctx)
        try:
            prepared = ds.prepare_run(snapshot_id)
        except DomainError as exc:
            if exc.code == ErrorCode.CONFLICT:
                snap = ds.get(snapshot_id)
                return self._report(
                    snap.id,
                    snap.digest,
                    target,
                    {},
                    {
                        "eligible": 0,
                        "ineligible": 0,
                        "labeled": 0,
                        "unlabeled": 0,
                        "distinctGroups": 0,
                        "partitionSizes": {},
                        "minLabeledDeclared": min_labeled_examples,
                    },
                    ["snapshot_not_frozen"],
                )
            raise
        snap = ds.get(snapshot_id)
        if not prepared["ok"]:
            if prepared["reason"] == "provenance_unresolved":
                return self._report(
                    snap.id,
                    snap.digest,
                    target,
                    {"provenance_unresolved": len(prepared.get("recordIds", []))},
                    {
                        "eligible": 0,
                        "ineligible": 0,
                        "labeled": 0,
                        "unlabeled": 0,
                        "distinctGroups": 0,
                        "partitionSizes": {},
                        "minLabeledDeclared": min_labeled_examples,
                    },
                    ["provenance_unresolved"],
                    extra={"provenance": prepared.get("violations", {})},
                )
            return self._report(
                snap.id,
                snap.digest,
                target,
                {
                    "source_drift": len(prepared.get("changed", []))
                    + len(prepared.get("missing", []))
                },
                {
                    "eligible": 0,
                    "ineligible": 0,
                    "labeled": 0,
                    "unlabeled": 0,
                    "distinctGroups": 0,
                    "partitionSizes": {},
                    "minLabeledDeclared": min_labeled_examples,
                },
                ["source_drift"],
                extra={
                    "changed": prepared.get("changed", []),
                    "missing": prepared.get("missing", []),
                },
            )
        records, exclusions = self._records(snap, target)
        report = assess_readiness(
            records,
            min_labeled_examples=min_labeled_examples,
            exclusion_reasons=exclusions,
            seed=seed,
        )
        report["snapshotId"] = str(snap.id)
        report["snapshotDigest"] = snap.digest
        report["scope"] = dict(target)
        report["snapshotImmutable"] = True
        return report

    # ---------------------------------------------------------------
    def _report(
        self,
        snapshot_id: uuid.UUID,
        digest: str,
        target: dict[str, str],
        exclusions: dict[str, int],
        coverage: dict[str, Any],
        blockers: list[str],
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        report: dict[str, Any] = {
            "capability": "not_ready",
            "scientificStatus": "not_validated",
            "coverage": coverage,
            "exclusions": exclusions,
            "blockers": blockers,
            "snapshotId": str(snapshot_id),
            "snapshotDigest": digest,
            "scope": dict(target),
            "snapshotImmutable": True,
        }
        if extra:
            report["drift"] = extra
        return report

    def _records(
        self, snap: Any, target: dict[str, str]
    ) -> tuple[list[SplitRecord], dict[str, int]]:
        """Map manifest entries to SplitRecords with real lineage keys:
        the sample, its batch and its execution — the connected
        components §17.2 requires so repeats never cross a split."""
        exclusions: dict[str, int] = {}
        records: list[SplitRecord] = []
        for entry in snap.manifest["entries"]:
            if entry["excluded"]:
                key = entry.get("exclusionReason") or "excluded"
                exclusions[key] = exclusions.get(key, 0) + 1
                continue
            if entry["recordKind"] != "measurement":
                # Claims stay a distinct class (AT-0601-1); they are
                # not numeric training labels for an endpoint.
                key = f"source_class:{entry['recordKind']}"
                exclusions[key] = exclusions.get(key, 0) + 1
                continue
            m = self.db.get(Measurement, uuid.UUID(str(entry["recordId"])))
            if m is None:
                exclusions["source_missing"] = exclusions.get("source_missing", 0) + 1
                continue
            # PAR-05: provenance is its own exclusion plane — synthetic
            # fixtures, predictions and unestablishable origins never
            # silently count as label evidence; the exclusion name makes
            # the missing scientific input explicit.
            origin = entry.get("evidenceOrigin")
            if origin is None:
                sample, batch, execution, plan = measurement_chain(
                    self.db, self.ctx.workspace_id, m
                )
                origin = measurement_origin(
                    m, sample=sample, batch=batch, execution=execution, plan=plan
                )["origin"]
            if origin == ORIGIN_UNKNOWN:
                exclusions["evidence_origin:unknown"] = (
                    exclusions.get("evidence_origin:unknown", 0) + 1
                )
                continue
            if origin not in REAL_EVIDENCE_ORIGINS:
                key = f"evidence_origin:{origin}"
                exclusions[key] = exclusions.get(key, 0) + 1
                continue
            if (
                m.metric != target.get("name")
                or m.method != target.get("method")
                or (m.value or {}).get("unit") != target.get("unit")
            ):
                exclusions["target_mismatch"] = exclusions.get("target_mismatch", 0) + 1
                continue
            try:
                label = Decimal(str((m.value or {}).get("value")))
            except InvalidOperation:
                label = Decimal("NaN")
            if not label.is_finite():
                exclusions["non_finite_label"] = exclusions.get("non_finite_label", 0) + 1
                continue
            sample = self.db.get(LabSample, m.sample_id)
            batch = self.db.get(LabBatch, sample.batch_id) if sample else None
            group_keys = {
                f"sample:{m.sample_id}",
                f"batch:{sample.batch_id}" if sample else "",
                f"execution:{batch.execution_id}" if batch else "",
            } - {""}
            records.append(
                SplitRecord(
                    record_id=str(m.id),
                    group_keys=frozenset(group_keys),
                    label=float(label),
                    eligible=True,
                )
            )
        return records, exclusions
