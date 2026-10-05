"""CS-0305 integration tests — data-quality reporting + revocation
lineage impact.

AT-0305-2  instrument failures vs genuine misses stay separate
AT-0305-3  revoked trained source → affected releases identified,
           no unlearning claim
"""

from __future__ import annotations

from pathlib import Path

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.auth.context import load_context
from studio.domain.evidence.archive import ArchiveLimits
from studio.domain.evidence.imports import ImportService
from studio.domain.evidence.retrieval import RetrievalService
from studio.domain.evidence.revocation import RevocationService
from studio.domain.evidence.service import ArtifactService
from studio.domain.evidence.vault import Vault
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Artifact,
    EvidenceClaim,
    ExtractedRecord,
    ImportBatch,
    Principal,
    PrincipalCapability,
    SourceRevocation,
    Workspace,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def env(session: Session, tmp_path: Path):
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    steward_p = Principal(workspace_id=ws.id, kind="user", login="ds", display_name="ds")
    session.add(steward_p)
    session.flush()
    for cap in sorted(capabilities_for_role("data_steward")):
        session.add(
            PrincipalCapability(workspace_id=ws.id, principal_id=steward_p.id, capability=cap)
        )
    session.flush()
    vault = Vault(tmp_path)
    ctx = load_context(session, ws.id, steward_p.id)
    return {
        "ws": ws,
        "ctx": ctx,
        "artifacts": ArtifactService(
            session, vault, max_bytes=64 * 1024 * 1024, archive_limits=ArchiveLimits()
        ),
        "importer": ImportService(session, vault, isolate=False),
        "retrieval": RetrievalService(session),
        "revocations": RevocationService(session, ctx),
        "session": session,
    }


def _import(env: dict, text: str, name: str = "doc.csv") -> tuple[Artifact, ImportBatch]:
    ctx = env["ctx"]
    data = text.encode()
    artifact = env["artifacts"].initiate(
        ctx,
        original_name=name,
        media_type="text/csv",
        declared_size=len(data),
        declared_checksum=None,
    )
    env["artifacts"].staging_path(ctx, artifact.id).write_bytes(data)
    artifact = env["artifacts"].finish(ctx, artifact.id)
    batch, _ = env["importer"].import_artifact(ctx, artifact.id)
    return artifact, batch


class TestOutcomeCategories:
    """AT-0305-2: a report over mixed outcomes keeps instrument failures
    and genuine performance misses in separate categories, original
    labels preserved, nothing collapsed into a score."""

    def test_failure_categories_stay_separate(self, env: dict) -> None:
        _, batch = _import(env, "component,amount\nresin_A,12\n")
        ctx = env["ctx"]
        s = env["session"]
        # one instrument failure, one genuine miss — both "outcomes",
        # different categories and labels
        claims = [
            EvidenceClaim(
                workspace_id=env["ws"].id,
                kind="measured_outcome",
                status="accepted",
                subject={"entity": "run-41"},
                statement={
                    "text": "viscosity not recorded",
                    "metric": "viscosity",
                    "outcome": {
                        "label": "run aborted — sensor offline",
                        "kind": "measured",
                        "category": "instrument_failure",
                    },
                },
                conditions={"method": "ASTM D2196"},
                source_batch_id=batch.id,
            ),
            EvidenceClaim(
                workspace_id=env["ws"].id,
                kind="measured_outcome",
                status="accepted",
                subject={"entity": "run-42"},
                statement={
                    "text": "tack below target",
                    "metric": "tack",
                    "outcome": {
                        "label": "tack 3.1 vs target ≥ 4.0",
                        "kind": "measured",
                        "category": "performance_miss",
                    },
                },
                conditions={"method": "loop tack"},
                source_batch_id=batch.id,
            ),
        ]
        for c in claims:
            s.add(c)
        s.flush()

        report = env["importer"].batch_quality_report(ctx, batch.id)
        cats = report["outcomes"]["byCategory"]
        assert set(cats) == {"instrument_failure", "performance_miss"}
        assert cats["instrument_failure"]["labels"] == ["run aborted — sensor offline"]
        assert cats["performance_miss"]["labels"] == ["tack 3.1 vs target ≥ 4.0"]
        # kinds and coverage matrix carry method/metric honestly
        assert report["outcomes"]["byKind"] == {"measured": 2}
        cov = report["coverage"]
        assert cov["byMethod"]["ASTM D2196"] == 1
        assert cov["byMetric"]["viscosity"] == 1
        assert cov["byEvidenceType"]["measured_outcome"] == 2
        # no single inflated score exists anywhere
        assert "score" not in report and "quality_score" not in report


class TestRevocationImpact:
    """AT-0305-3: revoking a source propagates to index, records,
    claims, and downstream lineage — and honestly says nothing was
    unlearned."""

    def test_impact_report_and_propagation(self, env: dict) -> None:
        ctx = env["ctx"]
        artifact, batch = _import(env, "component,amount\nresin_A,12\n")
        env["retrieval"].index_batch(ctx, batch.id)
        # exposure: a search that served these chunks
        hits, _ = env["retrieval"].search(ctx, "resin_A")
        assert hits

        claim = EvidenceClaim(
            workspace_id=env["ws"].id,
            kind="document_claim",
            status="accepted",
            subject={"entity": "recipe"},
            statement={"text": "resin_A at 12"},
            source_batch_id=batch.id,
        )
        env["session"].add(claim)
        # a downstream artifact trained on / derived from the source
        derived = Artifact(
            workspace_id=env["ws"].id,
            storage_key="de/adbeef",
            media_type="application/json",
            original_name="dataset-snapshot.json",
            source_kind="derived",
            review_state="accepted",
            upload_state="committed",
            source_artifact_ids=[str(artifact.id)],
            rights={"training": "allowed"},
        )
        env["session"].add(derived)
        env["session"].flush()

        # preview (read-only) then the real revocation
        preview = env["revocations"].impact(ctx, artifact.id)
        assert preview["chunksRevoked"] == 2
        assert preview["affectedDerivedIds"] == [str(derived.id)]

        rev = env["revocations"].revoke(ctx, artifact.id, reason="supplier revoked rights")
        report = rev.report
        # propagation landed: chunks out of index, claims superseded,
        # derived artifact suspended for re-review
        assert report["claimsSuperseded"] == [str(claim.id)]
        assert report["exposedPrincipalIds"] == [str(ctx.principal_id)]
        assert report["affectedDerivedIds"] == [str(derived.id)]
        # §17.5 honesty — releases identified where they exist,
        # unlearning never claimed
        assert report["affectedModelReleaseIds"] == []
        assert report["unlearningGuarantee"] is False

        env["session"].refresh(claim)
        assert claim.status == "superseded"
        env["session"].refresh(derived)
        assert derived.retention["lineage_review"] == "required"
        assert derived.retention["lineage_affected_by"] == str(artifact.id)
        env["session"].refresh(artifact)
        assert artifact.review_state == "revoked"
        # extracted records marked with the reason, not silently dropped
        recs = (
            env["session"]
            .execute(select(ExtractedRecord).where(ExtractedRecord.batch_id == batch.id))
            .scalars()
            .all()
        )
        assert recs and all(r.status == "rejected" for r in recs)
        assert all("source_revoked" in r.flags for r in recs)
        # search can no longer serve it
        hits2, _ = env["retrieval"].search(ctx, "resin_A")
        assert hits2 == []
        # the revocation itself is a persisted audit record
        stored = (
            env["session"]
            .execute(select(SourceRevocation).where(SourceRevocation.artifact_id == artifact.id))
            .scalar_one()
        )
        assert stored.id == rev.id

    def test_revoke_twice_conflicts(self, env: dict) -> None:
        artifact, _ = _import(env, "component,amount\nx,1\n")
        ctx = env["ctx"]
        env["revocations"].revoke(ctx, artifact.id, reason="first")
        with pytest.raises(DomainError) as exc:
            env["revocations"].revoke(ctx, artifact.id, reason="again")
        assert exc.value.code == ErrorCode.CONFLICT

    def test_revoke_requires_reason(self, env: dict) -> None:
        artifact, _ = _import(env, "component,amount\nx,1\n")
        with pytest.raises(DomainError) as exc:
            env["revocations"].revoke(env["ctx"], artifact.id, reason="  ")
        assert exc.value.code == ErrorCode.VALIDATION
