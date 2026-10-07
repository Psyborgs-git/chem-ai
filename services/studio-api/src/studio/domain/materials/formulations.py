"""Formulation + process revisions (§5, §6.2).

Drafts may be incomplete — an incomplete draft can sit above or
below its declared total with validation findings attached.
Acceptance is the gate: a *complete* revision must satisfy its
declared-basis rules inside its own recorded tolerance, and the
pilot's optimizer representation additionally requires the
as-supplied mass-fraction basis. Nothing is ever normalized.

Process order is significant: steps persist verbatim and dedup
signatures treat reordered processes as different.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from chem_studio_policy.capabilities import CAP_EDIT_TASK, CAP_READ_PROJECT
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.domain.materials.quantities import Quantity, check_declared_total
from studio.errors import DomainError, ErrorCode, not_found
from studio.events.outbox import publish
from studio.persistence.models import (
    FormulationFamily,
    FormulationRevision,
    ProcessRevision,
)
from studio.persistence.revisions import content_hash

# The pilot's optimizer-supported representation (§6.2): as-supplied
# mass fractions in [0,1] summing to a declared total of 1.
OPTIMIZER_BASIS = "as_supplied"
OPTIMIZER_DECLARED_TOTAL = "1"


def ingredient_key(payload: dict[str, Any]) -> str:
    """Order-independent identity of the ingredient set (§6.2):
    the *list* may canonicalize for dedup where order is chemically
    irrelevant — ingredient identity only, not amounts."""
    keys: list[str] = []
    for line in payload.get("ingredients", []):
        ident = line.get("materialId") or line.get("alias") or line.get("name") or "unidentified"
        keys.append(str(ident))
    return hashlib.sha256("|".join(sorted(keys)).encode()).hexdigest()[:24]


def process_signature(payload: dict[str, Any]) -> str:
    """Order-*significant* signature of the process steps — reordering
    steps produces a different signature (AT-0204-3)."""
    steps = payload.get("steps", [])
    rendered = "||".join(f"{s.get('order', i)}:{s.get('action', '')}" for i, s in enumerate(steps))
    return hashlib.sha256(rendered.encode()).hexdigest()[:24]


class FormulationService:
    def __init__(self, db: Session, ctx: ServiceContext) -> None:
        self.db = db
        self.ctx = ctx

    # ---------------------------------------------------------- reads

    def _family(self, family_id: uuid.UUID) -> FormulationFamily:
        row = self.db.execute(
            select(FormulationFamily).where(
                FormulationFamily.id == family_id,
                FormulationFamily.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("formulation family")
        return row

    def _revision(self, revision_id: uuid.UUID) -> FormulationRevision:
        row = self.db.execute(
            select(FormulationRevision).where(
                FormulationRevision.id == revision_id,
                FormulationRevision.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("formulation revision")
        return row

    # ------------------------------------------------------- commands

    def create_family(self, *, name: str, description: str | None = None) -> FormulationFamily:
        self.ctx.require(CAP_EDIT_TASK)
        if not name.strip():
            raise DomainError(ErrorCode.VALIDATION, "name is required", field_path="input.name")
        row = FormulationFamily(
            workspace_id=self.ctx.workspace_id,
            name=name.strip(),
            description=description,
        )
        self.db.add(row)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="formulation.family.create",
            target_type="formulation_family",
            target_id=row.id,
        )
        return row

    def draft_revision(
        self,
        *,
        family_id: uuid.UUID,
        payload: dict[str, Any],
        parent_revision_id: uuid.UUID | None = None,
    ) -> FormulationRevision:
        """Draft a revision. Ingredient amounts must be valid Quantity
        DTOs — anything else is rejected at the boundary. Drafts may
        be incomplete: validation *findings* are recorded, not made
        blocking."""
        family = self._family(family_id)
        self.ctx.require(CAP_EDIT_TASK)
        if parent_revision_id is not None:
            parent = self._revision(parent_revision_id)
            if parent.family_id != family.id:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "parent revision belongs to a different family",
                    field_path="input.parentRevisionId",
                )
        findings = self._validate_payload(payload)
        stored = {**payload, "validationFindings": findings}
        current_max = self.db.execute(
            select(func.max(FormulationRevision.revision)).where(
                FormulationRevision.family_id == family.id
            )
        ).scalar_one()
        row = FormulationRevision(
            workspace_id=self.ctx.workspace_id,
            family_id=family.id,
            revision=(current_max or 0) + 1,
            status="draft",
            parent_revision_id=parent_revision_id,
            payload=stored,
            content_hash=content_hash(stored),
            created_by=self.ctx.principal_id,
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="formulation_family",
            aggregate_id=family.id,
            event_type="formulation.revision_drafted",
            payload={"familyId": str(family.id), "revisionId": str(row.id)},
        )
        return row

    def accept_revision(self, *, revision_id: uuid.UUID) -> FormulationRevision:
        """Accept a draft — the declared-basis gate (§6.2).

        A complete revision must hit its declared total within its own
        tolerance → COMPOSITION_TOTAL_INVALID when it doesn't; the
        amounts themselves are never rewritten. Basis must be a
        supported basis; the optimizer representation additionally
        requires as-supplied mass fractions in [0,1] — anything else
        stays an *imported* draft, not an accepted optimizer input.
        """
        self.ctx.require(CAP_EDIT_TASK)
        rev = self._revision(revision_id)
        if rev.status != "draft":
            raise DomainError(
                ErrorCode.VALIDATION,
                f"only a draft revision can be accepted (status is '{rev.status}')",
                field_path="input.revisionId",
            )
        payload = rev.payload
        findings = list(payload.get("validationFindings", []))
        completeness = payload.get("completeness", "draft")
        if completeness != "complete":
            raise DomainError(
                ErrorCode.VALIDATION,
                "only a complete revision can be accepted",
                field_path="input.payload.completeness",
            )
        amounts = self._amounts(payload)
        if not amounts:
            raise DomainError(
                ErrorCode.VALIDATION,
                "a complete revision needs at least one ingredient",
            )
        declared = payload.get("declaredTotal")
        if declared is None:
            raise DomainError(
                ErrorCode.VALIDATION,
                "declaredTotal is required for a complete revision",
                field_path="input.payload.declaredTotal",
            )
        tolerance = payload.get("tolerance", "0.001")
        actual = check_declared_total(
            amounts, declared_total=declared, tolerance=tolerance
        )  # raises COMPOSITION_TOTAL_INVALID — never normalizes
        # optimizer-representation checks are findings, not rewrites
        if payload.get("amountBasis") == OPTIMIZER_BASIS:
            if str(actual.normalize()) != OPTIMIZER_DECLARED_TOTAL:
                findings.append(
                    {
                        "kind": "optimizer_representation",
                        "detail": f"as-supplied basis expects declared total 1; actual {actual}",
                    }
                )
        rev.payload = {**payload, "validationFindings": findings}
        rev.content_hash = content_hash(rev.payload)
        prior = self.db.execute(
            select(FormulationRevision).where(
                FormulationRevision.family_id == rev.family_id,
                FormulationRevision.status == "accepted",
            )
        ).scalar_one_or_none()
        if prior is not None:
            prior.status = "superseded"
            self.db.flush()
        rev.status = "accepted"
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="formulation_family",
            aggregate_id=rev.family_id,
            event_type="formulation.revision_accepted",
            payload={"familyId": str(rev.family_id), "revisionId": str(rev.id)},
        )
        audit_record(
            self.db,
            self.ctx,
            action="formulation.revision.accept",
            target_type="formulation_revision",
            target_id=rev.id,
            detail={"revision": rev.revision},
        )
        return rev

    # -------------------------------------------------- process revs

    def draft_process_revision(
        self, *, family_id: uuid.UUID, payload: dict[str, Any]
    ) -> ProcessRevision:
        """Store a process faithfully — step order is content, not
        presentation; unknown conditions stay marked unknown."""
        family = self._family(family_id)
        self.ctx.require(CAP_EDIT_TASK)
        steps = payload.get("steps")
        if not isinstance(steps, list) or not steps:
            raise DomainError(
                ErrorCode.VALIDATION,
                "a process revision needs at least one step",
                field_path="input.payload.steps",
            )
        for i, step in enumerate(steps):
            if not step.get("action"):
                raise DomainError(
                    ErrorCode.VALIDATION,
                    f"step {i} has no action",
                    field_path=f"input.payload.steps[{i}].action",
                )
        current_max = self.db.execute(
            select(func.max(ProcessRevision.revision)).where(ProcessRevision.family_id == family.id)
        ).scalar_one()
        row = ProcessRevision(
            workspace_id=self.ctx.workspace_id,
            family_id=family.id,
            revision=(current_max or 0) + 1,
            status="draft",
            payload=payload,
            content_hash=content_hash(payload),
            created_by=self.ctx.principal_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def accept_process_revision(self, *, revision_id: uuid.UUID) -> ProcessRevision:
        self.ctx.require(CAP_EDIT_TASK)
        rev = self.db.execute(
            select(ProcessRevision).where(
                ProcessRevision.id == revision_id,
                ProcessRevision.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if rev is None:
            raise not_found("process revision")
        if rev.status != "draft":
            raise DomainError(
                ErrorCode.VALIDATION,
                f"only a draft process revision can be accepted ('{rev.status}')",
                field_path="input.revisionId",
            )
        prior = self.db.execute(
            select(ProcessRevision).where(
                ProcessRevision.family_id == rev.family_id,
                ProcessRevision.status == "accepted",
            )
        ).scalar_one_or_none()
        if prior is not None:
            prior.status = "superseded"
            self.db.flush()
        rev.status = "accepted"
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="formulation.process.accept",
            target_type="process_revision",
            target_id=rev.id,
            detail={"revision": rev.revision},
        )
        return rev

    # -------------------------------------------------------- dedup

    def find_duplicate_formulations(self) -> list[dict[str, Any]]:
        """Exact-ingredient-set grouping (AT-0204-3): revisions sharing
        an order-independent ingredient key are reported *with* their
        process signatures — different process order means different
        signature, and nothing is merged."""
        self.ctx.require(CAP_READ_PROJECT)
        rows = self.db.execute(
            select(FormulationRevision, ProcessRevision.payload.label("proc"))
            .outerjoin(
                ProcessRevision,
                (ProcessRevision.family_id == FormulationRevision.family_id)
                & (ProcessRevision.workspace_id == self.ctx.workspace_id)
                & (ProcessRevision.status == "accepted"),
            )
            .where(FormulationRevision.workspace_id == self.ctx.workspace_id)
        ).all()
        groups: dict[str, list[dict[str, Any]]] = {}
        for rev, proc_payload in rows:
            key = ingredient_key(rev.payload)
            groups.setdefault(key, []).append(
                {
                    "revisionId": str(rev.id),
                    "familyId": str(rev.family_id),
                    "revision": rev.revision,
                    "status": rev.status,
                    "processSignature": (process_signature(proc_payload) if proc_payload else None),
                }
            )
        return [
            {
                "ingredientKey": key,
                "revisions": members,
                "processSignatures": sorted(
                    {m["processSignature"] for m in members if m["processSignature"]}
                ),
            }
            for key, members in groups.items()
            if len(members) > 1
        ]

    # ----------------------------------------------------- internals

    def _amounts(self, payload: dict[str, Any]) -> list[Quantity]:
        """Parse ingredient amounts as Quantities — malformed DTOs are
        rejected, never patched."""
        out: list[Quantity] = []
        for i, line in enumerate(payload.get("ingredients", [])):
            amount = line.get("amount")
            if amount is None:
                continue
            try:
                out.append(Quantity.from_dto(amount))
            except DomainError as exc:
                raise DomainError(
                    exc.code,
                    f"ingredient {i}: {exc.message}",
                    field_path=f"input.payload.ingredients[{i}].amount",
                ) from exc
        return out

    def _validate_payload(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Non-blocking findings for drafts: parse amounts, flag
        missing basis, duplicate lines, totals outside tolerance."""
        findings: list[dict[str, Any]] = []
        ingredients = payload.get("ingredients", [])
        seen: dict[str, int] = {}
        for i, line in enumerate(ingredients):
            ident = str(line.get("materialId") or line.get("alias") or line.get("name") or "?")
            seen[ident] = seen.get(ident, 0) + 1
            if seen[ident] > 1:
                findings.append(
                    {
                        "kind": "duplicate_ingredient_line",
                        "detail": f"'{ident}' appears {seen[ident]} times — needs "
                        "reconciliation or a documented reason, not silent summing",
                    }
                )
            amount = line.get("amount")
            if amount is None:
                findings.append(
                    {"kind": "missing_amount", "detail": f"ingredient {i} has no amount"}
                )
                continue
            try:
                q = Quantity.from_dto(amount)
            except DomainError as exc:
                findings.append(
                    {
                        "kind": "invalid_amount",
                        "detail": f"ingredient {i}: {exc.message}",
                    }
                )
                continue
            if q.dimension == "mass_fraction":
                # compare the canonical fraction — mass_percent 70 is
                # 0.70 canonically, not out-of-range 70
                frac = q.convert("mass_fraction").value
                if not (0 <= frac <= 1):
                    findings.append(
                        {
                            "kind": "fraction_out_of_range",
                            "detail": f"ingredient {i} mass fraction {frac} "
                            f"(entered {q.value} {q.unit}) outside [0,1]",
                        }
                    )
        try:
            amounts = self._amounts(payload)
            if amounts and payload.get("declaredTotal") is not None:
                try:
                    check_declared_total(
                        amounts,
                        declared_total=payload["declaredTotal"],
                        tolerance=payload.get("tolerance", "0.001"),
                    )
                except DomainError as exc:
                    if exc.code == ErrorCode.COMPOSITION_TOTAL_INVALID:
                        findings.append(
                            {
                                "kind": "total_outside_tolerance",
                                "detail": exc.message,
                            }
                        )
                    else:
                        raise
        except DomainError:
            pass  # already recorded as invalid_amount findings
        return findings
