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
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Artifact,
    DatasetSnapshot,
    EvidenceClaim,
    ExtractedRecord,
    ImportBatch,
    LabBatch,
    LabExecution,
    LabSample,
    Measurement,
    ResearchSession,
    SessionMessage,
)

_TRAINABLE_VALUE_TYPES = {"numeric", "interval", "ordinal", "categorical"}
_TRAINING_OK = {"allowed", "owned"}


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


def _record_hash(fields: dict[str, Any]) -> str:
    return hashlib.sha256(_canon(fields)).hexdigest()


def _measurement_fields(m: Measurement) -> dict[str, Any]:
    return {
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


def _semantics_measurement(m: Measurement) -> dict[str, Any]:
    """Missing/censored/failure semantics are retained, not dropped."""
    value = m.value or {}
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
    return semantics


class DatasetService:
    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    # -------------------------------------------------------- collect

    def _measurement_entries(self, task_id: uuid.UUID | None) -> list[dict[str, Any]]:
        ws = self.ctx.workspace_id
        stmt = (
            select(Measurement, LabExecution.task_id)
            .join(LabSample, LabSample.id == Measurement.sample_id)
            .join(LabBatch, LabBatch.id == LabSample.batch_id)
            .join(LabExecution, LabExecution.id == LabBatch.execution_id)
            .where(Measurement.workspace_id == ws)
        )
        rows = self.db.execute(stmt).all()
        entries: list[dict[str, Any]] = []
        for m, exec_task_id in rows:
            if task_id is not None and exec_task_id != task_id:
                continue
            excluded_reason: str | None = None
            if m.status in ("rejected", "superseded"):
                excluded_reason = f"status:{m.status}"
            elif not m.applicable:
                excluded_reason = "not_applicable"
            elif m.value_type not in _TRAINABLE_VALUE_TYPES:
                excluded_reason = f"value_type:{m.value_type}"
            entries.append(
                {
                    "recordId": str(m.id),
                    "recordKind": "measurement",
                    "sourceClass": "lab_measurement",
                    "hash": _record_hash(_measurement_fields(m)),
                    "rightsTraining": "owned",
                    "labelKind": "measured_value",
                    "metric": m.metric,
                    "semantics": _semantics_measurement(m),
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
            excluded_reason = None
            if c.status in ("rejected", "superseded"):
                excluded_reason = f"status:{c.status}"
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
            entries.append(
                {
                    "recordId": str(s.id),
                    "recordKind": "session",
                    "sourceClass": "research_session",
                    "hash": _record_hash(_session_fields(s, messages)),
                    "rightsTraining": "owned",
                    "labelKind": "reviewed_response",
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
        manifest = {
            "purpose": purpose,
            "taskId": str(task_id) if task_id else None,
            "entries": entries,
            "scientificStatus": "not_validated",
            "notes": "fixture/software evidence only; snapshot is not "
            "scientific validation of any label",
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
            return _record_hash(_measurement_fields(m)) if m else None
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
        return {
            "ok": True,
            "snapshotId": str(snap.id),
            "digest": snap.digest,
            "entryIds": [e["recordId"] for e in snap.manifest["entries"] if not e["excluded"]],
            "scientificStatus": "not_validated",
        }
