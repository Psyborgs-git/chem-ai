"""CS-0703 integration — ingest lineage, scoped comparison, unsupported formats.

AT-0703-1  a raw export ingested with declared method/context persists
           sample/method/raw lineage plus the derived processed artifact
           and its transform record (parser + preprocessing versions).
AT-0703-2  comparing two processed series returns a SCOPED similarity
           whose algorithm, version, applied range, aligned point count
           and interpretation limits are persisted on the result.
AT-0703-3  an unsupported instrument format still ingests: the raw
           bytes stay in the vault and interpretation is 'unsupported'
           — a blocked capability label, not a guessed parse.

All fixture spectra are synthetic; nothing here is scientific evidence.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session

from studio.auth.context import load_context
from studio.config.settings import Settings
from studio.domain.chemistry.analytics import AnalyticsService
from studio.domain.evidence.vault import Vault
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    AnalyticalSeries,
    Artifact,
    Principal,
    PrincipalCapability,
    Project,
    ResearchTask,
    Workspace,
)

pytestmark = pytest.mark.integration

FIXTURES = Path("fixtures/synthetic/analytics")
INGEST_SPEC = {
    "method": "infrared",
    "x_unit": "1/CM",
    "y_unit": "TRANSMITTANCE",
    "instrument": {"vendor": "ACME", "model": "FT-900", "resolution": "4 cm-1"},
    "calibration": {"reference": "polystyrene film", "performed_at": "2026-09-30"},
    "sample": {"label": "synthetic film A", "preparation": "cast film, fixture"},
}
COMPARE_SPEC = {"similarity": {"algorithm": "cosine"}}


def _commit_artifact(
    session: Session,
    vault: Vault,
    workspace_id: uuid.UUID,
    principal_id: uuid.UUID,
    data: bytes,
    name: str,
) -> Artifact:
    artifact = Artifact(
        workspace_id=workspace_id,
        storage_key="",
        media_type="application/octet-stream",
        original_name=name,
        source_kind="upload",
        created_by=principal_id,
    )
    session.add(artifact)
    session.flush()
    staging = vault.begin_staging(workspace_id, artifact.id)
    vault.append_bytes(staging, data)
    key, size = vault.commit(workspace_id, artifact.id, hashlib.sha256(data).hexdigest())
    artifact.storage_key = key
    artifact.checksum_sha256 = hashlib.sha256(data).hexdigest()
    artifact.byte_size = size
    artifact.upload_state = "committed"
    artifact.committed_at = datetime.now(UTC)
    session.flush()
    return artifact


@pytest.fixture()
def env(session: Session, tmp_path: Path):
    ws = Workspace(slug="analytics", display_name="Analytics tests")
    session.add(ws)
    session.flush()
    user = Principal(workspace_id=ws.id, kind="user", login="r", display_name="r")
    session.add(user)
    session.flush()
    for cap in sorted(capabilities_for_role("researcher")):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=user.id, capability=cap))
    project = Project(workspace_id=ws.id, slug="analytics", name="Analytics")
    session.add(project)
    session.flush()
    task = ResearchTask(
        workspace_id=ws.id,
        project_id=project.id,
        mode="discover",
        title="Reference analysis fixture",
        target_kind="formulation",
        workflow_state="active",
    )
    session.add(task)
    session.flush()
    ctx = load_context(session, ws.id, user.id)
    root = tmp_path / "vault"
    service = AnalyticsService(session, ctx, Settings(vault_root=root), Vault(root))
    return {"ctx": ctx, "task": task, "service": service, "vault": Vault(root)}


def _ingest(
    env, session: Session, name: str, key: str, spec: dict | None = None
) -> AnalyticalSeries:
    artifact = _commit_artifact(
        session,
        env["vault"],
        env["ctx"].workspace_id,
        env["ctx"].principal_id,
        (FIXTURES / name).read_bytes(),
        name,
    )
    return env["service"].ingest(env["task"].id, artifact.id, spec or INGEST_SPEC, key)


def test_at0703_1_ingest_keeps_lineage_and_transform_version(env, session: Session) -> None:
    row = _ingest(env, session, "ir-film-a.dx", "ingest-a")
    session.flush()
    assert row.interpretation_state == "processed"
    assert row.source_format == "jcamp-dx"
    assert row.method == "infrared"
    # Raw + processed lineage + declared context are all persisted.
    assert row.raw_artifact_id is not None
    assert row.processed_artifact_id is not None
    assert row.instrument["vendor"] == "ACME"
    assert row.calibration["reference"] == "polystyrene film"
    assert row.sample["label"] == "synthetic film A"
    # Transform record is pinned, not implied.
    assert row.transform["parser_version"] == "jcampdx-reader/v1"
    assert row.transform["preprocessing"] == []
    # The processed artifact is a real vault blob deriving from the raw one.
    processed = session.get(Artifact, row.processed_artifact_id)
    assert processed is not None and processed.source_kind == "derived"
    assert processed.upload_state == "committed"
    assert str(row.raw_artifact_id) in processed.source_artifact_ids
    with env["vault"].open_blob(env["ctx"].workspace_id, processed.storage_key) as f:
        payload = json.loads(f.read().decode())
    assert len(payload["trace"]["x"]) == 801
    assert payload["method"] == "infrared"


def test_at0703_1_replay_and_mismatch(env, session: Session) -> None:
    row = _ingest(env, session, "ir-film-a.dx", "same-key")
    artifact2 = _commit_artifact(
        session,
        env["vault"],
        env["ctx"].workspace_id,
        env["ctx"].principal_id,
        (FIXTURES / "ir-film-a.dx").read_bytes(),
        "again.dx",
    )
    with pytest.raises(DomainError) as exc:
        env["service"].ingest(env["task"].id, artifact2.id, INGEST_SPEC, "same-key")
    assert exc.value.code == ErrorCode.IDEMPOTENCY_MISMATCH
    # Exact replay of the original request returns the original row.
    replay = env["service"].ingest(env["task"].id, row.raw_artifact_id, INGEST_SPEC, "same-key")
    assert replay.id == row.id


def test_at0703_2_scoped_comparison_not_identity(env, session: Session) -> None:
    left = _ingest(env, session, "ir-film-a.dx", "ingest-a")
    right = _ingest(env, session, "ir-film-b.dx", "ingest-b")
    row = env["service"].compare(env["task"].id, left.id, right.id, COMPARE_SPEC, "cmp-1")
    session.flush()
    sim = row.similarity
    assert sim["algorithm"] == "cosine"
    assert sim["algorithm_version"] == "cosine-similarity/v1"
    assert 0.9 < sim["value"] < 1.0  # similar synthetic pair — a value, not a claim
    assert sim["scope"]["x_unit"] == "1/CM"
    assert sim["scope"]["aligned_points"] == 2048
    assert sim["scientific_status"] == "not_composition_evidence"
    assert sim["interpretation_limits"]  # persisted, not implied
    assert any(
        "not evidence of identical composition" in lim
        for lim in sim["interpretation_limits"]
    )
    # The transform chain travels with the result and is reproducible.
    assert row.transform["alignment"]["version"] == "resample-linear/v1"
    result_artifact = session.get(Artifact, row.result_artifact_id)
    assert result_artifact is not None and result_artifact.source_kind == "derived"
    # A ranged comparison records the applied range.
    ranged = env["service"].compare(
        env["task"].id,
        left.id,
        right.id,
        {"similarity": {"algorithm": "pearson", "range_min": 1400.0, "range_max": 3200.0}},
        "cmp-2",
    )
    assert ranged.similarity["algorithm"] == "pearson"
    assert ranged.similarity["scope"]["range_min"] >= 1400.0
    assert ranged.similarity["scope"]["range_max"] <= 3200.0


def test_at0703_2_cross_method_and_unprocessed_refused(env, session: Session) -> None:
    left = _ingest(env, session, "ir-film-a.dx", "ingest-a")
    uv = _ingest(
        env,
        session,
        "uv-sample-a.csv",
        "ingest-uv",
        {
            "method": "uv_vis",
            "x_unit": "nm",
            "y_unit": "absorbance",
            "sample": {"label": "solution A"},
        },
    )
    assert uv.interpretation_state == "processed"  # csv-xy is supported
    with pytest.raises(DomainError) as exc:
        env["service"].compare(env["task"].id, left.id, uv.id, COMPARE_SPEC, "cmp-x")
    assert exc.value.code == ErrorCode.METHOD_INCOMPATIBLE
    un = _ingest(env, session, "vendor-binary.spc", "ingest-spc")
    with pytest.raises(DomainError) as exc:
        env["service"].compare(env["task"].id, left.id, un.id, COMPARE_SPEC, "cmp-y")
    assert exc.value.code == ErrorCode.VALIDATION


def test_at0703_3_unsupported_format_stores_raw_marked(env, session: Session) -> None:
    row = _ingest(env, session, "vendor-binary.spc", "ingest-spc")
    session.flush()
    # Raw stored with provenance; interpretation explicitly unsupported.
    assert row.interpretation_state == "unsupported"
    assert row.source_format is None
    assert row.processed_artifact_id is None
    assert row.transform is None
    assert row.raw_artifact_id is not None
    assert "not supported" in row.detail["reason"]
    listed = env["service"].list_series(env["task"].id)
    assert [r.id for r in listed] == [row.id]
    # The raw blob is intact in the vault.
    raw = session.get(Artifact, row.raw_artifact_id)
    assert raw is not None and raw.upload_state == "committed"


def test_capability_checks_are_server_side(env, session: Session) -> None:
    viewer = Principal(
        workspace_id=env["ctx"].workspace_id, kind="user", login="v", display_name="v"
    )
    session.add(viewer)
    session.flush()
    for cap in sorted(capabilities_for_role("viewer")):
        session.add(
            PrincipalCapability(
                workspace_id=env["ctx"].workspace_id, principal_id=viewer.id, capability=cap
            )
        )
    session.flush()
    vctx = load_context(session, env["ctx"].workspace_id, viewer.id)
    vsvc = AnalyticsService(session, vctx, Settings(vault_root=env["vault"].root))
    artifact = _commit_artifact(
        session,
        env["vault"],
        env["ctx"].workspace_id,
        env["ctx"].principal_id,
        (FIXTURES / "ir-film-a.dx").read_bytes(),
        "ir.dx",
    )
    with pytest.raises(DomainError) as exc:
        vsvc.ingest(env["task"].id, artifact.id, INGEST_SPEC, "v1")
    assert exc.value.code == ErrorCode.FORBIDDEN
    # A viewer can still read what exists (read_project).
    assert vsvc.list_series(env["task"].id) == []


def test_spec_validation_rejects_guessed_input(env, session: Session) -> None:
    artifact = _commit_artifact(
        session,
        env["vault"],
        env["ctx"].workspace_id,
        env["ctx"].principal_id,
        (FIXTURES / "ir-film-a.dx").read_bytes(),
        "ir.dx",
    )
    with pytest.raises(DomainError) as exc:
        env["service"].ingest(env["task"].id, artifact.id, {"method": "infrared"}, "bad")
    assert exc.value.code == ErrorCode.ENGINE_UNSUPPORTED_INPUT
    # Declared units that contradict the export are a conflict, not an override.
    with pytest.raises(DomainError) as exc:
        env["service"].ingest(
            env["task"].id,
            artifact.id,
            {**INGEST_SPEC, "x_unit": "nm"},
            "conflict",
        )
    assert exc.value.code == ErrorCode.VALIDATION
