"""Dataset snapshots and training eligibility (CS-0601, §17.2).

A snapshot is a point-in-time manifest of records eligible for one
declared purpose. Each entry carries the record id, a content hash,
its source class, the rights decision for training, the permitted
label kind, and missing/censored/failure semantics — nothing is
silently dropped; unsuitable records are marked ``excluded`` with a
reason instead.

- Source classes stay distinct (AT-0601-1): a lab measurement can
  never be relabelled as a supplier claim or vice versa.
- Freeze is a governance action (``manage_models``). Any included
  record whose training rights are not ``allowed``/``owned`` blocks
  the freeze with ``DATA_RIGHTS_UNKNOWN`` (AT-0601-2).
- After freeze, ``drift_status``/``prepare_run`` re-hash the source
  records; a changed source is reported as drift while the signed
  manifest stays immutable (AT-0601-3).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from chem_studio_policy.capabilities import (
    CAP_MANAGE_MODELS,
    CAP_READ_PROJECT,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext
from studio.domain.provenance import (
    ORIGIN_UNKNOWN,
    claim_origin,
    claim_source_resolvable,
    measurement_origin,
    session_origin,
    summarize,
)
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Artifact,
    DatasetSnapshot,
    EvidenceClaim,
    ExperimentPlan,
    ExtractedRecord,
    ImportBatch,
    LabBatch,
    LabExecution,
    LabSample,
    Measurement,
    MeasurementAmendment,
    ResearchSession,
    SessionMessage,
)

_TRAINABLE_VALUE_TYPES = {"numeric", "interval", "ordinal", "categorical"}
_TRAINING_OK = {"allowed", "owned"}


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


def _record_hash(fields: dict[str, Any]) -> str:
    return hashlib.sha256(_canon(fields)).hexdigest()


def _measurement_fields(
    m: Measurement, amendment: MeasurementAmendment | None = None
) -> dict[str, Any]:
    """Fields hashed into a snapshot entry. A superseded row with a
    resolvable amendment hashes the *effective* (corrected) value and
    names the successor — the pre-amendment value is never re-read
    (PAR-04 §4). Non-amended rows keep the exact pre-PAR-04 field set
    so older frozen manifests still hash identically."""
    fields: dict[str, Any] = {
        "kind": "measurement",
        "metric": m.metric,
        "method": m.method,
        "value_type": m.value_type,
        "value": m.value,
        "conditions": m.conditions,
        "applicable": m.applicable,
        "status": m.status,
        "superseded_by": str(m.superseded_by) if m.superseded_by else None,
    }
    if amendment is not None:
        fields["value"] = amendment.value
        fields["conditions"] = amendment.conditions or m.conditions
        fields["effective_amendment"] = str(amendment.id)
    return fields


def _claim_fields(c: EvidenceClaim, artifact: Artifact | None) -> dict[str, Any]:
    return {
        "kind": "claim",
        "claim_kind": c.kind,
        "statement": c.statement,
        "subject": c.subject,
        "status": c.status,
        "conditions": c.conditions,
        "artifact_id": str(artifact.id) if artifact else None,
        "artifact_checksum": artifact.checksum_sha256 if artifact else None,
    }


def _session_fields(s: ResearchSession, messages: Sequence[SessionMessage]) -> dict[str, Any]:
    return {
        "kind": "session",
        "status": s.status,
        "task_id": str(s.task_id),
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "kind": m.kind,
                "content_hash": hashlib.sha256(m.content.encode()).hexdigest(),
                "refs": m.refs,
                "created_by": str(m.created_by) if m.created_by else None,
            }
            for m in messages
        ],
    }


def _semantics_measurement(
    m: Measurement, amendment: MeasurementAmendment | None = None
) -> dict[str, Any]:
    """Missing/censored/failure semantics are retained, not dropped —
    read from the effective value once a correction supersedes the
    original (PAR-04 §4-5)."""
    value = (amendment.value if amendment is not None else m.value) or {}
    semantics: dict[str, Any] = {
        "valueType": m.value_type,
        "status": m.status,
        "applicable": m.applicable,
    }
    if m.value_type == "missing":
        semantics["missingReason"] = value.get("reason", "unknown")
    if m.value_type in ("below_detection", "above_quantification"):
        semantics["censored"] = True
        semantics["censorBound"] = value.get("value")
    if amendment is not None:
        semantics["effectiveFromAmendment"] = str(amendment.id)
        semantics["correctionReason"] = amendment.reason
        semantics["correctionSource"] = amendment.source
        semantics["correctedBy"] = str(amendment.created_by) if amendment.created_by else None
    return semantics


class DatasetService:
    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    # -------------------------------------------------------- collect

    def _measurement_entries(self, task_id: uuid.UUID | None) -> list[dict[str, Any]]:
        ws = self.ctx.workspace_id
        stmt = (
            select(Measurement, LabSample, LabBatch, LabExecution, ExperimentPlan)
            .join(LabSample, LabSample.id == Measurement.sample_id)
            .join(LabBatch, LabBatch.id == LabSample.batch_id)
            .join(LabExecution, LabExecution.id == LabBatch.execution_id)
            .outerjoin(ExperimentPlan, ExperimentPlan.id == LabExecution.plan_id)
            .where(Measurement.workspace_id == ws)
        )
        rows = self.db.execute(stmt).all()
        # PAR-04 §4: a superseded row's effective version is the
        # amendment ``superseded_by`` names — the corrected reading
        # enters exactly once under the measurement's own identity; a
        # supersession with no resolvable amendment stays excluded.
        supersession_ids = [m.superseded_by for m, *_ in rows if m.superseded_by]
        amendments: dict[uuid.UUID, MeasurementAmendment] = {}
        if supersession_ids:
            for amd_row in self.db.execute(
                select(MeasurementAmendment).where(MeasurementAmendment.id.in_(supersession_ids))
            ).scalars():
                amendments[amd_row.id] = amd_row
        entries: list[dict[str, Any]] = []
        for m, sample, batch, execution, plan in rows:
            if task_id is not None and execution.task_id != task_id:
                continue
            amd = amendments.get(m.superseded_by) if m.superseded_by else None
            # PAR-05: every record's origin is labeled — a record whose
            # origin cannot be established is excluded, never silent
            prov = measurement_origin(m, sample=sample, batch=batch, execution=execution, plan=plan)
            excluded_reason: str | None = None
            if m.status == "rejected":
                excluded_reason = "status:rejected"
            elif m.status == "superseded" and amd is None:
                excluded_reason = "status:superseded"
            elif not m.applicable:
                excluded_reason = "not_applicable"
            elif m.value_type not in _TRAINABLE_VALUE_TYPES:
                excluded_reason = f"value_type:{m.value_type}"
            if excluded_reason is None and prov["origin"] == ORIGIN_UNKNOWN:
                excluded_reason = "provenance:unknown"
            entries.append(
                {
                    "recordId": str(m.id),
                    "recordKind": "measurement",
                    "sourceClass": "lab_measurement",
                    "hash": _record_hash(_measurement_fields(m, amd)),
                    "rightsTraining": "owned",
                    "labelKind": "measured_value",
                    "metric": m.metric,
                    "evidenceOrigin": prov["origin"],
                    "originVia": prov["via"],
                    "reviewState": m.status,
                    "semantics": _semantics_measurement(m, amd),
                    "excluded": excluded_reason is not None,
                    "exclusionReason": excluded_reason,
                }
            )
        return entries

    def _claim_entries(self) -> list[dict[str, Any]]:
        ws = self.ctx.workspace_id
        claims = (
            self.db.execute(select(EvidenceClaim).where(EvidenceClaim.workspace_id == ws))
            .scalars()
            .all()
        )
        # Resolve source artifact → training rights once per record.
        art_by_claim: dict[uuid.UUID, Artifact | None] = {}
        for c in claims:
            artifact: Artifact | None = None
            if c.source_record_id:
                # record → import batch → source artifact (rights owner)
                rec = self.db.get(ExtractedRecord, c.source_record_id)
                if rec is not None:
                    batch = self.db.get(ImportBatch, rec.batch_id)
                    if batch is not None:
                        artifact = self.db.get(Artifact, batch.artifact_id)
            art_by_claim[c.id] = artifact

        entries: list[dict[str, Any]] = []
        for c in claims:
            artifact = art_by_claim[c.id]
            rights = (artifact.rights or {}) if artifact else {}
            training = rights.get("training", "unknown")
            prov = claim_origin(
                c,
                source_resolvable=(artifact is not None or claim_source_resolvable(self.db, c)),
            )
            excluded_reason = None
            if c.status in ("rejected", "superseded"):
                excluded_reason = f"status:{c.status}"
            if excluded_reason is None and prov["origin"] == ORIGIN_UNKNOWN:
                excluded_reason = "provenance:unknown"
            entries.append(
                {
                    "recordId": str(c.id),
                    "recordKind": "claim",
                    # AT-0601-1: supplier/document claims stay a distinct
                    # class from lab measurements — never conflated.
                    "sourceClass": c.kind,
                    "hash": _record_hash(_claim_fields(c, artifact)),
                    "rightsTraining": training,
                    "labelKind": "claimed_value",
                    "evidenceOrigin": prov["origin"],
                    "originVia": prov["via"],
                    "reviewState": c.status,
                    "semantics": {"status": c.status},
                    "excluded": excluded_reason is not None,
                    "exclusionReason": excluded_reason,
                }
            )
        return entries

    def _session_entries(self, task_id: uuid.UUID | None) -> list[dict[str, Any]]:
        """Research sessions as SFT source records (CS-0801, §17.2).

        Sessions are locally generated research records — training
        rights are ``owned``; the *example* layer (§17.3) still drops
        hidden reasoning traces and unreviewed turns. Only collected
        for ``assistant_sft``/``preference_pairs`` snapshots."""
        ws = self.ctx.workspace_id
        stmt = select(ResearchSession).where(ResearchSession.workspace_id == ws)
        if task_id is not None:
            stmt = stmt.where(ResearchSession.task_id == task_id)
        entries: list[dict[str, Any]] = []
        for s in self.db.execute(stmt).scalars():
            messages = (
                self.db.execute(
                    select(SessionMessage)
                    .where(SessionMessage.session_id == s.id)
                    .order_by(SessionMessage.created_at, SessionMessage.id)
                )
                .scalars()
                .all()
            )
            prov = session_origin(s)
            entries.append(
                {
                    "recordId": str(s.id),
                    "recordKind": "session",
                    "sourceClass": "research_session",
                    "hash": _record_hash(_session_fields(s, messages)),
                    "rightsTraining": "owned",
                    "labelKind": "reviewed_response",
                    "evidenceOrigin": prov["origin"],
                    "originVia": prov["via"],
                    "semantics": {
                        "status": s.status,
                        "messageCount": len(messages),
                    },
                    "excluded": s.status not in ("active", "ended"),
                    "exclusionReason": (
                        None if s.status in ("active", "ended") else f"status:{s.status}"
                    ),
                }
            )
        return entries

    # -------------------------------------------------------- commands

    def build(
        self,
        purpose: str,
        name: str,
        task_id: uuid.UUID | None = None,
    ) -> DatasetSnapshot:
        self.ctx.require(CAP_MANAGE_MODELS)
        entries = self._measurement_entries(task_id) + self._claim_entries()
        if purpose in ("assistant_sft", "preference_pairs"):
            entries += self._session_entries(task_id)
        entries.sort(key=lambda e: (e["recordKind"], str(e["recordId"])))
        # PAR-05: provenance summary over the included corpus — the
        # origin labels make composition visible; scientificStatus
        # never upgrades on provenance alone
        included_origins = [e["evidenceOrigin"] for e in entries if not e["excluded"]]
        provenance = summarize(included_origins)
        if provenance["composition"] in ("synthetic_only", "none"):
            notes = (
                "fixture/software evidence only; snapshot is not scientific validation of any label"
            )
        else:
            notes = (
                f"corpus provenance is {provenance['composition'].replace('_', ' ')} "
                "(per-record evidenceOrigin labels); provenance does not "
                "imply scientific validation — method validation and "
                "independent validation are still required"
            )
        manifest = {
            "purpose": purpose,
            "taskId": str(task_id) if task_id else None,
            "entries": entries,
            # same shape as the packet block so every consumer reads
            # one wire format: provenance.evidenceOrigin.{composition,
            # counts, classesPresent}
            "provenance": {"evidenceOrigin": provenance},
            "scientificStatus": "not_validated",
            "notes": notes,
        }
        digest = hashlib.sha256(_canon(manifest)).hexdigest()
        snap = DatasetSnapshot(
            workspace_id=self.ctx.workspace_id,
            purpose=purpose,
            name=name,
            task_id=task_id,
            manifest=manifest,
            digest=digest,
            state="draft",
            created_by=self.ctx.principal_id,
        )
        self.db.add(snap)
        self.db.flush()
        return snap

    def freeze(self, snapshot_id: uuid.UUID) -> DatasetSnapshot:
        self.ctx.require(CAP_MANAGE_MODELS)
        snap = self._get(snapshot_id)
        if snap.state == "frozen":
            raise DomainError(ErrorCode.CONFLICT, "snapshot already frozen")
        blocked = [
            e["recordId"]
            for e in snap.manifest["entries"]
            if not e["excluded"] and e["rightsTraining"] not in _TRAINING_OK
        ]
        if blocked:
            raise DomainError(
                ErrorCode.DATA_RIGHTS_UNKNOWN,
                "training rights unresolved for included records",
                safe_details={"recordIds": blocked},
            )
        # PAR-05: an included record without established provenance
        # cannot be frozen into a corpus — manifests built before
        # provenance existed (no evidenceOrigin field) fail the same
        # plane and must be rebuilt so every record is labeled.
        unprovenanced = [
            e["recordId"]
            for e in snap.manifest["entries"]
            if not e["excluded"] and e.get("evidenceOrigin", ORIGIN_UNKNOWN) == ORIGIN_UNKNOWN
        ]
        if unprovenanced:
            raise DomainError(
                ErrorCode.PROVENANCE_UNKNOWN,
                "evidence origin unresolved for included records — rebuild "
                "the snapshot so provenance is derived and labeled",
                safe_details={"recordIds": unprovenanced},
            )
        snap.state = "frozen"
        snap.frozen_by = self.ctx.principal_id
        snap.frozen_at = datetime.now(UTC)
        self.db.flush()
        return snap

    # -------------------------------------------------------- queries

    def _get(self, snapshot_id: uuid.UUID) -> DatasetSnapshot:
        snap = self.db.execute(
            select(DatasetSnapshot).where(
                DatasetSnapshot.id == snapshot_id,
                DatasetSnapshot.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if snap is None:
            raise DomainError(ErrorCode.NOT_FOUND, "dataset snapshot not found")
        return snap

    def list(self, task_id: uuid.UUID | None = None) -> list[DatasetSnapshot]:
        self.ctx.require(CAP_READ_PROJECT)
        stmt = select(DatasetSnapshot).where(DatasetSnapshot.workspace_id == self.ctx.workspace_id)
        if task_id is not None:
            stmt = stmt.where(DatasetSnapshot.task_id == task_id)
        return list(self.db.execute(stmt.order_by(DatasetSnapshot.created_at)).scalars())

    def get(self, snapshot_id: uuid.UUID) -> DatasetSnapshot:
        self.ctx.require(CAP_READ_PROJECT)
        return self._get(snapshot_id)

    # -------------------------------------------------------- drift

    def _current_hash(self, entry: dict[str, Any]) -> str | None:
        """Re-hash the live source record; None if the record is gone."""
        rid = uuid.UUID(str(entry["recordId"]))
        if entry["recordKind"] == "measurement":
            m = self.db.get(Measurement, rid)
            if m is None:
                return None
            amd = self.db.get(MeasurementAmendment, m.superseded_by) if m.superseded_by else None
            return _record_hash(_measurement_fields(m, amd))
        if entry["recordKind"] == "session":
            s = self.db.get(ResearchSession, rid)
            if s is None:
                return None
            messages = (
                self.db.execute(
                    select(SessionMessage)
                    .where(SessionMessage.session_id == s.id)
                    .order_by(SessionMessage.created_at, SessionMessage.id)
                )
                .scalars()
                .all()
            )
            return _record_hash(_session_fields(s, messages))
        c = self.db.get(EvidenceClaim, rid)
        if c is None:
            return None
        artifact: Artifact | None = None
        if c.source_record_id:
            rec = self.db.get(ExtractedRecord, c.source_record_id)
            if rec is not None:
                batch = self.db.get(ImportBatch, rec.batch_id)
                if batch is not None:
                    artifact = self.db.get(Artifact, batch.artifact_id)
        return _record_hash(_claim_fields(c, artifact))

    def drift_status(self, snapshot_id: uuid.UUID) -> dict[str, Any]:
        self.ctx.require(CAP_READ_PROJECT)
        snap = self._get(snapshot_id)
        changed: list[str] = []
        missing: list[str] = []
        for e in snap.manifest["entries"]:
            current = self._current_hash(e)
            if current is None:
                missing.append(str(e["recordId"]))
            elif current != e["hash"]:
                changed.append(str(e["recordId"]))
        return {
            "snapshotId": str(snap.id),
            "digest": snap.digest,
            "drift": bool(changed or missing),
            "changed": changed,
            "missing": missing,
            "snapshotImmutable": True,
        }

    def provenance_violations(self, snapshot_id: uuid.UUID) -> dict[str, dict[str, Any]]:
        """Re-derive every *included* record's evidence origin against
        live source rows (PAR-05 — the same plane as AT-0601-2's
        live-rights re-check). A record is a violation when its current
        origin is ``unknown`` or it no longer matches what the frozen
        manifest recorded. Entries without a recorded origin (manifests
        built before provenance existed) are checked against the live
        derivation only — ``unknown`` still fails."""
        snap = self._get(snapshot_id)
        violations: dict[str, dict[str, Any]] = {}
        for entry in snap.manifest.get("entries", []):
            if entry.get("excluded"):
                continue
            rid_str = str(entry["recordId"])
            try:
                rid = uuid.UUID(rid_str)
            except ValueError:
                violations[rid_str] = {
                    "recorded": entry.get("evidenceOrigin"),
                    "current": "missing",
                }
                continue
            kind = entry.get("recordKind")
            current: str | None = None
            if kind == "measurement":
                m = self.db.get(Measurement, rid)
                if m is None:
                    current = "missing"
                else:
                    sample = self.db.get(LabSample, m.sample_id)
                    batch = self.db.get(LabBatch, sample.batch_id) if sample else None
                    execution = self.db.get(LabExecution, batch.execution_id) if batch else None
                    plan = (
                        self.db.get(ExperimentPlan, execution.plan_id)
                        if execution is not None and execution.plan_id
                        else None
                    )
                    current = measurement_origin(
                        m, sample=sample, batch=batch, execution=execution, plan=plan
                    )["origin"]
            elif kind == "claim":
                c = self.db.get(EvidenceClaim, rid)
                if c is None:
                    current = "missing"
                else:
                    current = claim_origin(
                        c, source_resolvable=claim_source_resolvable(self.db, c)
                    )["origin"]
            elif kind == "session":
                s = self.db.get(ResearchSession, rid)
                current = "missing" if s is None else session_origin(s)["origin"]
            else:
                current = ORIGIN_UNKNOWN
            recorded = entry.get("evidenceOrigin")
            # ``recorded`` missing means the manifest never established
            # provenance for the record (pre-PAR-05 manifest) — the
            # label is unverifiable, so it fails the plane alongside a
            # genuinely unknown or drifted origin.
            if current != recorded or current in ("missing", ORIGIN_UNKNOWN):
                violations[rid_str] = {"recorded": recorded, "current": current}
        return violations

    def prepare_run(self, snapshot_id: uuid.UUID) -> dict[str, Any]:
        """AT-0601-3: a run may only prepare against a frozen, un-drifted
        snapshot. Drift is reported; the signed manifest is never
        rewritten to match."""
        self.ctx.require(CAP_MANAGE_MODELS)
        snap = self._get(snapshot_id)
        if snap.state != "frozen":
            raise DomainError(ErrorCode.CONFLICT, "snapshot is not frozen")
        drift = self.drift_status(snapshot_id)
        if drift["drift"]:
            return {
                "ok": False,
                "reason": "source_drift",
                "snapshotId": str(snap.id),
                "digest": snap.digest,
                "changed": drift["changed"],
                "missing": drift["missing"],
            }
        violations = self.provenance_violations(snapshot_id)
        if violations:
            return {
                "ok": False,
                "reason": "provenance_unresolved",
                "snapshotId": str(snap.id),
                "digest": snap.digest,
                "recordIds": sorted(violations),
                "violations": violations,
            }
        return {
            "ok": True,
            "snapshotId": str(snap.id),
            "digest": snap.digest,
            "entryIds": [e["recordId"] for e in snap.manifest["entries"] if not e["excluded"]],
            "scientificStatus": "not_validated",
        }
