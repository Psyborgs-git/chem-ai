"""Provider metadata transactions with Keychain-only credentials.

Keychain and PostgreSQL cannot share a transaction. A durable opaque intent
is committed before writing a new key, and retired keys remain retryable until
deletion succeeds. A provider never points at a key that failed to be stored.
"""

from __future__ import annotations

import secrets
import uuid
from builtins import list as list_type
from datetime import UTC, datetime, timedelta

from chem_studio_policy.capabilities import CAP_ADMINISTER_WORKSPACE, CAP_READ_PROJECT
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from studio.application.idempotency import request_digest
from studio.application.inference.runtime import OpenAICompatibleRuntime, validate_base_url
from studio.application.inference.secrets import SecretStore, get_secret_store
from studio.auth.context import ServiceContext
from studio.errors import DomainError, ErrorCode, not_found
from studio.persistence.models import IdempotencyRecord, InferenceCredential, InferenceProvider


class ProviderService:
    def __init__(
        self, db: Session, ctx: ServiceContext, secret_store: SecretStore | None = None
    ) -> None:
        self.db, self.ctx = db, ctx
        self.secrets = secret_store or get_secret_store()

    def can_manage(self) -> bool:
        return self.ctx.principal_kind == "user" and self.ctx.has(CAP_ADMINISTER_WORKSPACE)

    def _admin(self) -> None:
        self.ctx.require(CAP_ADMINISTER_WORKSPACE)
        if self.ctx.principal_kind != "user":
            raise DomainError(
                ErrorCode.FORBIDDEN, "provider configuration requires a human administrator"
            )

    def list(self) -> list[InferenceProvider]:
        self.ctx.require(CAP_READ_PROJECT)
        query = select(InferenceProvider).where(
            InferenceProvider.workspace_id == self.ctx.workspace_id
        )
        if not self.can_manage():
            query = query.where(InferenceProvider.enabled.is_(True))
        return list(
            self.db.scalars(query.order_by(InferenceProvider.created_at, InferenceProvider.id))
        )

    def get(self, provider_id: uuid.UUID, *, lock: bool = False) -> InferenceProvider:
        self.ctx.require(CAP_READ_PROJECT)
        query = select(InferenceProvider).where(
            InferenceProvider.id == provider_id,
            InferenceProvider.workspace_id == self.ctx.workspace_id,
        )
        if lock:
            query = query.with_for_update()
        row = self.db.scalar(query.execution_options(populate_existing=True))
        if row is None:
            raise not_found("inference provider")
        return row

    @staticmethod
    def _version(row: InferenceProvider, expected: int | None) -> None:
        if expected != row.version:
            raise DomainError(
                ErrorCode.REVISION_CONFLICT, "provider changed; reload before editing"
            )

    def _cleanup(self, references: list_type[uuid.UUID] | None = None) -> bool:
        rows = list(
            self.db.scalars(
                select(InferenceCredential).where(
                    InferenceCredential.workspace_id == self.ctx.workspace_id,
                    InferenceCredential.state == "retired",
                )
            )
        )
        # Pending intents left by a process crash are cleaned after a grace
        # period; a currently-saving request is never mistaken for an orphan.
        stale = list(
            self.db.scalars(
                select(InferenceCredential).where(
                    InferenceCredential.workspace_id == self.ctx.workspace_id,
                    InferenceCredential.state == "pending",
                    InferenceCredential.created_at < datetime.now(UTC) - timedelta(hours=1),
                )
            )
        )
        rows.extend(stale)
        if references:
            rows.extend(
                self.db.scalars(
                    select(InferenceCredential).where(
                        InferenceCredential.workspace_id == self.ctx.workspace_id,
                        InferenceCredential.id.in_(references),
                        InferenceCredential.state != "active",
                    )
                )
            )
        pending = False
        for row in {item.id: item for item in rows}.values():
            row.state = "retired"
            try:
                self.secrets.delete(self.ctx.workspace_id, row.id)
            except DomainError:
                pending = True
            else:
                self.db.delete(row)
        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            pending = True
        return pending

    def save(
        self,
        *,
        name: str,
        kind: str,
        base_url: str,
        model: str,
        api_style: str = "chat_completions",
        enabled: bool = False,
        supports_tools: bool = True,
        provider_id: uuid.UUID | None = None,
        expected_revision: int | None = None,
        api_key: str | None = None,
        clear_api_key: bool = False,
        client_mutation_id: str | None = None,
    ) -> InferenceProvider:
        self._admin()
        base_url = validate_base_url(base_url)
        if not name.strip() or len(name) > 120 or not model.strip() or len(model) > 160:
            raise DomainError(
                ErrorCode.VALIDATION, "provider name and model must be nonempty and bounded"
            )
        if kind not in {"openai", "openai_compatible"} or api_style not in {
            "chat_completions",
            "responses",
        }:
            raise DomainError(
                ErrorCode.VALIDATION, "supported providers use Chat Completions or Responses"
            )
        if api_key and (
            not 8 <= len(api_key) <= 8192 or any(not 33 <= ord(c) <= 126 for c in api_key)
        ):
            raise DomainError(
                ErrorCode.VALIDATION,
                "API key must be 8-8192 characters without whitespace or controls",
            )
        replacement = api_key or None
        if clear_api_key and replacement:
            raise DomainError(ErrorCode.VALIDATION, "replace or clear the API key, not both")
        command_key = (
            f"{self.ctx.principal_id}:{client_mutation_id}" if client_mutation_id else None
        )
        if command_key and len(command_key) > 200:
            raise DomainError(ErrorCode.VALIDATION, "clientMutationId is too long")
        metadata = {
            "id": str(provider_id) if provider_id else None,
            "revision": expected_revision,
            "name": name.strip(),
            "kind": kind,
            "baseUrl": base_url,
            "model": model.strip(),
            "apiStyle": api_style,
            "enabled": enabled,
            "supportsTools": supports_tools,
            "clearApiKey": clear_api_key,
        }
        # No credential-derived verifier belongs in the database. Replays
        # compare the supplied key with its still-active Keychain item.
        fingerprint = request_digest({**metadata, "keyProvided": replacement is not None})

        def replay() -> InferenceProvider | None:
            if command_key is None:
                return None
            record = self.db.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.workspace_id == self.ctx.workspace_id,
                    IdempotencyRecord.operation == "providers.save",
                    IdempotencyRecord.key == command_key,
                )
            )
            if record is None:
                return None
            if record.request_digest != fingerprint:
                raise DomainError(
                    ErrorCode.IDEMPOTENCY_MISMATCH,
                    "clientMutationId was already used with different settings",
                )
            response = record.response or {}
            current = self.get(uuid.UUID(str(response["providerId"])))
            if current.version != response.get("revision") or str(
                current.credential_ref
            ) != response.get("credentialRef"):
                raise DomainError(
                    ErrorCode.CONFLICT, "saved provider changed; reload before retrying"
                )
            if replacement:
                if current.credential_ref is None or not secrets.compare_digest(
                    replacement, self.secrets.get(self.ctx.workspace_id, current.credential_ref)
                ):
                    raise DomainError(
                        ErrorCode.IDEMPOTENCY_MISMATCH,
                        "clientMutationId was used with a different API key",
                    )
            return current

        previous = replay()
        if previous is not None:
            return previous
        row = self.get(provider_id, lock=True) if provider_id else None
        if row is not None:
            self._version(row, expected_revision)
            if (
                row.credential_ref
                and (row.base_url != base_url or row.kind != kind)
                and not (replacement or clear_api_key)
            ):
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "changing a keyed provider destination requires "
                    "replacing or removing its API key",
                )
        new_reference: uuid.UUID | None = None
        if replacement:
            intent = InferenceCredential(workspace_id=self.ctx.workspace_id, state="pending")
            self.db.add(intent)
            self.db.commit()
            new_reference = intent.id
            try:
                self.secrets.put(self.ctx.workspace_id, new_reference, replacement)
            except DomainError:
                self._cleanup([new_reference])
                raise
        try:
            # A Keychain operation may release the metadata lock at the
            # committed intent boundary. Recheck the compare-and-swap.
            if provider_id:
                row = self.get(provider_id, lock=True)
                self._version(row, expected_revision)
            if row is None:
                row = InferenceProvider(workspace_id=self.ctx.workspace_id, version=1)
                self.db.add(row)
            else:
                row.version += 1
            old_reference = row.credential_ref
            row.name, row.kind, row.base_url, row.model = (
                name.strip(),
                kind,
                base_url,
                model.strip(),
            )
            row.api_style, row.enabled, row.supports_tools = api_style, enabled, supports_tools
            row.last_test_status, row.last_test_detail, row.last_test_at = "untested", None, None
            if new_reference or clear_api_key:
                row.credential_ref = new_reference
                if old_reference:
                    old = self.db.get(InferenceCredential, old_reference)
                    if old is not None:
                        old.state = "retired"
            if new_reference:
                current = self.db.get(InferenceCredential, new_reference)
                if current is not None:
                    current.state = "active"
            self.db.flush()
            if command_key:
                self.db.add(
                    IdempotencyRecord(
                        workspace_id=self.ctx.workspace_id,
                        principal_id=self.ctx.principal_id,
                        operation="providers.save",
                        key=command_key,
                        request_digest=fingerprint,
                        response={
                            "providerId": str(row.id),
                            "revision": row.version,
                            "credentialRef": str(row.credential_ref),
                        },
                        status="succeeded",
                        completed_at=datetime.now(UTC),
                    )
                )
            self.db.commit()
        except (SQLAlchemyError, DomainError):
            self.db.rollback()
            if new_reference:
                self._cleanup([new_reference])
            winner = replay()
            if winner is not None:
                return winner
            raise
        self._cleanup()
        return row

    def delete(self, provider_id: uuid.UUID, expected_revision: int) -> bool:
        self._admin()
        row = self.get(provider_id, lock=True)
        self._version(row, expected_revision)
        if row.credential_ref:
            credential = self.db.get(InferenceCredential, row.credential_ref)
            if credential is not None:
                credential.state = "retired"
        self.db.delete(row)
        self.db.commit()
        return self._cleanup()

    def cleanup_credentials(self) -> bool:
        self._admin()
        return self._cleanup()

    def cleanup_pending(self) -> bool:
        self._admin()
        return (
            self.db.scalar(
                select(InferenceCredential.id)
                .where(
                    InferenceCredential.workspace_id == self.ctx.workspace_id,
                    or_(
                        InferenceCredential.state == "retired",
                        (InferenceCredential.state == "pending")
                        & (InferenceCredential.created_at < datetime.now(UTC) - timedelta(hours=1)),
                    ),
                )
                .limit(1)
            )
            is not None
        )

    def test(self, provider_id: uuid.UUID) -> InferenceProvider:
        self._admin()
        row = self.get(provider_id, lock=True)
        # Release row locks before a bounded network request. The immutable
        # revision snapshot is checked again before recording its probe.
        version = row.version
        self.db.commit()
        key_error: DomainError | None = None
        try:
            result = OpenAICompatibleRuntime(row, self.secrets).models()
            data = result.get("data")
            if not isinstance(data, list) or any(
                not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in data
            ):
                raise RuntimeError("provider returned an invalid model list")
            listed = any(item["id"] == row.model for item in data)
            status = "reachable"
            detail = (
                "Endpoint responded; configured model is listed. "
                if listed
                else "Endpoint responded; configured model was not listed and remains unverified. "
            ) + "Completion and tool compatibility were not tested."
        except (RuntimeError, DomainError) as exc:
            status = "failed"
            detail = exc.message if isinstance(exc, DomainError) else str(exc)
            if isinstance(exc, DomainError):
                key_error = exc
        row = self.get(provider_id, lock=True)
        self._version(row, version)
        row.last_test_status, row.last_test_detail, row.last_test_at = (
            status,
            detail,
            datetime.now(UTC),
        )
        self.db.commit()
        if key_error is not None:
            raise key_error
        return row
