"""Minimal transformed export payload + disclosure review (§20.2-20.3, CS-1002).

Pipeline order (fixed, versioned):

1. select minimum permitted records — frozen snapshot manifest entries
   only: excluded records skipped, unresolved training/export rights
   skipped, missing/drifted sources refused before any transform.
2. transform explicitly — per-kind field allowlists (everything else is
   reported as removed), metadata/hidden keys stripped, direct names
   replaced by tokens from a LOCAL-ONLY alias map, every kept string
   scanned for leftover identifiers, secret-shaped values, structure
   notation, and compositional/process content.
3. report honestly — a redaction report (what was removed and why) and
   a residual-disclosure report (what still leaks: ratios, structures,
   process windows, outcomes, free text, metadata, derived features).
   A scanner flags risk; it can never certify all trade secrets are
   removed, so neither the payload nor the reports are ever labelled
   ``anonymous`` or ``safe`` (AT-1002-1). Hidden sensitive fields are
   flagged or excluded and stay reviewable (AT-1002-2).
4. bind — a §20.2 manifest (source/derived hashes, transformation
   version, payload fields, redaction report, classification,
   recipient/account/region, environment, permitted job, limits,
   retention/deletion, expiry, approver) reduces to ``bound_inputs``;
   its ``bound_digest`` is what an approval binds. Any change —
   including a transformation-version bump — invalidates a reused
   approval (AT-1002-3). Transfers stay inert: nothing outbound, ever.
"""

from __future__ import annotations

import base64
import hashlib
import platform
import re
import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from chem_studio_policy.capabilities import CAP_APPROVE_EXPORT, CAP_REVIEW_EXPORT
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.application.approvals import bound_digest, grant, require_valid
from studio.application.idempotency import canonical_json
from studio.audit.log import record as audit_record
from studio.auth.context import ServiceContext
from studio.domain.learning.datasets import DatasetService
from studio.domain.provenance import (
    ORIGIN_UNKNOWN,
    claim_origin,
    claim_source_resolvable,
    measurement_chain,
    measurement_origin,
    session_origin,
)
from studio.domain.runs.feasibility import cloud_capability
from studio.errors import DomainError, ErrorCode
from studio.persistence.models import (
    Approval,
    Artifact,
    DatasetSnapshot,
    EvidenceClaim,
    ExportProposal,
    ExportTransformedPayload,
    ExtractedRecord,
    FormulationFamily,
    ImportBatch,
    LabBatch,
    LabSample,
    MaterialGrade,
    MaterialIdentity,
    Measurement,
    Principal,
    ResearchSession,
    Run,
    SessionMessage,
)

TRANSFORM_VERSION = "export-transform/v1"
PAYLOAD_VERSION = "export-payload/v1"
MANIFEST_VERSION = "export-manifest/v1"

# Bounded inputs — a transform request is itself a bounded document.
MAX_RECORDS = 2000
MAX_PAYLOAD_BYTES = 4 * 1024 * 1024
MAX_ALIASES = 5000
MAX_NAME_LEN = 200
MAX_DECLARED_TEXT = 120
MAX_STRING = 20_000
MAX_LIST = 500
MAX_DEPTH = 24
MAX_SNAPSHOT_PICKER = 100

CLASSIFICATIONS = ("internal", "confidential", "restricted")
_CLASS_RANK = {c: i for i, c in enumerate(CLASSIFICATIONS)}
_EXPORT_OK = {"allowed", "owned"}
_PROPOSAL_OPEN = {"proposed", "approved"}

# Per-record-kind removed fields reported in the redaction report —
# the allowlist is the literal field set each builder emits.
_MEASUREMENT_REMOVED = ("id", "sample", "applicable", "status", "supersededBy")
_CLAIM_REMOVED = ("id", "status", "artifact", "extractedRecord")
_SESSION_REMOVED = ("id", "task", "status", "messageIds", "refs", "actors")

# Keys stripped recursively inside kept values. Normalized lowercase
# comparison; suffixes catch prefixed variants (api_key, created_by…).
_METADATA_KEYS = {
    "id",
    "ids",
    "uuid",
    "guid",
    "ref",
    "refs",
    "name",
    "names",
    "label",
    "labels",
    "title",
    "caption",
    "path",
    "paths",
    "file",
    "files",
    "filename",
    "filepath",
    "folder",
    "directory",
    "url",
    "urls",
    "uri",
    "uris",
    "host",
    "hostname",
    "ip",
    "endpoint",
    "login",
    "logins",
    "email",
    "emails",
    "phone",
    "phones",
    "address",
    "addresses",
    "secret",
    "secrets",
    "password",
    "passwords",
    "token",
    "tokens",
    "apikey",
    "credential",
    "credentials",
    "note",
    "notes",
    "comment",
    "comments",
    "remark",
    "remarks",
    "principal",
    "principals",
    "user",
    "users",
    "owner",
    "owners",
    "operator",
    "operators",
    "author",
    "authors",
    "creator",
    "creators",
    "reviewer",
    "reviewers",
    "approver",
    "source",
    "sources",
    "locator",
    "locators",
    "artifact",
    "artifacts",
    "storage",
    "batch",
    "batches",
    "sample",
    "samples",
    "workspace",
    "project",
    "projects",
    "task",
    "tasks",
}
_METADATA_SUFFIXES = (
    "_id",
    "_ids",
    "_by",
    "_at",
    "_key",
    "_uuid",
    "_ref",
    "_name",
    "_label",
    "_path",
    "_file",
    "_url",
    "_uri",
    "_email",
    "_note",
    "_hash",
    "_digest",
    "_token",
    "_secret",
    "_login",
)

# Residual-content detectors. These never remove anything — they make
# the remaining disclosure explicit in the report.
_PROCESS_KEYS = {
    "temperature",
    "temp",
    "time",
    "duration",
    "pressure",
    "rpm",
    "ph",
    "stir",
    "stirring",
    "agitation",
    "cure",
    "bake",
    "anneal",
    "hold",
    "ramp",
    "rate",
    "speed",
    "humidity",
    "vacuum",
    "dwell",
    "soak",
    "cool",
    "heat",
    "flow",
    "sinter",
    "reflux",
    "drying",
}
_RATIO_KEYS = {
    "ratio",
    "ratios",
    "fraction",
    "fractions",
    "percent",
    "percentage",
    "proportion",
    "proportions",
    "content",
    "concentration",
    "loading",
    "purity",
    "composition",
    "ppm",
    "ppb",
    "wt_pct",
    "mol_pct",
    "vol_pct",
    "weight_fraction",
    "mol_fraction",
    "mass_fraction",
    "share",
    "basis_points",
}
_DERIVED_KEYS = {
    "spectra",
    "spectrum",
    "peaks",
    "peak",
    "wavelength",
    "wavelengths",
    "descriptor",
    "descriptors",
    "fingerprint",
    "fingerprints",
    "embedding",
    "embeddings",
    "feature",
    "features",
    "score",
    "scores",
    "signature",
    "checksum",
    "sha256",
}

# Suspicious-content patterns — matched against *aliased* text so only
# leaks that survived replacement are reported.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL = re.compile(r"(?:https?://|www\.)[^\s<>'\"]+", re.IGNORECASE)
_FS_PATH = re.compile(r"(?:/[A-Za-z0-9._~+-]+){2,}|(?:[A-Za-z]:\\[^\s'\"]+)|(?:~[/\\][^\s'\"]+)")
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_SECRETISH = re.compile(
    r"BEGIN [A-Z ]*PRIVATE KEY(?:[^\n]*END [A-Z ]*PRIVATE KEY)?"
    r"|password\s*[:=]\s*\S+"
    r"|passwd\s*[:=]\s*\S+"
    r"|api[_-]?key\s*[:=]\s*\S+"
    r"|secret\s*[:=]\s*\S+"
    r"|token\s*[:=]\s*\S+"
    r"|bearer\s+\S+",
    re.IGNORECASE,
)
_SHA256_BLOB = re.compile(r"\b[0-9a-f]{64}\b")
_INCHI = re.compile(r"\bInChI=1S?/[^\s]+")
# A permissive SMILES-ish heuristic: long-ish atom/bond token run.
_SMILESISH = re.compile(r"^[A-Za-z0-9@+\-\[\]()=#%\\/.$]{10,}$")

_FLAG_PATTERNS = (
    ("email", _EMAIL, "high"),
    ("url", _URL, "medium"),
    ("filesystem_path", _FS_PATH, "medium"),
    ("uuid", _UUID, "medium"),
    ("secret_value", _SECRETISH, "high"),
    ("hash_blob", _SHA256_BLOB, "medium"),
)


def _looks_like_structure(token: str) -> bool:
    if _INCHI.search(token):
        return True
    if len(token) > 160 or not _SMILESISH.match(token):
        return False
    specials = sum(token.count(c) for c in "()[]=#@/\\")
    return specials >= 2


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return None


class _Scan:
    """Mutable transform state: the LOCAL alias map plus report
    collectors. ``map`` never leaves the vault — it is stored on the
    persistence row's ``local_alias_map`` only."""

    _PREFIXES: ClassVar[dict[str, str]] = {
        "metric": "m",
        "artifact": "a",
        "material": "mat",
        "lab": "lab",
        "principal": "p",
        "formulation": "f",
    }

    def __init__(self) -> None:
        self.map: dict[str, dict[str, str]] = {}
        self._by_orig: dict[str, str] = {}
        self._count_by_kind: dict[str, int] = {}
        self.flags: list[dict[str, Any]] = []
        self.removed_keys: list[dict[str, Any]] = []
        self.residuals: dict[str, list[dict[str, Any]]] = {
            "ratios": [],
            "structures": [],
            "process_windows": [],
            "outcomes": [],
            "free_text": [],
            "derived_features": [],
        }

    # ---------------------------------------------------- aliasing

    def alias(self, kind: str, original: str | None) -> str | None:
        """Return the token for ``original`` (or the input unchanged
        when it cannot carry an identifier)."""
        if not isinstance(original, str):
            return original
        if len(original) < 3 or len(original) > MAX_NAME_LEN:
            return original
        token = self._by_orig.get(original)
        if token is None:
            if len(self.map) >= MAX_ALIASES:
                return original
            n = self._count_by_kind.get(kind, 0) + 1
            self._count_by_kind[kind] = n
            token = f"{self._PREFIXES.get(kind, 'x')}-{n:04d}"
            self._by_orig[original] = token
            self.map[token] = {"kind": kind, "original": original}
        return token

    def replace(self, text: str) -> str:
        """Substitute known identifiers — longest first so a name that
        prefixes another is handled correctly."""
        for orig in sorted(self._by_orig, key=len, reverse=True):
            if orig in text:
                text = text.replace(orig, self._by_orig[orig])
        return text

    # ---------------------------------------------------- scanning

    def text(self, s: str, *, path: str, ref: str) -> str:
        if len(s) > MAX_STRING:
            self.flag(ref, path, "oversize_string", "medium")
            s = s[:MAX_STRING]
        s = self.replace(s)
        for name, pattern, severity in _FLAG_PATTERNS:
            if not pattern.search(s):
                continue
            # High-severity leaks (emails, secrets) are redacted from
            # the payload AND flagged; medium ones are flagged for
            # review but kept — the reviewer sees the exact payload
            # either way.
            redacted = severity == "high"
            self.flag(ref, path, name, severity, redacted=redacted)
            if redacted:
                s = pattern.sub(f"[redacted:{name}]", s)
        # Structure notation is a residual disclosure, not a flag.
        if any(_looks_like_structure(tok) for tok in s.split()):
            self.residuals["structures"].append(
                {"ref": ref, "path": path, "detail": "structure notation retained"}
            )
        return s

    def flag(
        self, ref: str, path: str, pattern: str, severity: str, *, redacted: bool = False
    ) -> None:
        self.flags.append(
            {
                "ref": ref,
                "path": path,
                "pattern": pattern,
                "severity": severity,
                "redacted": redacted,
            }
        )

    def filter(self, node: Any, *, path: str, ref: str, depth: int = 0) -> Any:
        """Denylist metadata keys + scan kept values, recursively."""
        if depth > MAX_DEPTH:
            self.flag(ref, path, "max_depth", "medium")
            return None
        if isinstance(node, dict):
            out: dict[str, Any] = {}
            for k, v in node.items():
                key = str(k)
                norm = key.strip().lower()
                if norm in _METADATA_KEYS or norm.endswith(_METADATA_SUFFIXES):
                    self.removed_keys.append(
                        {
                            "ref": ref,
                            "path": f"{path}.{key}" if path else key,
                            "key": key,
                            "reason": "metadata_key",
                        }
                    )
                    continue
                out[key] = self.filter(v, path=f"{path}.{key}", ref=ref, depth=depth + 1)
            self.detect_dict_residuals(out, path=path, ref=ref)
            return out
        if isinstance(node, list):
            if len(node) > MAX_LIST:
                self.flag(ref, path, "oversize_list", "medium")
                node = node[:MAX_LIST]
            return [
                self.filter(v, path=f"{path}[{i}]", ref=ref, depth=depth + 1)
                for i, v in enumerate(node)
            ]
        if isinstance(node, str):
            return self.text(node, path=path, ref=ref)
        if isinstance(node, (int, float, bool)) or node is None:
            return node
        # bytes / exotic types are dropped and reported.
        self.removed_keys.append(
            {"ref": ref, "path": path, "key": None, "reason": "unsupported_type"}
        )
        return None

    def detect_dict_residuals(self, node: dict[str, Any], *, path: str, ref: str) -> None:
        keys = {str(k).strip().lower() for k in node}
        proc = sorted(keys & _PROCESS_KEYS)
        if proc:
            self.residuals["process_windows"].append({"ref": ref, "path": path, "keys": proc})
        der = sorted(keys & _DERIVED_KEYS)
        if der:
            self.residuals["derived_features"].append({"ref": ref, "path": path, "keys": der})
        numeric = [_num(v) for v in node.values()]
        vals = [v for v in numeric if v is not None]
        ratio_keys = sorted(keys & _RATIO_KEYS)
        unit_hit = any(
            str(node[k]).strip().endswith(("%", "ppm", "ppb"))
            for k in node
            if str(k).strip().lower() in ("unit", "basis")
        )
        if ratio_keys or unit_hit or self._looks_compositional(vals):
            self.residuals["ratios"].append(
                {
                    "ref": ref,
                    "path": path,
                    "keys": ratio_keys,
                    "detail": "compositional/ratio fields retained",
                }
            )

    @staticmethod
    def _looks_compositional(vals: list[float]) -> bool:
        if len(vals) < 2:
            return False
        total = sum(vals)
        return abs(total - 100.0) <= 1.5 or abs(total - 1.0) <= 0.02


def _digest(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def _gid(type_name: str, node_id: str) -> str:
    """Relay GlobalID wire format (TypeName:node_id, base64) — emitted
    inside the view so the API layer never imports strawberry."""
    return base64.b64encode(f"{type_name}:{node_id}".encode()).decode()


def _field_paths(node: Any, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            paths.update(_field_paths(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(node, list):
        for v in node:
            paths.update(_field_paths(v, prefix))
    else:
        paths.add(prefix)
    return paths


def _declared(text: str | None, field: str) -> str | None:
    """Optional manifest free text (recipient/account/region/…) — a
    declared label, bounded; never a credential or endpoint."""
    if text is None:
        return None
    text = str(text).strip()
    if not text:
        return None
    if len(text) > MAX_DECLARED_TEXT:
        raise DomainError(
            ErrorCode.VALIDATION,
            f"{field} exceeds {MAX_DECLARED_TEXT} characters",
            field_path=field,
        )
    return text


class TransformService:
    """Prepare + review minimal transformed payloads (CS-1002)."""

    def __init__(self, db: Session, ctx: ServiceContext):
        self.db = db
        self.ctx = ctx

    # -------------------------------------------------------- helpers

    def _proposal(self, proposal_id: uuid.UUID) -> ExportProposal:
        row = self.db.execute(
            select(ExportProposal).where(
                ExportProposal.id == proposal_id,
                ExportProposal.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, "export proposal not found")
        return row

    def payload(self, payload_id: uuid.UUID) -> ExportTransformedPayload:
        """Workspace-scoped fetch for callers that already know the id
        (e.g. the mutation layer re-loading a row post-commit)."""
        return self._payload(payload_id)

    def _payload(self, payload_id: uuid.UUID) -> ExportTransformedPayload:
        row = self.db.execute(
            select(ExportTransformedPayload).where(
                ExportTransformedPayload.id == payload_id,
                ExportTransformedPayload.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, "export payload not found")
        return row

    def latest_payload(self, proposal_id: uuid.UUID) -> ExportTransformedPayload | None:
        return self.db.execute(
            select(ExportTransformedPayload)
            .where(
                ExportTransformedPayload.workspace_id == self.ctx.workspace_id,
                ExportTransformedPayload.proposal_id == proposal_id,
            )
            .order_by(ExportTransformedPayload.seq.desc())
            .limit(1)
        ).scalar_one_or_none()

    # ---------------------------------------------------- collection

    def _alias_candidates(self) -> list[tuple[str, str]]:
        """Workspace names that could appear inside kept text — bounded,
        deterministic order. The map itself never enters the payload."""
        ws = self.ctx.workspace_id
        out: list[tuple[str, str]] = []

        def add(kind: str, value: Any) -> None:
            if isinstance(value, str) and 3 <= len(value) <= MAX_NAME_LEN:
                out.append((kind, value))

        for a in self.db.execute(
            select(Artifact).where(Artifact.workspace_id == ws).limit(MAX_ALIASES)
        ).scalars():
            add("artifact", a.original_name)
        for m in self.db.execute(
            select(MaterialIdentity).where(MaterialIdentity.workspace_id == ws).limit(MAX_ALIASES)
        ).scalars():
            add("material", m.name)
            for ident in m.identifiers or []:
                if isinstance(ident, dict):
                    add("material", ident.get("value"))
            for alias in m.aliases or []:
                # Alias proposals are dicts ({name, …}); tolerate plain
                # strings too.
                if isinstance(alias, dict):
                    add("material", alias.get("name") or alias.get("value"))
                else:
                    add("material", alias)
        for g in self.db.execute(
            select(MaterialGrade).where(MaterialGrade.workspace_id == ws).limit(MAX_ALIASES)
        ).scalars():
            add("material", g.supplier)
            add("material", g.grade_name)
        for f in self.db.execute(
            select(FormulationFamily).where(FormulationFamily.workspace_id == ws).limit(MAX_ALIASES)
        ).scalars():
            add("formulation", f.name)
        for s in self.db.execute(
            select(LabSample).where(LabSample.workspace_id == ws).limit(MAX_ALIASES)
        ).scalars():
            add("lab", s.label)
        for b in self.db.execute(
            select(LabBatch).where(LabBatch.workspace_id == ws).limit(MAX_ALIASES)
        ).scalars():
            add("lab", b.label)
        for p in self.db.execute(
            select(Principal).where(Principal.workspace_id == ws).limit(MAX_ALIASES)
        ).scalars():
            add("principal", p.login)
            add("principal", p.display_name)
        out.sort(key=lambda t: (t[0], t[1]))
        return out[:MAX_ALIASES]

    def _claim_artifact(self, claim: EvidenceClaim) -> Artifact | None:
        if not claim.source_record_id:
            return None
        rec = self.db.get(ExtractedRecord, claim.source_record_id)
        if rec is None:
            return None
        batch = self.db.get(ImportBatch, rec.batch_id)
        if batch is None:
            return None
        return self.db.get(Artifact, batch.artifact_id)

    def _source_classification(self, entries: list[dict[str, Any]]) -> str:
        """Highest artifact classification among claim sources; claims
        without a resolved artifact default to 'restricted' (a claim's
        provenance is not self-evident). Local records are 'internal'."""
        worst = 0
        for e in entries:
            if e["recordKind"] != "claim" or e["excluded"]:
                continue
            claim = self.db.get(EvidenceClaim, uuid.UUID(str(e["recordId"])))
            if claim is None:
                continue
            artifact = self._claim_artifact(claim)
            cls = (artifact.classification if artifact else "restricted") or "restricted"
            worst = max(worst, _CLASS_RANK.get(cls, 2))
        return CLASSIFICATIONS[worst]

    def _measurement_fields(self, m: Measurement, scan: _Scan, ref: str) -> dict[str, Any]:
        metric = scan.alias("metric", m.metric) or m.metric
        return {
            "metric": metric,
            "method": scan.filter(m.method, path="method", ref=ref),
            "valueType": m.value_type,
            "value": scan.filter(m.value, path="value", ref=ref),
            "conditions": scan.filter(m.conditions, path="conditions", ref=ref),
        }

    def _claim_fields(
        self, c: EvidenceClaim, entry: dict[str, Any], scan: _Scan, ref: str
    ) -> dict[str, Any]:
        fields = {
            "sourceClass": c.kind,
            "labelKind": entry.get("labelKind") or "claimed_value",
            "subject": scan.filter(c.subject, path="subject", ref=ref),
            "statement": scan.filter(c.statement, path="statement", ref=ref),
            "conditions": scan.filter(c.conditions or {}, path="conditions", ref=ref),
        }
        scan.residuals["free_text"].append(
            {"ref": ref, "fields": ["subject", "statement"], "detail": "free text retained"}
        )
        return fields

    def _session_fields(self, s: ResearchSession, scan: _Scan, ref: str) -> dict[str, Any]:
        messages = (
            self.db.execute(
                select(SessionMessage)
                .where(SessionMessage.session_id == s.id)
                .order_by(SessionMessage.created_at, SessionMessage.id)
                .limit(MAX_LIST)
            )
            .scalars()
            .all()
        )
        fields = {
            "messages": [
                {
                    "role": m.role,
                    "content": scan.filter(m.content, path=f"messages[{i}].content", ref=ref),
                }
                for i, m in enumerate(messages)
            ]
        }
        scan.residuals["free_text"].append(
            {"ref": ref, "fields": ["messages.content"], "detail": "session text retained"}
        )
        return fields

    def _collect(
        self,
        snap: DatasetSnapshot,
        scan: _Scan,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        """Transform permitted entries → payload records. Returns
        (records, excludedEntries, mergedCount)."""
        ws = self.ctx.workspace_id
        records: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        seen: dict[str, int] = {}
        merged = 0
        for i, e in enumerate(snap.manifest["entries"]):
            rid = str(e["recordId"])
            kind = str(e["recordKind"])
            if e["excluded"]:
                excluded.append(
                    {"recordId": rid, "recordKind": kind, "reason": e.get("exclusionReason")}
                )
                continue
            if e["rightsTraining"] not in _EXPORT_OK:
                excluded.append(
                    {"recordId": rid, "recordKind": kind, "reason": "rights_unresolved"}
                )
                continue
            # Ref tracks the manifest position — stable across rebuilds
            # and unique even when entries are skipped or merged.
            ref = f"r-{i:04d}"
            # PAR-05: provenance rides on the record envelope — a record
            # whose origin cannot be established is excluded at the same
            # plane as unresolved rights. Manifests built before
            # provenance existed (no evidenceOrigin field) are derived
            # live, never trusted silently.
            origin = e.get("evidenceOrigin")
            if kind == "measurement":
                row = self.db.execute(
                    select(Measurement).where(
                        Measurement.id == uuid.UUID(rid), Measurement.workspace_id == ws
                    )
                ).scalar_one_or_none()
                if row is None:
                    excluded.append(
                        {"recordId": rid, "recordKind": kind, "reason": "source_missing"}
                    )
                    continue
                if origin is None:
                    sample, batch, execution, plan = measurement_chain(
                        self.db, ws, row
                    )
                    origin = measurement_origin(
                        row, sample=sample, batch=batch, execution=execution, plan=plan
                    )["origin"]
                fields = self._measurement_fields(row, scan, ref)
                scan.residuals["outcomes"].append(
                    {
                        "ref": ref,
                        "metric": fields["metric"],
                        "valueType": fields["valueType"],
                        "detail": "measured value remains exposed",
                    }
                )
            elif kind == "claim":
                claim = self.db.execute(
                    select(EvidenceClaim).where(
                        EvidenceClaim.id == uuid.UUID(rid), EvidenceClaim.workspace_id == ws
                    )
                ).scalar_one_or_none()
                if claim is None:
                    excluded.append(
                        {"recordId": rid, "recordKind": kind, "reason": "source_missing"}
                    )
                    continue
                if origin is None:
                    origin = claim_origin(
                        claim,
                        source_resolvable=claim_source_resolvable(self.db, claim),
                    )["origin"]
                artifact = self._claim_artifact(claim)
                export_right = (
                    (artifact.rights or {}).get("export", "unknown") if artifact else "unknown"
                )
                if export_right not in _EXPORT_OK:
                    excluded.append(
                        {
                            "recordId": rid,
                            "recordKind": kind,
                            "reason": "export_rights_unresolved",
                        }
                    )
                    continue
                fields = self._claim_fields(claim, e, scan, ref)
            elif kind == "session":
                sess = self.db.execute(
                    select(ResearchSession).where(
                        ResearchSession.id == uuid.UUID(rid), ResearchSession.workspace_id == ws
                    )
                ).scalar_one_or_none()
                if sess is None:
                    excluded.append(
                        {"recordId": rid, "recordKind": kind, "reason": "source_missing"}
                    )
                    continue
                if origin is None:
                    origin = session_origin(sess)["origin"]
                fields = self._session_fields(sess, scan, ref)
            else:
                excluded.append({"recordId": rid, "recordKind": kind, "reason": "unsupported_kind"})
                continue
            if origin == ORIGIN_UNKNOWN:
                excluded.append(
                    {"recordId": rid, "recordKind": kind, "reason": "provenance_unknown"}
                )
                continue
            key = hashlib.sha256(
                canonical_json({"kind": kind, "fields": fields}).encode()
            ).hexdigest()
            if key in seen:
                merged += 1
                continue
            seen[key] = i
            records.append(
                {"ref": ref, "kind": kind, "evidenceOrigin": origin, "fields": fields}
            )
        return records, excluded, merged

    # ---------------------------------------------------- reports

    @staticmethod
    def _redaction_report(
        scan: _Scan, excluded: list[dict[str, Any]], merged: int
    ) -> dict[str, Any]:
        return {
            "version": "redaction-report/v1",
            "removedFields": {
                "measurement": list(_MEASUREMENT_REMOVED),
                "claim": list(_CLAIM_REMOVED),
                "session": list(_SESSION_REMOVED),
            },
            "removedKeys": scan.removed_keys,
            "excludedEntries": excluded,
            "mergedDuplicates": merged,
            "aliasedIdentifiers": {
                "count": len(scan.map),
                "kinds": sorted({v["kind"] for v in scan.map.values()}),
                "localOnly": True,
                "note": "the alias map stays in the local vault — it is never "
                "part of the payload or its digest",
            },
        }

    @staticmethod
    def _residual_report(records: list[dict[str, Any]], scan: _Scan) -> dict[str, Any]:
        flagged = sorted({f["ref"] for f in scan.flags})
        categories: list[dict[str, Any]] = []
        if scan.residuals["outcomes"]:
            categories.append(
                {
                    "kind": "outcomes",
                    "count": len(scan.residuals["outcomes"]),
                    "findings": scan.residuals["outcomes"],
                    "detail": "measured/predicted values remain exposed",
                }
            )
        for kind in ("ratios", "process_windows", "structures", "free_text", "derived_features"):
            findings = scan.residuals[kind]
            if findings:
                categories.append({"kind": kind, "count": len(findings), "findings": findings})
        if records:
            categories.append(
                {
                    "kind": "metadata",
                    "count": len(records),
                    "detail": "record count, ordering, per-record refs, and the field "
                    "selection itself remain exposed",
                }
            )
        return {
            "version": "residual-risk/v1",
            # AT-1002-1: a scanner flags risk; it can never certify that
            # all trade secrets are removed. These stay false forever.
            "verdict": "residual_disclosure",
            "anonymous": False,
            "safe": False,
            "certified": False,
            "categories": categories,
            "flags": scan.flags,
            "flaggedRecords": flagged,
            "advisory": "Masking is not confidentiality. Direct names are aliased, "
            "but ratios, structures, process windows, outcomes, free text and "
            "metadata remain exposed; no scan can certify all trade secrets are "
            "removed.",
        }

    # ---------------------------------------------------- commands

    def prepare(
        self,
        proposal_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        *,
        recipient: str | None = None,
        account: str | None = None,
        region: str | None = None,
        expires_at: datetime | None = None,
        max_records: int | None = None,
        max_bytes: int | None = None,
        retention_expectation: str | None = None,
        deletion_expectation: str | None = None,
        transformation_version: str = TRANSFORM_VERSION,
    ) -> ExportTransformedPayload:
        """Build (or reuse) the minimal transformed payload for review.

        Records come only from a frozen, un-drifted snapshot. Any
        declared recipient/job/limits/expiry are bound into the
        approval digest; nothing here transfers anything."""
        self.ctx.require(CAP_REVIEW_EXPORT)
        proposal = self._proposal(proposal_id)
        if proposal.status not in _PROPOSAL_OPEN:
            raise DomainError(ErrorCode.CONFLICT, f"export proposal is {proposal.status}")
        run = self.db.execute(
            select(Run).where(Run.id == proposal.run_id, Run.workspace_id == self.ctx.workspace_id)
        ).scalar_one()

        datasets = DatasetService(self.db, self.ctx)
        snap = datasets.get(snapshot_id)
        if snap.state != "frozen":
            raise DomainError(ErrorCode.CONFLICT, "snapshot is not frozen")
        drift = datasets.drift_status(snapshot_id)
        if drift["drift"]:
            raise DomainError(
                ErrorCode.CONFLICT,
                "snapshot source drift — refreeze before export",
                safe_details={"changed": drift["changed"], "missing": drift["missing"]},
            )
        if snap.task_id and run.task_id and snap.task_id != run.task_id:
            raise DomainError(
                ErrorCode.VALIDATION,
                "snapshot task does not match the proposed run's task",
                field_path="snapshotId",
            )

        max_records = max_records if max_records is not None else MAX_RECORDS
        max_bytes = max_bytes if max_bytes is not None else MAX_PAYLOAD_BYTES
        if not (1 <= max_records <= MAX_RECORDS) or not (1 <= max_bytes <= MAX_PAYLOAD_BYTES):
            raise DomainError(
                ErrorCode.VALIDATION,
                f"limits must be within {MAX_RECORDS} records / {MAX_PAYLOAD_BYTES} bytes",
            )

        scan = _Scan()
        for kind, name in self._alias_candidates():
            scan.alias(kind, name)
        records, excluded, merged = self._collect(snap, scan)
        if len(records) > max_records:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"payload selects {len(records)} records, above the {max_records} limit",
            )

        payload_doc = {
            "version": PAYLOAD_VERSION,
            "transformationVersion": transformation_version,
            "purpose": snap.purpose,
            "records": records,
            "notes": "transformed review payload — names aliased only; NOT "
            "anonymous or safe (§20.3)",
        }
        payload_digest = _digest(payload_doc)
        byte_size = len(canonical_json(payload_doc).encode())
        if byte_size > max_bytes:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"payload is {byte_size} bytes, above the {max_bytes} limit",
            )
        fields = sorted(_field_paths(payload_doc["records"]))
        classification = self._source_classification(snap.manifest["entries"])
        redaction = self._redaction_report(scan, excluded, merged)
        residual = self._residual_report(records, scan)

        from studio.persistence.models import RunFeasibilityReport

        report = self.db.get(RunFeasibilityReport, proposal.feasibility_report_id)
        operation = report.operation if report else run.kind
        manifest = {
            "version": MANIFEST_VERSION,
            "transformationVersion": transformation_version,
            "proposalId": str(proposal.id),
            "proposalBoundDigest": proposal.bound_digest,
            "snapshot": {
                "id": str(snap.id),
                "digest": snap.digest,
                "purpose": snap.purpose,
                "provenance": (snap.manifest or {}).get("provenance"),
            },
            "payload": {
                "digest": payload_digest,
                "recordCount": len(records),
                "byteSize": byte_size,
                "fields": fields,
            },
            "reports": {
                "redactionDigest": _digest(redaction),
                "residualDigest": _digest(residual),
            },
            "classification": classification,
            "recipient": {
                "provider": _declared(recipient, "recipient"),
                "account": _declared(account, "account"),
                "region": _declared(region, "region"),
            },
            "environment": {
                # No provider or container is configured in this ticket —
                # the runtime digest stays local and honest.
                "containerDigest": None,
                "runtime": {
                    "python": platform.python_version(),
                    "transform": transformation_version,
                },
            },
            "permittedJob": {
                "operation": operation,
                "runKind": run.kind,
                "runId": str(run.id),
            },
            "limits": {"maxRecords": max_records, "maxBytes": max_bytes},
            "retention": {
                "expectation": _declared(retention_expectation, "retentionExpectation"),
                "deletionExpectation": _declared(deletion_expectation, "deletionExpectation"),
            },
            "expiry": expires_at.isoformat() if expires_at else None,
            "approver": None,
            "egress": "deny",
        }
        bound_inputs = {
            "manifestVersion": MANIFEST_VERSION,
            "proposalBoundDigest": proposal.bound_digest,
            "snapshotDigest": snap.digest,
            "payloadDigest": payload_digest,
            "transformationVersion": transformation_version,
            "classification": classification,
            "recipient": manifest["recipient"],
            "permittedJob": manifest["permittedJob"],
            "limits": manifest["limits"],
            "expiry": manifest["expiry"],
        }
        digest = bound_digest(bound_inputs)

        existing = self.db.execute(
            select(ExportTransformedPayload).where(
                ExportTransformedPayload.workspace_id == self.ctx.workspace_id,
                ExportTransformedPayload.bound_digest == digest,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        row = ExportTransformedPayload(
            workspace_id=self.ctx.workspace_id,
            proposal_id=proposal.id,
            snapshot_id=snap.id,
            purpose=snap.purpose,
            transformation_version=transformation_version,
            classification=classification,
            source_classification=classification,
            classification_review=None,
            payload=payload_doc,
            payload_digest=payload_digest,
            payload_fields=fields,
            redaction_report=redaction,
            residual_report=residual,
            manifest=manifest,
            bound_inputs=bound_inputs,
            bound_digest=digest,
            local_alias_map=scan.map,
            created_by=self.ctx.principal_id,
        )
        self.db.add(row)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="export.transform_prepared",
            target_type="export_transformed_payload",
            target_id=row.id,
            detail={
                "proposalId": str(proposal.id),
                "snapshotId": str(snap.id),
                "records": len(records),
                "flagged": len(residual["flaggedRecords"]),
            },
        )
        return row

    def decide(
        self,
        payload_id: uuid.UUID,
        *,
        decision: str,
        rationale: str | None = None,
        ttl_seconds: int | None = None,
    ) -> Approval:
        """Human decision bound to the exact payload+transformation
        digest (§20.2). ``grant`` enforces ``approve_export`` — agents
        can never hold it."""
        row = self._payload(payload_id)
        if decision not in ("approved", "rejected"):
            raise DomainError(ErrorCode.VALIDATION, "decision must be approved|rejected")
        approval = grant(
            self.db,
            self.ctx,
            action="export",
            bound_inputs=row.bound_inputs,
            decision=decision,
            rationale=rationale,
            ttl_seconds=ttl_seconds,
        )
        proposal = self._proposal(row.proposal_id)
        proposal.status = "approved" if decision == "approved" else "rejected"
        audit_record(
            self.db,
            self.ctx,
            action="export.decided",
            target_type="export_transformed_payload",
            target_id=row.id,
            detail={"decision": decision, "boundDigest": row.bound_digest},
        )
        return approval

    def validate_approval(self, payload_id: uuid.UUID) -> Approval:
        """Re-check that a valid approval still binds this exact
        payload+transformation digest — the hook CS-1003 calls before
        any transfer. Raises APPROVAL_STALE when the bound inputs
        changed (AT-1002-3)."""
        row = self._payload(payload_id)
        return require_valid(self.db, self.ctx, action="export", bound_inputs=row.bound_inputs)

    def set_classification(
        self, payload_id: uuid.UUID, *, classification: str, rationale: str
    ) -> ExportTransformedPayload:
        """Reviewed classification change — preserved source value is
        kept, the change is recorded, and the bound digest is rebuilt so
        prior approvals invalidate."""
        self.ctx.require(CAP_REVIEW_EXPORT)
        row = self._payload(payload_id)
        if classification not in CLASSIFICATIONS:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"classification must be one of {CLASSIFICATIONS}",
                field_path="classification",
            )
        if not (rationale or "").strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "a reviewed classification change requires a rationale",
                field_path="rationale",
            )
        if classification == row.classification:
            return row
        row.classification_review = {
            "from": row.classification,
            "to": classification,
            "rationale": rationale.strip(),
            "reviewedBy": str(self.ctx.principal_id),
            "at": datetime.now(UTC).isoformat(),
        }
        row.classification = classification
        # JSONB columns are not mutable-tracked — reassign whole dicts.
        row.manifest = {
            **row.manifest,
            "classification": classification,
            "classificationReview": row.classification_review,
        }
        row.bound_inputs = {**row.bound_inputs, "classification": classification}
        row.bound_digest = bound_digest(row.bound_inputs)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="export.classification_reviewed",
            target_type="export_transformed_payload",
            target_id=row.id,
            detail={"classification": classification},
        )
        return row

    # ---------------------------------------------------- queries

    def _approval_state(self, row: ExportTransformedPayload) -> dict[str, Any]:
        """Non-mutating mirror of ``require_valid`` for the review view —
        approvals for OTHER proposals must not leak into this state, so
        candidates are scoped by the bound proposal digest."""
        candidates = (
            self.db.execute(
                select(Approval)
                .where(
                    Approval.workspace_id == self.ctx.workspace_id,
                    Approval.action == "export",
                )
                .order_by(Approval.created_at.desc(), Approval.id.desc())
                .limit(50)
            )
            .scalars()
            .all()
        )
        proposal_digest = row.bound_inputs.get("proposalBoundDigest")
        candidates = [
            a
            for a in candidates
            if (a.bound_inputs or {}).get("proposalBoundDigest") == proposal_digest
        ]

        def _view(a: Approval, state: str) -> dict[str, Any]:
            return {
                "state": state,
                "decision": a.decision,
                "decidedBy": str(a.decided_by),
                "boundDigest": a.bound_digest,
                "expiresAt": a.expires_at.isoformat() if a.expires_at else None,
                "rationale": a.rationale,
            }

        approval = next(
            (
                a
                for a in candidates
                if a.decision == "approved" and a.bound_digest == row.bound_digest
            ),
            None,
        )
        newest = candidates[0] if candidates else None
        if approval is None:
            if newest is None:
                return {"state": "none"}
            if newest.decision != "approved":
                return _view(newest, "rejected")
            if newest.bound_digest != row.bound_digest:
                return _view(newest, "stale")
            approval = newest
        if approval.revoked_at is not None:
            return _view(approval, "revoked")
        expires = approval.expires_at
        if expires is not None:
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires <= datetime.now(UTC):
                return _view(approval, "expired")
        return _view(approval, "approved")

    def review_view(self, proposal_id: uuid.UUID) -> dict[str, Any]:
        self.ctx.require(CAP_REVIEW_EXPORT)
        proposal = self._proposal(proposal_id)
        run = self.db.execute(
            select(Run).where(Run.id == proposal.run_id, Run.workspace_id == self.ctx.workspace_id)
        ).scalar_one()
        row = self.latest_payload(proposal_id)
        snapshots = (
            self.db.execute(
                select(DatasetSnapshot)
                .where(
                    DatasetSnapshot.workspace_id == self.ctx.workspace_id,
                    DatasetSnapshot.state == "frozen",
                )
                .order_by(DatasetSnapshot.created_at)
                .limit(MAX_SNAPSHOT_PICKER)
            )
            .scalars()
            .all()
        )
        payload_view = None
        if row is not None:
            payload_view = {
                "id": str(row.id),
                "gid": _gid("ExportPayload", str(row.id)),
                "transformationVersion": row.transformation_version,
                "purpose": row.purpose,
                "classification": row.classification,
                "sourceClassification": row.source_classification,
                "classificationReview": row.classification_review,
                "digest": row.payload_digest,
                "recordCount": len(row.payload["records"]),
                "byteSize": len(canonical_json(row.payload).encode()),
                "fields": row.payload_fields,
                "document": row.payload,
                "createdAt": row.created_at.isoformat() if row.created_at else None,
            }
        return {
            "proposal": {
                "id": str(proposal.id),
                "gid": _gid("ExportProposal", str(proposal.id)),
                "runId": str(proposal.run_id),
                "status": proposal.status,
                "requiredCapability": proposal.required_capability,
                "boundDigest": proposal.bound_digest,
            },
            "payload": payload_view,
            "redaction": row.redaction_report if row else None,
            "residual": row.residual_report if row else None,
            "manifest": row.manifest if row else None,
            "alias": (
                {
                    "count": len(row.local_alias_map),
                    "kinds": sorted({v["kind"] for v in row.local_alias_map.values()}),
                    "localOnly": True,
                }
                if row
                else None
            ),
            "approval": self._approval_state(row) if row else {"state": "none"},
            "snapshots": [
                {
                    "id": _gid("DatasetSnapshot", str(s.id)),
                    "name": s.name,
                    "purpose": s.purpose,
                    "state": s.state,
                    "digest": s.digest,
                    "taskId": str(s.task_id) if s.task_id else None,
                    "taskMatch": bool(s.task_id and run.task_id and s.task_id == run.task_id),
                }
                for s in snapshots
            ],
            "cloud": cloud_capability(),
            "capabilities": {
                "canReview": self.ctx.has(CAP_REVIEW_EXPORT),
                "canApprove": self.ctx.has(CAP_APPROVE_EXPORT),
            },
            "egress": "deny",
        }
