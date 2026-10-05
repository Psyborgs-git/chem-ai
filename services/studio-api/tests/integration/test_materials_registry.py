"""CS-0203 acceptance tests — material/grade/lot/reference registry.

AT-0203-1  purchased reference with no recipe -> composition stays
           unknown; no ingredient list is invented
AT-0203-2  two grades sharing a chemical identifier -> dedup keeps
           them distinct until reviewed reconciliation
AT-0203-3  unreviewed identity match -> structure-required tool gets
           unsupported/missing identity, never a guess
"""

from __future__ import annotations

import pytest
from chem_studio_policy.capabilities import capabilities_for_role
from sqlalchemy.orm import Session

from studio.auth.context import ServiceContext, load_context
from studio.domain.materials.service import MaterialService
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    IdentityMatch,
    Principal,
    PrincipalCapability,
    Workspace,
)

pytestmark = pytest.mark.integration


def _principal(session: Session, ws: Workspace, kind: str, role: str, login: str) -> Principal:
    p = Principal(workspace_id=ws.id, kind=kind, login=login, display_name=login)
    session.add(p)
    session.flush()
    for cap in sorted(capabilities_for_role(role)):
        session.add(PrincipalCapability(workspace_id=ws.id, principal_id=p.id, capability=cap))
    session.flush()
    return p


def _ctx(session: Session, ws: Workspace, p: Principal) -> ServiceContext:
    return load_context(session, ws.id, p.id)


@pytest.fixture()
def ctxs(session: Session) -> tuple[ServiceContext, ServiceContext, ServiceContext]:
    ws = Workspace(slug="w", display_name="W")
    session.add(ws)
    session.flush()
    steward = _principal(session, ws, "user", "data_steward", "ds")
    reviewer = _principal(session, ws, "user", "scientific_reviewer", "sr")
    agent = _principal(session, ws, "agent", "agent", "bot")
    return (
        _ctx(session, ws, steward),
        _ctx(session, ws, reviewer),
        _ctx(session, ws, agent),
    )


class TestReferenceUnknownComposition:
    """AT-0203-1: no recipe -> no invented ingredient list."""

    def test_unknown_reference_saves_and_reads_as_unknown(
        self, ctxs: tuple[ServiceContext, ...], session: Session
    ) -> None:
        ctx, _, _ = ctxs
        svc = MaterialService(session, ctx)
        product = svc.create_reference_product(
            name="Acme All-Purpose Cleaner", supplier="Acme", category="cleaner"
        )
        session.commit()
        assert product.composition_knowledge == "unknown"
        assert svc.reference_composition(product_id=product.id) is None

    def test_revision_with_unknown_composition_rejects_ingredients(
        self, ctxs: tuple[ServiceContext, ...], session: Session
    ) -> None:
        ctx, _, _ = ctxs
        svc = MaterialService(session, ctx)
        product = svc.create_reference_product(name="Mystery Solvent")
        with pytest.raises(DomainError) as exc:
            svc.draft_reference_revision(
                product_id=product.id,
                payload={
                    "compositionKnowledge": "unknown",
                    "composition": [{"ingredient": "water", "fraction": "1.0"}],
                },
            )
        assert exc.value.code == ErrorCode.VALIDATION
        # honest payload with empty composition is fine
        rev = svc.draft_reference_revision(
            product_id=product.id,
            payload={
                "compositionKnowledge": "unknown",
                "composition": None,
                "claimedProperties": {"scent": "lemon (label claim)"},
            },
        )
        svc.freeze_reference_revision(revision_id=rev.id)
        session.commit()
        assert product.composition_knowledge == "unknown"
        assert svc.reference_composition(product_id=product.id) is None
        assert rev.status == "frozen"

    def test_known_composition_records_and_reads(
        self, ctxs: tuple[ServiceContext, ...], session: Session
    ) -> None:
        ctx, _, _ = ctxs
        svc = MaterialService(session, ctx)
        product = svc.create_reference_product(
            name="Labelled Solvent", composition_knowledge="partial"
        )
        rev = svc.draft_reference_revision(
            product_id=product.id,
            payload={
                "compositionKnowledge": "partial",
                "composition": [{"ingredient": "ethanol", "fraction": "0.3"}],
                "claimedProperties": {},
            },
        )
        svc.freeze_reference_revision(revision_id=rev.id)
        session.commit()
        comp = svc.reference_composition(product_id=product.id)
        assert comp == [{"ingredient": "ethanol", "fraction": "0.3"}]


class TestSharedIdentifierGrades:
    """AT-0203-2: shared CAS identifier -> grades stay distinct."""

    def _two_grades(self, session: Session, ctx: ServiceContext) -> tuple[str, str]:
        svc = MaterialService(session, ctx)
        a = svc.create_identity(
            kind="defined_molecule",
            name="Sodium laureth sulfate (supplier A)",
            identifiers=[{"scheme": "cas", "value": "9004-82-4", "source": "sds-a.pdf"}],
        )
        b = svc.create_identity(
            kind="defined_molecule",
            name="SLES (supplier B)",
            identifiers=[{"scheme": "cas", "value": "9004-82-4", "source": "coa-b.pdf"}],
        )
        ga = svc.create_grade(material_id=a.id, supplier="ChemCo", grade_name="SLES 70%")
        gb = svc.create_grade(material_id=b.id, supplier="OtherCo", grade_name="SLES-2EO")
        session.commit()
        return str(ga.id), str(gb.id)

    def test_shared_identifier_report_keeps_distinct(
        self, ctxs: tuple[ServiceContext, ...], session: Session
    ) -> None:
        ctx, _, _ = ctxs
        ga, gb = self._two_grades(session, ctx)
        svc = MaterialService(session, ctx)
        groups = svc.find_shared_identifier_grades()
        assert len(groups) == 1
        group = groups[0]
        assert (group["scheme"], group["value"]) == ("cas", "9004-82-4")
        ids = {g["gradeId"] for g in group["grades"]}
        assert ids == {ga, gb}
        assert group["unresolved"] is True
        # both grades still exist, unreconciled
        for gid in (ga, gb):
            from studio.persistence.models import MaterialGrade

            row = session.get(MaterialGrade, __import__("uuid").UUID(gid))
            assert row is not None and row.reconciled_into is None

    def test_reviewed_reconciliation_resolves_group(
        self, ctxs: tuple[ServiceContext, ...], session: Session
    ) -> None:
        ctx, ctx_rev, _ = ctxs
        import uuid as _uuid

        ga, gb = self._two_grades(session, ctx)
        svc_rev = MaterialService(session, ctx_rev)
        svc_rev.reconcile_grades(
            keep_grade_id=_uuid.UUID(ga),
            merge_grade_id=_uuid.UUID(gb),
            reason="same supplier grade under two trade names",
        )
        session.commit()
        from studio.persistence.models import MaterialGrade

        merged = session.get(MaterialGrade, _uuid.UUID(gb))
        assert merged is not None and merged.reconciled_into == _uuid.UUID(ga)
        groups = MaterialService(session, ctx).find_shared_identifier_grades()
        assert groups[0]["unresolved"] is False

    def test_reconciliation_requires_review_and_reason(
        self, ctxs: tuple[ServiceContext, ...], session: Session
    ) -> None:
        ctx, ctx_rev, ctx_agent = ctxs
        import uuid as _uuid

        ga, gb = self._two_grades(session, ctx)
        # a data steward cannot reconcile — review_science required
        with pytest.raises(DomainError) as exc:
            MaterialService(session, ctx).reconcile_grades(
                keep_grade_id=_uuid.UUID(ga),
                merge_grade_id=_uuid.UUID(gb),
                reason="dup",
            )
        assert exc.value.code == ErrorCode.FORBIDDEN
        # nor an agent
        with pytest.raises(DomainError) as exc:
            MaterialService(session, ctx_agent).reconcile_grades(
                keep_grade_id=_uuid.UUID(ga),
                merge_grade_id=_uuid.UUID(gb),
                reason="dup",
            )
        assert exc.value.code == ErrorCode.FORBIDDEN
        # reviewer still needs a reason
        with pytest.raises(DomainError) as exc:
            MaterialService(session, ctx_rev).reconcile_grades(
                keep_grade_id=_uuid.UUID(ga),
                merge_grade_id=_uuid.UUID(gb),
                reason="",
            )
        assert exc.value.code == ErrorCode.VALIDATION


class TestStructureRequiredGate:
    """AT-0203-3: unreviewed match -> structure-required tool reports
    missing identity, never a guess."""

    def _identities(self, session: Session, ctx: ServiceContext):
        svc = MaterialService(session, ctx)
        src = svc.create_identity(kind="unknown", name="white powder, unlabeled jar")
        cand = svc.create_identity(
            kind="defined_molecule",
            name="sodium bicarbonate",
            structure="C(=O)(O)O[Na]",
            structure_format="smiles",
            identifiers=[{"scheme": "cas", "value": "144-55-8", "source": "guess"}],
        )
        session.commit()
        return src, cand

    def test_unknown_identity_has_no_structure(
        self, ctxs: tuple[ServiceContext, ...], session: Session
    ) -> None:
        ctx, _, _ = ctxs
        svc = MaterialService(session, ctx)
        src, _ = self._identities(session, ctx)
        with pytest.raises(DomainError) as exc:
            svc.require_structure(src.id)
        assert exc.value.code == ErrorCode.MISSING_IDENTITY

    def test_proposed_match_does_not_unblock_structure(
        self, ctxs: tuple[ServiceContext, ...], session: Session
    ) -> None:
        ctx, _, _ = ctxs
        svc = MaterialService(session, ctx)
        src, cand = self._identities(session, ctx)
        # even if an import proposed the match, the *source* identity
        # still reports missing structure — a proposal is not review
        svc.propose_match(
            source_identity_id=src.id,
            candidate_identity_id=cand.id,
            confidence="0.9",
            rationale="similar IR spectrum",
            proposed_by="import:doc-1",
        )
        session.commit()
        with pytest.raises(DomainError) as exc:
            svc.require_structure(src.id)
        assert exc.value.code == ErrorCode.MISSING_IDENTITY
        # and the candidate's own structure is only unreviewed
        with pytest.raises(DomainError) as exc:
            svc.require_structure(cand.id)
        assert exc.value.code == ErrorCode.MISSING_IDENTITY
        assert exc.value.safe_details["structureStatus"] == "unreviewed"

    def test_reviewed_structure_passes(
        self, ctxs: tuple[ServiceContext, ...], session: Session
    ) -> None:
        ctx, ctx_rev, _ = ctxs
        svc = MaterialService(session, ctx)
        _, cand = self._identities(session, ctx)
        svc_rev = MaterialService(session, ctx_rev)
        svc_rev.review_structure(identity_id=cand.id)
        session.commit()
        assert svc.require_structure(cand.id) == "C(=O)(O)O[Na]"
        # an agent can never review
        _, _, ctx_agent = ctxs
        svc_agent = MaterialService(session, ctx_agent)
        src2 = svc.create_identity(
            kind="defined_molecule", name="x", structure="C", structure_format="smiles"
        )
        session.commit()
        with pytest.raises(DomainError) as exc:
            svc_agent.review_structure(identity_id=src2.id)
        assert exc.value.code == ErrorCode.FORBIDDEN

    def test_match_review_human_only(
        self, ctxs: tuple[ServiceContext, ...], session: Session
    ) -> None:
        ctx, _, ctx_agent = ctxs
        svc = MaterialService(session, ctx)
        src, cand = self._identities(session, ctx)
        match = svc.propose_match(
            source_identity_id=src.id,
            candidate_identity_id=cand.id,
            proposed_by="agent:parser-v1",
        )
        session.commit()
        with pytest.raises(DomainError) as exc:
            MaterialService(session, ctx_agent).review_match(match_id=match.id, decision="accepted")
        assert exc.value.code == ErrorCode.FORBIDDEN
        # accepted matches still don't fabricate structure on source
        _, ctx_rev, _ = ctxs
        svc_rev = MaterialService(session, ctx_rev)
        svc_rev.review_match(match_id=match.id, decision="accepted")
        session.commit()
        row = session.get(IdentityMatch, match.id)
        assert row is not None and row.status == "accepted"
        with pytest.raises(DomainError) as exc:
            svc.require_structure(src.id)
        assert exc.value.code == ErrorCode.MISSING_IDENTITY


class TestRegistryScopeIsolation:
    def test_cross_workspace_identity_invisible(
        self, ctxs: tuple[ServiceContext, ...], session: Session
    ) -> None:
        ctx, _, _ = ctxs
        svc = MaterialService(session, ctx)
        mine = svc.create_identity(kind="polymer", name="PVP K30")
        other_ws = Workspace(slug="other", display_name="Other")
        session.add(other_ws)
        session.flush()
        outsider = _principal(session, other_ws, "user", "researcher", "o")
        svc_other = MaterialService(session, _ctx(session, other_ws, outsider))
        session.commit()
        with pytest.raises(DomainError) as exc:
            svc_other.require_structure(mine.id)
        assert exc.value.code == ErrorCode.NOT_FOUND

    def test_lot_and_grade_lifecycle(
        self, ctxs: tuple[ServiceContext, ...], session: Session
    ) -> None:
        ctx, _, _ = ctxs
        svc = MaterialService(session, ctx)
        mat = svc.create_identity(kind="defined_molecule", name="citric acid")
        grade = svc.create_grade(
            material_id=mat.id,
            supplier="SigmaCo",
            grade_name="anhydrous >99.5%",
            active_content={
                "value": "0.995",
                "unit": "mass_fraction",
                "basis": "as_supplied",
                "original_text": "99.5%",
            },
        )
        # a fraction without basis is rejected at the DTO boundary
        with pytest.raises(DomainError) as exc:
            svc.create_grade(
                material_id=mat.id,
                supplier="SigmaCo",
                grade_name="bad",
                active_content={
                    "value": "0.5",
                    "unit": "mass_fraction",
                    "basis": None,
                    "original_text": None,
                },
            )
        assert exc.value.code == ErrorCode.UNKNOWN_BASIS
        lot = svc.create_lot(grade_id=grade.id, lot_number="MK-2201")
        session.commit()
        assert lot.grade_id == grade.id
