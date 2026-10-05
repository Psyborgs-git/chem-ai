"""Analytical-data ingest + scoped comparison (CS-0703, §16.5).

Flow:

    ingest()   committed raw-export artifact -> content-sniffed format ->
               pinned parser -> declared units/context checked -> declared
               preprocessing -> processed artifact (vault, derived) ->
               AnalyticalSeries row with the full lineage
    compare()  two processed series (same task, same method, same x
               unit) -> declared preprocessing -> resample alignment ->
               scoped similarity -> result artifact + AnalyticalComparison

Unsupported formats are not failures and not guesses: ingest stores the
raw export and records ``interpretation_state='unsupported'`` with no
processed artifact (AT-0703-3). Similarity values are never composition
evidence — the scope and the interpretation limits are persisted with
every result.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from chem_studio_policy.capabilities import (
    CAP_EDIT_TASK,
    CAP_MANAGE_SOURCES,
    CAP_READ_PROJECT,
)
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine_adapter_analytics import (
    ADAPTER_VERSION,
    AnalyticsAdapter,
    AnalyticsFailure,
    CompareSpec,
    IngestSpec,
    SpectrumTrace,
)
from engine_adapter_analytics.contracts import UNDECLARED_UNIT
from studio.auth.context import ServiceContext
from studio.config.settings import Settings
from studio.domain.evidence.vault import Vault
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import (
    AnalyticalComparison,
    AnalyticalSeries,
    Artifact,
    LabSample,
    ResearchTask,
)

_FAILURE_CODES = {
    "ANALYTICS_METHOD_MISMATCH": ErrorCode.METHOD_INCOMPATIBLE,
    "ANALYTICS_UNIT_MISMATCH": ErrorCode.INVALID_UNIT,
    "ANALYTICS_METADATA_CONFLICT": ErrorCode.VALIDATION,
    "ANALYTICS_UNSUPPORTED_FORMAT": ErrorCode.ENGINE_UNSUPPORTED_INPUT,
    "ANALYTICS_UNSUPPORTED_ENCODING": ErrorCode.ENGINE_UNSUPPORTED_INPUT,
    "ANALYTICS_UNSUPPORTED_INPUT": ErrorCode.ENGINE_UNSUPPORTED_INPUT,
    "ANALYTICS_NO_OVERLAP": ErrorCode.VALIDATION,
    "ANALYTICS_DEGENERATE_TRANSFORM": ErrorCode.VALIDATION,
    "ANALYTICS_MALFORMED_INPUT": ErrorCode.VALIDATION,
}


class AnalyticsService:
    """Application service for analytical processing."""

    def __init__(
        self,
        db: Session,
        ctx: ServiceContext,
        settings: Settings,
        vault: Vault | None = None,
        adapter: AnalyticsAdapter | None = None,
    ) -> None:
        self.db, self.ctx, self.settings = db, ctx, settings
        self.vault = vault or Vault(settings.vault_root)
        self.adapter = adapter or AnalyticsAdapter()

    # ------------------------------------------------------------- reads

    def list_series(self, task_id: uuid.UUID) -> list[AnalyticalSeries]:
        self.ctx.require(CAP_READ_PROJECT, task_id)
        return list(
            self.db.scalars(
                select(AnalyticalSeries)
                .where(
                    AnalyticalSeries.workspace_id == self.ctx.workspace_id,
                    AnalyticalSeries.task_id == task_id,
                )
                .order_by(AnalyticalSeries.created_at.desc())
                .limit(50)
            )
        )

    def list_comparisons(self, task_id: uuid.UUID) -> list[AnalyticalComparison]:
        self.ctx.require(CAP_READ_PROJECT, task_id)
        return list(
            self.db.scalars(
                select(AnalyticalComparison)
                .where(
                    AnalyticalComparison.workspace_id == self.ctx.workspace_id,
                    AnalyticalComparison.task_id == task_id,
                )
                .order_by(AnalyticalComparison.created_at.desc())
                .limit(50)
            )
        )

    # ------------------------------------------------------------- ingest

    def ingest(
        self,
        task_id: uuid.UUID,
        raw_artifact_id: uuid.UUID,
        raw_spec: dict[str, Any],
        key: str,
    ) -> AnalyticalSeries:
        """Attach one raw export to a task with its declared method and
        context; when the format is supported, derive + persist the
        processed trace with a recorded transform version (AT-0703-1)."""
        if self.ctx.principal_kind != "user":
            raise DomainError(ErrorCode.FORBIDDEN, "only humans can ingest analytical data")
        self.ctx.require(CAP_EDIT_TASK, task_id)
        self.ctx.require(CAP_MANAGE_SOURCES, task_id)
        spec = self._validate_spec(IngestSpec, raw_spec)
        if not 1 <= len(key) <= 100:
            raise DomainError(ErrorCode.VALIDATION, "bounded idempotency key required")
        self._lock_task(task_id)
        digest = hashlib.sha256(
            json.dumps(
                {"ingest": spec.digest(), "raw": str(raw_artifact_id)},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        old = self.db.scalar(
            select(AnalyticalSeries).where(
                AnalyticalSeries.workspace_id == self.ctx.workspace_id,
                AnalyticalSeries.task_id == task_id,
                AnalyticalSeries.creation_key == key,
            )
        )
        if old:
            if old.spec_digest != digest:
                raise DomainError(
                    ErrorCode.IDEMPOTENCY_MISMATCH,
                    "creation key reused with a different ingest",
                )
            return old
        artifact = self._raw_artifact(raw_artifact_id)
        with self.vault.open_blob(self.ctx.workspace_id, artifact.storage_key) as f:
            data = f.read()

        detected = self.adapter.detect(data, filename=artifact.original_name)
        sample_id = self._sample_id(spec)
        base = {
            "workspace_id": self.ctx.workspace_id,
            "task_id": task_id,
            "label": spec.label or artifact.original_name,
            "method": spec.method,
            "sample_id": sample_id,
            "instrument": spec.instrument.model_dump(mode="json"),
            "calibration": (spec.calibration.model_dump(mode="json") if spec.calibration else None),
            "sample": spec.sample.model_dump(mode="json"),
            "raw_artifact_id": artifact.id,
            "spec_digest": digest,
            "creation_key": key,
            "created_by": self.ctx.principal_id,
        }
        if detected is None:
            row = AnalyticalSeries(
                **base,
                source_format=None,
                interpretation_state="unsupported",
                processed_artifact_id=None,
                transform=None,
                detail={
                    "reason": "export format not supported by the pinned readers; "
                    "raw bytes retained with provenance, nothing was interpreted",
                    "supported_formats": sorted(self.adapter.capability()["formats"].keys()),
                },
            )
            self.db.add(row)
            self.db.flush()
            return row

        try:
            parsed = self.adapter.parse(data, format=detected)
        except AnalyticsFailure as e:
            raise self._domain(e) from e
        trace = self._check_units(parsed.trace, spec)
        try:
            processed, records = self.adapter.process(trace, spec.preprocessing)
        except AnalyticsFailure as e:
            raise self._domain(e) from e
        processed_artifact = self._persist_blob(
            json.dumps(
                {
                    "schema_version": "1",
                    "adapter_version": ADAPTER_VERSION,
                    "method": spec.method,
                    "trace": processed.model_dump(mode="json"),
                    "raw_artifact_id": str(artifact.id),
                },
                sort_keys=True,
            ).encode(),
            original_name=f"analytics-processed-{str(artifact.id)[:12]}.json",
            source_artifact_ids=[str(artifact.id)],
        )
        row = AnalyticalSeries(
            **base,
            source_format=detected,
            interpretation_state="processed",
            processed_artifact_id=processed_artifact.id,
            transform={
                "parser_version": parsed.parser_version,
                "preprocessing": [r.model_dump(mode="json") for r in records],
            },
            detail={
                "parser_version": parsed.parser_version,
                "source_metadata": parsed.metadata,
                "parser_warnings": parsed.warnings,
                "points": len(processed.x),
            },
        )
        self.db.add(row)
        self.db.flush()
        return row

    # ------------------------------------------------------------ compare

    def compare(
        self,
        task_id: uuid.UUID,
        left_series_id: uuid.UUID,
        right_series_id: uuid.UUID,
        raw_spec: dict[str, Any],
        key: str,
    ) -> AnalyticalComparison:
        """One scoped comparison (AT-0703-2). Both series must be
        processed; the adapter refuses cross-method/cross-unit pairs."""
        if self.ctx.principal_kind != "user":
            raise DomainError(ErrorCode.FORBIDDEN, "only humans can run a comparison")
        self.ctx.require(CAP_EDIT_TASK, task_id)
        spec = self._validate_spec(CompareSpec, raw_spec)
        if not 1 <= len(key) <= 100:
            raise DomainError(ErrorCode.VALIDATION, "bounded idempotency key required")
        self._lock_task(task_id)
        digest = hashlib.sha256(
            json.dumps(
                {
                    "compare": spec.digest(),
                    "left": str(left_series_id),
                    "right": str(right_series_id),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        old = self.db.scalar(
            select(AnalyticalComparison).where(
                AnalyticalComparison.workspace_id == self.ctx.workspace_id,
                AnalyticalComparison.task_id == task_id,
                AnalyticalComparison.creation_key == key,
            )
        )
        if old:
            if old.spec_digest != digest:
                raise DomainError(
                    ErrorCode.IDEMPOTENCY_MISMATCH,
                    "creation key reused with a different comparison",
                )
            return old
        left = self._series(task_id, left_series_id)
        right = self._series(task_id, right_series_id)
        trace_left = self._processed_trace(left)
        trace_right = self._processed_trace(right)
        try:
            outcome = self.adapter.compare(
                trace_left,
                trace_right,
                method_a=left.method,
                method_b=right.method,
                spec=spec,
            )
        except AnalyticsFailure as e:
            raise self._domain(e) from e
        similarity = outcome.similarity.model_dump(mode="json")
        result_artifact = self._persist_blob(
            json.dumps(
                {
                    "schema_version": "1",
                    "adapter_version": ADAPTER_VERSION,
                    "method": left.method,
                    "left_series_id": str(left.id),
                    "right_series_id": str(right.id),
                    "similarity": similarity,
                    "transform": outcome.transform,
                },
                sort_keys=True,
            ).encode(),
            original_name=f"analytics-comparison-{str(left.id)[:12]}-{str(right.id)[:12]}.json",
            source_artifact_ids=[
                str(left.processed_artifact_id),
                str(right.processed_artifact_id),
            ],
        )
        row = AnalyticalComparison(
            workspace_id=self.ctx.workspace_id,
            task_id=task_id,
            left_series_id=left.id,
            right_series_id=right.id,
            result_artifact_id=result_artifact.id,
            similarity=similarity,
            transform=outcome.transform,
            spec_digest=digest,
            creation_key=key,
            created_by=self.ctx.principal_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    # ------------------------------------------------------------- intern

    def _validate_spec(self, model: Any, raw: dict[str, Any]) -> Any:
        try:
            return model.model_validate(raw)
        except ValidationError as exc:
            raise DomainError(
                ErrorCode.ENGINE_UNSUPPORTED_INPUT,
                "unsupported or incomplete analytical spec; nothing was dropped",
            ) from exc

    def _domain(self, failure: AnalyticsFailure) -> DomainError:
        return DomainError(_FAILURE_CODES.get(failure.code, ErrorCode.VALIDATION), failure.message)

    def _lock_task(self, task_id: uuid.UUID) -> ResearchTask:
        task = self.db.scalar(
            select(ResearchTask)
            .where(
                ResearchTask.id == task_id,
                ResearchTask.workspace_id == self.ctx.workspace_id,
            )
            .with_for_update()
        )
        if task is None:
            raise not_found("task")
        if task.workflow_state != "active":
            raise DomainError(ErrorCode.CONFLICT, "analytical ingest requires an active task")
        return task

    def _raw_artifact(self, artifact_id: uuid.UUID) -> Artifact:
        artifact = self.db.get(Artifact, artifact_id)
        if (
            artifact is None
            or artifact.workspace_id != self.ctx.workspace_id
            or artifact.upload_state != "committed"
            or artifact.source_kind not in ("upload", "import")
        ):
            raise not_found("raw export artifact")
        return artifact

    def _series(self, task_id: uuid.UUID, series_id: uuid.UUID) -> AnalyticalSeries:
        row = self.db.scalar(
            select(AnalyticalSeries).where(
                AnalyticalSeries.id == series_id,
                AnalyticalSeries.workspace_id == self.ctx.workspace_id,
                AnalyticalSeries.task_id == task_id,
            )
        )
        if row is None:
            raise not_found("analytical series")
        return row

    def _processed_trace(self, series: AnalyticalSeries) -> SpectrumTrace:
        if series.interpretation_state != "processed" or not series.processed_artifact_id:
            raise DomainError(
                ErrorCode.VALIDATION,
                "series has no processed values (interpretation unsupported); "
                "comparisons only run on processed series",
            )
        artifact = self.db.get(Artifact, series.processed_artifact_id)
        if artifact is None or artifact.upload_state != "committed":
            raise not_found("processed values artifact")
        with self.vault.open_blob(self.ctx.workspace_id, artifact.storage_key) as f:
            payload = json.loads(f.read().decode())
        try:
            return SpectrumTrace.model_validate(payload["trace"])
        except (ValidationError, KeyError) as exc:
            raise DomainError(
                ErrorCode.VALIDATION, "processed artifact payload is malformed"
            ) from exc

    def _check_units(self, trace: SpectrumTrace, spec: IngestSpec) -> SpectrumTrace:
        """Declared units are operator metadata: a unitless export
        (csv-xy) takes them verbatim; a unit-bearing export (JCAMP) must
        agree — conflicting metadata is an error, never an override."""
        file_x = trace.x_unit if trace.x_unit != UNDECLARED_UNIT else None
        file_y = trace.y_unit if trace.y_unit != UNDECLARED_UNIT else None
        conflicts = []
        if file_x and file_x.lower() != spec.x_unit.lower():
            conflicts.append(f"x_unit declared {spec.x_unit!r} vs file {file_x!r}")
        if file_y and file_y != "arbitrary" and file_y.lower() != spec.y_unit.lower():
            conflicts.append(f"y_unit declared {spec.y_unit!r} vs file {file_y!r}")
        if conflicts:
            raise DomainError(
                ErrorCode.VALIDATION,
                "declared units conflict with the export: " + "; ".join(conflicts),
            )
        return SpectrumTrace(
            x=trace.x,
            y=trace.y,
            x_unit=file_x or spec.x_unit,
            y_unit=file_y or spec.y_unit,
        )

    def _sample_id(self, spec: IngestSpec) -> uuid.UUID | None:
        """Link to a real lab sample only when the declared reference is
        a UUID that exists in this workspace; the raw reference itself is
        retained in the series' sample metadata regardless."""
        if spec.sample.sample_id is None:
            return None
        try:
            candidate = uuid.UUID(spec.sample.sample_id)
        except ValueError:
            return None
        exists = self.db.scalar(
            select(LabSample.id).where(
                LabSample.id == candidate,
                LabSample.workspace_id == self.ctx.workspace_id,
            )
        )
        return exists

    def _persist_blob(
        self,
        data: bytes,
        *,
        original_name: str,
        source_artifact_ids: list[str],
    ) -> Artifact:
        """Store derived bytes in the private vault as a committed
        artifact — content-addressed, workspace-scoped, never served."""
        artifact = Artifact(
            workspace_id=self.ctx.workspace_id,
            storage_key="",
            media_type="application/json",
            original_name=original_name,
            source_kind="derived",
            source_artifact_ids=source_artifact_ids,
            created_by=self.ctx.principal_id,
        )
        self.db.add(artifact)
        self.db.flush()
        staging = self.vault.begin_staging(self.ctx.workspace_id, artifact.id)
        self.vault.append_bytes(staging, data)
        key, size = self.vault.commit(
            self.ctx.workspace_id, artifact.id, hashlib.sha256(data).hexdigest()
        )
        artifact.storage_key = key
        artifact.checksum_sha256 = hashlib.sha256(data).hexdigest()
        artifact.byte_size = size
        artifact.upload_state = "committed"
        artifact.committed_at = datetime.now(UTC)
        self.db.flush()
        return artifact


def series_state(row: AnalyticalSeries) -> dict[str, Any]:
    """Client-safe series manifest: lineage + transform + interpretation
    state. Vault storage keys never cross the API — artifact ids only."""
    return {
        "seriesId": str(row.id),
        "taskId": str(row.task_id),
        "label": row.label,
        "method": row.method,
        "sampleId": str(row.sample_id) if row.sample_id else None,
        "sample": row.sample,
        "instrument": row.instrument,
        "calibration": row.calibration,
        "sourceFormat": row.source_format,
        "interpretationState": row.interpretation_state,
        "rawArtifactId": str(row.raw_artifact_id),
        "processedArtifactId": str(row.processed_artifact_id)
        if row.processed_artifact_id
        else None,
        "transform": row.transform,
        "detail": row.detail,
    }


def comparison_state(row: AnalyticalComparison) -> dict[str, Any]:
    """Client-safe comparison manifest: scoped similarity + the recorded
    transform chain. The value travels with its algorithm, version,
    applied range and interpretation limits (§16.5)."""
    return {
        "taskId": str(row.task_id),
        "leftSeriesId": str(row.left_series_id),
        "rightSeriesId": str(row.right_series_id),
        "resultArtifactId": str(row.result_artifact_id),
        "similarity": row.similarity,
        "transform": row.transform,
    }
