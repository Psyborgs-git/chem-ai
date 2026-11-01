# GraphQL command state and validation contracts

These generated source excerpts define exact capability checks, accepted payloads, state transitions and version/approval rules for the corresponding commands. They are static documentation; viewing Help never invokes them.

## AnalyticalMutation.compare

Source: `services/studio-api/src/studio/api/graphql/schema.py:AnalyticalMutation.compare`.

```python
    @strawberry.mutation
    def compare(self, info: strawberry.Info, input: AnalyticalCompareInput) -> AnalyticalResult:
        from studio.domain.chemistry.analytics import AnalyticsService

        gql = gql_ctx(info)
        try:
            if not isinstance(input.spec, dict):
                raise DomainError(ErrorCode.VALIDATION, "spec must be an object")
            row = AnalyticsService(gql.db, gql.service_ctx(), gql.settings).compare(
                _gid_uuid(input.task_id, "Task", "taskId"),
                _gid_uuid(input.left_series_id, "AnalyticalSeries", "leftSeriesId"),
                _gid_uuid(input.right_series_id, "AnalyticalSeries", "rightSeriesId"),
                input.spec,
                input.idempotency_key,
            )
            gql.db.commit()
            task = gql.db.get(TaskRow, row.task_id)
            return AnalyticalResult(
                task=Task.from_row(task) if task else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return AnalyticalResult(
                task=None, errors=[_err_payload(exc)], client_mutation_id=input.client_mutation_id
            )
```

## AnalyticalMutation.ingest

Source: `services/studio-api/src/studio/api/graphql/schema.py:AnalyticalMutation.ingest`.

```python
    @strawberry.mutation
    def ingest(self, info: strawberry.Info, input: AnalyticalIngestInput) -> AnalyticalResult:
        from studio.domain.chemistry.analytics import AnalyticsService

        gql = gql_ctx(info)
        try:
            if not isinstance(input.spec, dict):
                raise DomainError(ErrorCode.VALIDATION, "spec must be an object")
            try:
                a_uuid = uuid.UUID(input.raw_artifact_id)
            except ValueError as e:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "malformed artifact id",
                    field_path="input.rawArtifactId",
                ) from e
            row = AnalyticsService(gql.db, gql.service_ctx(), gql.settings).ingest(
                _gid_uuid(input.task_id, "Task", "taskId"),
                a_uuid,
                input.spec,
                input.idempotency_key,
            )
            gql.db.commit()
            task = gql.db.get(TaskRow, row.task_id)
            return AnalyticalResult(
                task=Task.from_row(task) if task else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return AnalyticalResult(
                task=None, errors=[_err_payload(exc)], client_mutation_id=input.client_mutation_id
            )
```

## CandidatesMutation.create

Source: `services/studio-api/src/studio/api/graphql/schema.py:CandidatesMutation.create`.

```python
    @strawberry.mutation
    def create(self, info: strawberry.Info, input: CandidateCreateInput) -> CandidateRevisionResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = CandidateService(gql.db, ctx)
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")
            entity_rev = uuid.UUID(input.entity_revision_id) if input.entity_revision_id else None
            payload = {
                "taskId": str(t_uuid),
                "entityKind": input.entity_kind,
                "entityRevisionId": input.entity_revision_id,
                "hypothesis": input.hypothesis,
            }

            def _do() -> dict[str, str]:
                row = svc.create_candidate(
                    task_id=t_uuid,
                    entity_kind=input.entity_kind,
                    entity_revision_id=entity_rev,
                    hypothesis=input.hypothesis,
                    proposed_differences=cast(
                        list[dict[str, Any]] | None, input.proposed_differences
                    ),
                    evidence_ids=cast(list[str] | None, input.evidence_ids),
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="candidate.create",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(CandidateRow, uuid.UUID(result["id"]))
            return CandidateRevisionResult(
                candidate=CandidateRevision.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return CandidateRevisionResult(
                candidate=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## CandidatesMutation.patch_propose

Source: `services/studio-api/src/studio/api/graphql/schema.py:CandidatesMutation.patch_propose`.

```python
    @strawberry.mutation
    def patch_propose(
        self, info: strawberry.Info, input: CandidatePatchProposeInput
    ) -> CandidatePatchResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = CandidateService(gql.db, ctx)
            c_uuid = _gid_uuid(input.candidate_id, "CandidateRevision", "candidateId")

            def _do() -> dict[str, str]:
                row = svc.propose_patch(
                    candidate_id=c_uuid,
                    patch=cast(dict[str, Any], input.patch),
                    reason=input.reason,
                )
                return {"id": str(row.id), "status": row.status}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="candidate.patch_propose",
                payload={
                    "candidateId": str(c_uuid),
                    "patch": cast(dict[str, Any], input.patch),
                },
                fn=_do,
            )
            gql.db.commit()
            return CandidatePatchResult(
                patch_id=result["id"],
                status=result["status"],
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return CandidatePatchResult(
                patch_id=None,
                status=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## CandidatesMutation.patch_review

Source: `services/studio-api/src/studio/api/graphql/schema.py:CandidatesMutation.patch_review`.

```python
    @strawberry.mutation
    def patch_review(
        self, info: strawberry.Info, input: CandidatePatchReviewInput
    ) -> CandidatePatchResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = CandidateService(gql.db, ctx)
            row = svc.review_patch(
                patch_id=uuid.UUID(input.patch_id),
                accept=input.accept,
                rejection_reason=input.rejection_reason,
            )
            gql.db.commit()
            return CandidatePatchResult(
                patch_id=str(row.id),
                status=row.status,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return CandidatePatchResult(
                patch_id=None,
                status=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## CandidatesMutation.review

Source: `services/studio-api/src/studio/api/graphql/schema.py:CandidatesMutation.review`.

```python
    @strawberry.mutation
    def review(self, info: strawberry.Info, input: CandidateReviewInput) -> CandidateRevisionResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = CandidateService(gql.db, ctx)
            c_uuid = _gid_uuid(input.candidate_id, "CandidateRevision", "candidateId")
            row = svc.review_candidate(candidate_id=c_uuid, accept=input.accept)
            gql.db.commit()
            return CandidateRevisionResult(
                candidate=CandidateRevision.from_row(row),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return CandidateRevisionResult(
                candidate=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## CandidatesMutation.submit

Source: `services/studio-api/src/studio/api/graphql/schema.py:CandidatesMutation.submit`.

```python
    @strawberry.mutation
    def submit(self, info: strawberry.Info, input: CandidateSubmitInput) -> CandidateRevisionResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            svc = CandidateService(gql.db, ctx)
            c_uuid = _gid_uuid(input.candidate_id, "CandidateRevision", "candidateId")
            row = svc.submit_candidate(candidate_id=c_uuid)
            gql.db.commit()
            return CandidateRevisionResult(
                candidate=CandidateRevision.from_row(row),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return CandidateRevisionResult(
                candidate=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## EvidenceMutation.claim_create

Source: `services/studio-api/src/studio/api/graphql/schema.py:EvidenceMutation.claim_create`.

```python
    @strawberry.mutation
    def claim_create(self, info: strawberry.Info, input: ClaimCreateInput) -> EvidenceClaimResult:
        gql = gql_ctx(info)
        try:
            payload = {"kind": input.kind, "subject": input.subject}

            def _do() -> dict[str, str]:
                row = ClaimService(gql.db).create_claim(
                    gql.service_ctx(),
                    kind=input.kind,
                    subject=cast(dict[str, Any], input.subject),
                    statement=cast(dict[str, Any], input.statement),
                    locator=cast(dict[str, Any] | None, input.locator),
                    original_text=input.original_text,
                    conditions=cast(dict[str, Any] | None, input.conditions),
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="evidence.claim_create",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(ClaimRow, uuid.UUID(result["id"]))
            return EvidenceClaimResult(
                claim=EvidenceClaim.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return EvidenceClaimResult(
                claim=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## EvidenceMutation.claim_link

Source: `services/studio-api/src/studio/api/graphql/schema.py:EvidenceMutation.claim_link`.

```python
    @strawberry.mutation
    def claim_link(self, info: strawberry.Info, input: ClaimLinkInput) -> ClaimLinkResult:
        gql = gql_ctx(info)
        try:
            f_uuid = _gid_uuid(input.from_claim_id, "EvidenceClaim", "fromClaimId")
            t_uuid = _gid_uuid(input.to_claim_id, "EvidenceClaim", "toClaimId")
            payload = {
                "from": str(f_uuid),
                "to": str(t_uuid),
                "relation": input.relation,
            }

            def _do() -> dict[str, str]:
                row = ClaimService(gql.db).link(
                    gql.service_ctx(),
                    f_uuid,
                    t_uuid,
                    input.relation,
                    note=input.note,
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="evidence.claim_link",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(LinkRow, uuid.UUID(result["id"]))
            return ClaimLinkResult(
                link=ClaimLink.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ClaimLinkResult(
                link=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## EvidenceMutation.claim_review

Source: `services/studio-api/src/studio/api/graphql/schema.py:EvidenceMutation.claim_review`.

```python
    @strawberry.mutation
    def claim_review(self, info: strawberry.Info, input: ClaimReviewInput) -> EvidenceClaimResult:
        gql = gql_ctx(info)
        try:
            c_uuid = _gid_uuid(input.claim_id, "EvidenceClaim", "claimId")
            payload = {"claimId": str(c_uuid), "decision": input.decision}

            def _do() -> dict[str, str]:
                row = ClaimService(gql.db).review(gql.service_ctx(), c_uuid, input.decision)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="evidence.claim_review",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(ClaimRow, uuid.UUID(result["id"]))
            return EvidenceClaimResult(
                claim=EvidenceClaim.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return EvidenceClaimResult(
                claim=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ExportsMutation.decide

Source: `services/studio-api/src/studio/api/graphql/schema.py:ExportsMutation.decide`.

```python
    @strawberry.mutation
    def decide(self, info: strawberry.Info, input: ExportDecideInput) -> ExportReviewResult:
        gql = gql_ctx(info)
        try:
            p_uuid = _gid_uuid(input.payload_id, "ExportPayload", "payloadId")
            service = TransformService(gql.db, gql.service_ctx())
            row = service.payload(p_uuid)
            service.decide(
                p_uuid,
                decision=input.decision,
                rationale=input.rationale,
                ttl_seconds=input.ttl_seconds,
            )
            gql.db.commit()
            return ExportReviewResult(
                view=JSON(service.review_view(row.proposal_id)),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ExportReviewResult(
                view=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ExportsMutation.prepare

Source: `services/studio-api/src/studio/api/graphql/schema.py:ExportsMutation.prepare`.

```python
    @strawberry.mutation
    def prepare(self, info: strawberry.Info, input: ExportPrepareInput) -> ExportReviewResult:
        gql = gql_ctx(info)
        try:
            p_uuid = _gid_uuid(input.proposal_id, "ExportProposal", "proposalId")
            s_uuid = _gid_uuid(input.snapshot_id, "DatasetSnapshot", "snapshotId")
            service = TransformService(gql.db, gql.service_ctx())
            row = service.prepare(
                p_uuid,
                s_uuid,
                recipient=input.recipient,
                account=input.account,
                region=input.region,
                expires_at=_parse_export_expiry(input.expires_at),
                max_records=input.max_records,
                max_bytes=input.max_bytes,
                retention_expectation=input.retention_expectation,
                deletion_expectation=input.deletion_expectation,
            )
            gql.db.commit()
            return ExportReviewResult(
                view=JSON(service.review_view(row.proposal_id)),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ExportReviewResult(
                view=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ExportsMutation.set_classification

Source: `services/studio-api/src/studio/api/graphql/schema.py:ExportsMutation.set_classification`.

```python
    @strawberry.mutation
    def set_classification(
        self, info: strawberry.Info, input: ExportSetClassificationInput
    ) -> ExportReviewResult:
        gql = gql_ctx(info)
        try:
            p_uuid = _gid_uuid(input.payload_id, "ExportPayload", "payloadId")
            service = TransformService(gql.db, gql.service_ctx())
            row = service.set_classification(
                p_uuid,
                classification=input.classification,
                rationale=input.rationale or "",
            )
            gql.db.commit()
            return ExportReviewResult(
                view=JSON(service.review_view(row.proposal_id)),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ExportReviewResult(
                view=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## FormulationsMutation.family_create

Source: `services/studio-api/src/studio/api/graphql/schema.py:FormulationsMutation.family_create`.

```python
    @strawberry.mutation
    def family_create(
        self, info: strawberry.Info, input: FormulationFamilyCreateInput
    ) -> FormulationFamilyResult:
        gql = gql_ctx(info)
        try:
            svc = FormulationService(gql.db, gql.service_ctx())
            payload = {"name": input.name, "description": input.description}

            def _do() -> dict[str, str]:
                row = svc.create_family(name=input.name, description=input.description)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="formulation.family_create",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(FamilyRow, uuid.UUID(result["id"]))
            return FormulationFamilyResult(
                family=FormulationFamily.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return FormulationFamilyResult(
                family=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## FormulationsMutation.process_accept

Source: `services/studio-api/src/studio/api/graphql/schema.py:FormulationsMutation.process_accept`.

```python
    @strawberry.mutation
    def process_accept(
        self, info: strawberry.Info, input: ProcessRevisionIdInput
    ) -> ProcessRevisionResult:
        gql = gql_ctx(info)
        try:
            svc = FormulationService(gql.db, gql.service_ctx())
            r_uuid = _gid_uuid(input.revision_id, "ProcessRevision", "revisionId")

            def _do() -> dict[str, str]:
                row = svc.accept_process_revision(revision_id=r_uuid)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="formulation.process_accept",
                payload={"revisionId": str(r_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(ProcRevRow, uuid.UUID(result["id"]))
            return ProcessRevisionResult(
                revision=ProcessRevision.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ProcessRevisionResult(
                revision=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## FormulationsMutation.process_draft

Source: `services/studio-api/src/studio/api/graphql/schema.py:FormulationsMutation.process_draft`.

```python
    @strawberry.mutation
    def process_draft(
        self, info: strawberry.Info, input: ProcessRevisionDraftInput
    ) -> ProcessRevisionResult:
        gql = gql_ctx(info)
        try:
            svc = FormulationService(gql.db, gql.service_ctx())
            f_uuid = _gid_uuid(input.family_id, "FormulationFamily", "familyId")
            if not isinstance(input.payload, dict):
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "payload must be an object",
                    field_path="input.payload",
                )
            payload = {"familyId": str(f_uuid), "payload": input.payload}

            def _do() -> dict[str, str]:
                row = svc.draft_process_revision(
                    family_id=f_uuid, payload=cast(dict[str, Any], input.payload)
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="formulation.process_draft",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(ProcRevRow, uuid.UUID(result["id"]))
            return ProcessRevisionResult(
                revision=ProcessRevision.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ProcessRevisionResult(
                revision=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## FormulationsMutation.revision_accept

Source: `services/studio-api/src/studio/api/graphql/schema.py:FormulationsMutation.revision_accept`.

```python
    @strawberry.mutation
    def revision_accept(
        self, info: strawberry.Info, input: FormulationRevisionIdInput
    ) -> FormulationRevisionResult:
        gql = gql_ctx(info)
        try:
            svc = FormulationService(gql.db, gql.service_ctx())
            r_uuid = _gid_uuid(input.revision_id, "FormulationRevision", "revisionId")

            def _do() -> dict[str, str]:
                row = svc.accept_revision(revision_id=r_uuid)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="formulation.revision_accept",
                payload={"revisionId": str(r_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(FormRevRow, uuid.UUID(result["id"]))
            fam = gql.db.get(FamilyRow, row.family_id) if row else None
            return FormulationRevisionResult(
                revision=FormulationRevision.from_row(row, family_name=fam.name if fam else None)
                if row
                else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return FormulationRevisionResult(
                revision=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## FormulationsMutation.revision_draft

Source: `services/studio-api/src/studio/api/graphql/schema.py:FormulationsMutation.revision_draft`.

```python
    @strawberry.mutation
    def revision_draft(
        self, info: strawberry.Info, input: FormulationRevisionDraftInput
    ) -> FormulationRevisionResult:
        gql = gql_ctx(info)
        try:
            svc = FormulationService(gql.db, gql.service_ctx())
            f_uuid = _gid_uuid(input.family_id, "FormulationFamily", "familyId")
            p_uuid = (
                _gid_uuid(input.parent_revision_id, "FormulationRevision", "parentRevisionId")
                if input.parent_revision_id is not None
                else None
            )
            if not isinstance(input.payload, dict):
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "payload must be an object",
                    field_path="input.payload",
                )
            payload = {
                "familyId": str(f_uuid),
                "parentRevisionId": str(p_uuid) if p_uuid else None,
                "payload": input.payload,
            }

            def _do() -> dict[str, str]:
                row = svc.draft_revision(
                    family_id=f_uuid,
                    payload=cast(dict[str, Any], input.payload),
                    parent_revision_id=p_uuid,
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="formulation.revision_draft",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(FormRevRow, uuid.UUID(result["id"]))
            fam = gql.db.get(FamilyRow, row.family_id) if row else None
            return FormulationRevisionResult(
                revision=FormulationRevision.from_row(row, family_name=fam.name if fam else None)
                if row
                else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return FormulationRevisionResult(
                revision=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ImportsMutation.artifact_import

Source: `services/studio-api/src/studio/api/graphql/schema.py:ImportsMutation.artifact_import`.

```python
    @strawberry.mutation
    def artifact_import(
        self, info: strawberry.Info, input: ImportArtifactInput
    ) -> ImportBatchResult:
        """Run the quarantined ingestion pipeline over a committed
        artifact — dedup makes a reimport return the existing batch."""
        gql = gql_ctx(info)
        try:
            try:
                a_uuid = uuid.UUID(input.artifact_id)
            except ValueError as exc:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "malformed artifact id",
                    field_path="input.artifactId",
                ) from exc
            payload = {"artifactId": str(a_uuid)}
            from studio.domain.evidence.vault import Vault

            def _do() -> dict[str, str]:
                batch, deduped = ImportService(
                    gql.db, Vault(gql.settings.vault_root)
                ).import_artifact(gql.service_ctx(), a_uuid)
                return {"id": str(batch.id), "deduplicated": str(deduped)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="imports.artifact_import",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(BatchRow, uuid.UUID(result["id"]))
            return ImportBatchResult(
                batch=ImportBatch.from_row(row) if row else None,
                deduplicated=result["deduplicated"] == "True",
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ImportBatchResult(
                batch=None,
                deduplicated=False,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ImportsMutation.record_promote

Source: `services/studio-api/src/studio/api/graphql/schema.py:ImportsMutation.record_promote`.

```python
    @strawberry.mutation
    def record_promote(
        self, info: strawberry.Info, input: PromoteRecordInput
    ) -> EvidenceClaimResult:
        """Promote an extracted field to a proposed evidence claim —
        ambiguity stays visible; nothing is auto-accepted."""
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.record_id, "ExtractedRecord", "recordId")
            payload = {
                "recordId": str(r_uuid),
                "subject": input.subject,
                "statement": input.statement,
            }

            def _do() -> dict[str, str]:
                row = ClaimService(gql.db).promote_record(
                    gql.service_ctx(),
                    r_uuid,
                    subject=cast(dict[str, Any], input.subject),
                    statement=cast(dict[str, Any], input.statement),
                    conditions=cast(dict[str, Any] | None, input.conditions),
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="imports.record_promote",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(ClaimRow, uuid.UUID(result["id"]))
            return EvidenceClaimResult(
                claim=EvidenceClaim.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return EvidenceClaimResult(
                claim=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ImportsMutation.record_review

Source: `services/studio-api/src/studio/api/graphql/schema.py:ImportsMutation.record_review`.

```python
    @strawberry.mutation
    def record_review(
        self, info: strawberry.Info, input: ReviewRecordInput
    ) -> ExtractedRecordResult:
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.record_id, "ExtractedRecord", "recordId")
            payload = {"recordId": str(r_uuid), "decision": input.decision}

            def _do() -> dict[str, str]:
                row = ImportService(gql.db, None).review_record(
                    gql.service_ctx(), r_uuid, input.decision
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="imports.record_review",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(RecordRow, uuid.UUID(result["id"]))
            return ExtractedRecordResult(
                record=ExtractedRecord.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ExtractedRecordResult(
                record=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ImportsMutation.source_revoke

Source: `services/studio-api/src/studio/api/graphql/schema.py:ImportsMutation.source_revoke`.

```python
    @strawberry.mutation
    def source_revoke(self, info: strawberry.Info, input: SourceRevokeInput) -> SourceRevokeResult:
        """Revoke a source and propagate supersession through index,
        records, claims, and downstream lineage (§9.4, §17.5)."""
        gql = gql_ctx(info)
        try:
            try:
                a_uuid = uuid.UUID(input.artifact_id)
            except ValueError as exc:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "malformed artifact id",
                    field_path="input.artifactId",
                ) from exc
            payload = {"artifactId": str(a_uuid), "reason": input.reason}

            def _do() -> dict[str, str]:
                row = RevocationService(gql.db, gql.service_ctx()).revoke(
                    gql.service_ctx(), a_uuid, reason=input.reason
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="imports.source_revoke",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(RevocationRow, uuid.UUID(result["id"]))
            return SourceRevokeResult(
                report=JSON(row.report) if row else None,
                revocation_id=result["id"],
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return SourceRevokeResult(
                report=None,
                revocation_id=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LabMeasurementsMutation.actuals_record

Source: `services/studio-api/src/studio/api/graphql/schema.py:LabMeasurementsMutation.actuals_record`.

```python
    @strawberry.mutation
    def actuals_record(self, info: strawberry.Info, input: ActualsRecordInput) -> ExecutionResult:
        gql = gql_ctx(info)
        try:
            e_uuid = _gid_uuid(input.execution_id, "LabExecution", "executionId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).record_actuals(
                    e_uuid,
                    actual=cast(dict[str, Any] | None, input.actual),
                    deviations=cast(list[dict[str, Any]] | None, input.deviations),
                    observations=input.observations,
                )
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.actuals_record",
                payload={"executionId": str(e_uuid)},
                fn=_do,
            )
            return _execution_result(gql, result, input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return _execution_error(exc, input.client_mutation_id)
```

## LabMeasurementsMutation.batch_add

Source: `services/studio-api/src/studio/api/graphql/schema.py:LabMeasurementsMutation.batch_add`.

```python
    @strawberry.mutation
    def batch_add(self, info: strawberry.Info, input: BatchAddInput) -> BatchResult:
        gql = gql_ctx(info)
        try:
            e_uuid = _gid_uuid(input.execution_id, "LabExecution", "executionId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).add_batch(
                    e_uuid,
                    label=input.label,
                    payload=cast(dict[str, Any] | None, input.payload),
                )
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.batch_add",
                payload={"executionId": str(e_uuid), "label": input.label},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(LabBatchRow, uuid.UUID(result["id"]))
            return BatchResult(
                batch=LabBatch.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return BatchResult(
                batch=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LabMeasurementsMutation.execution_close

Source: `services/studio-api/src/studio/api/graphql/schema.py:LabMeasurementsMutation.execution_close`.

```python
    @strawberry.mutation
    def execution_close(self, info: strawberry.Info, input: ExecutionCloseInput) -> ExecutionResult:
        gql = gql_ctx(info)
        try:
            e_uuid = _gid_uuid(input.execution_id, "LabExecution", "executionId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).close_execution(
                    e_uuid, status=input.status
                )
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.execution_close",
                payload={"executionId": str(e_uuid), "status": input.status},
                fn=_do,
            )
            return _execution_result(gql, result, input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return _execution_error(exc, input.client_mutation_id)
```

## LabMeasurementsMutation.execution_historical_import

Source: `services/studio-api/src/studio/api/graphql/schema.py:LabMeasurementsMutation.execution_historical_import`.

```python
    @strawberry.mutation
    def execution_historical_import(
        self, info: strawberry.Info, input: ExecutionHistoricalInput
    ) -> ExecutionResult:
        """Historical record — marked, never retrospectively approved."""
        gql = gql_ctx(info)
        try:
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).import_historical(
                    t_uuid, payload=cast(dict[str, Any], input.payload)
                )
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.execution_historical",
                payload={"taskId": str(t_uuid)},
                fn=_do,
            )
            return _execution_result(gql, result, input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return _execution_error(exc, input.client_mutation_id)
```

## LabMeasurementsMutation.execution_open

Source: `services/studio-api/src/studio/api/graphql/schema.py:LabMeasurementsMutation.execution_open`.

```python
    @strawberry.mutation
    def execution_open(self, info: strawberry.Info, input: ExecutionOpenInput) -> ExecutionResult:
        gql = gql_ctx(info)
        try:
            p_uuid = _gid_uuid(input.plan_id, "ExperimentPlan", "planId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).open_execution(p_uuid)
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.execution_open",
                payload={"planId": str(p_uuid)},
                fn=_do,
            )
            return _execution_result(gql, result, input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return _execution_error(exc, input.client_mutation_id)
```

## LabMeasurementsMutation.measurement_amend

Source: `services/studio-api/src/studio/api/graphql/schema.py:LabMeasurementsMutation.measurement_amend`.

```python
    @strawberry.mutation
    def measurement_amend(
        self, info: strawberry.Info, input: MeasurementAmendInput
    ) -> MeasurementResult:
        gql = gql_ctx(info)
        try:
            m_uuid = _gid_uuid(input.measurement_id, "Measurement", "measurementId")

            def _do() -> dict[str, str]:
                LabMeasurementService(gql.db, gql.service_ctx()).amend(
                    m_uuid,
                    reason=input.reason,
                    source=input.source,
                    value=cast(dict[str, Any], input.value),
                    conditions=cast(dict[str, Any] | None, input.conditions),
                )
                return {"id": str(m_uuid)}

            result = _lab_mutation(
                gql,
                operation="lab.measurement_amend",
                payload={"measurementId": str(m_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(MeasurementRow, uuid.UUID(result["id"]))
            return MeasurementResult(
                measurement=Measurement.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return _measurement_error(exc, input.client_mutation_id)
```

## LabMeasurementsMutation.measurement_applicability

Source: `services/studio-api/src/studio/api/graphql/schema.py:LabMeasurementsMutation.measurement_applicability`.

```python
    @strawberry.mutation
    def measurement_applicability(
        self, info: strawberry.Info, input: MeasurementApplicabilityInput
    ) -> MeasurementResult:
        gql = gql_ctx(info)
        try:
            m_uuid = _gid_uuid(input.measurement_id, "Measurement", "measurementId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).set_applicability(
                    m_uuid, applicable=input.applicable, note=input.note
                )
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.measurement_applicability",
                payload={"measurementId": str(m_uuid), "applicable": input.applicable},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(MeasurementRow, uuid.UUID(result["id"]))
            return MeasurementResult(
                measurement=Measurement.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return _measurement_error(exc, input.client_mutation_id)
```

## LabMeasurementsMutation.measurement_map_applicability

Source: `services/studio-api/src/studio/api/graphql/schema.py:LabMeasurementsMutation.measurement_map_applicability`.

```python
    @strawberry.mutation
    def measurement_map_applicability(
        self, info: strawberry.Info, input: MeasurementApplicabilityMapInput
    ) -> ApplicabilityMapResult:
        """Record (or withdraw) a reviewed evidence→candidate
        applicability mapping — the only path for lineage-less evidence
        to substantiate a candidate (PAR-02 §4)."""
        gql = gql_ctx(info)
        try:
            m_uuid = _gid_uuid(input.measurement_id, "Measurement", "measurementId")
            c_uuid = _gid_uuid(
                input.candidate_revision_id, "CandidateRevision", "candidateRevisionId"
            )
            k_uuid = (
                _gid_uuid(
                    input.contract_revision_id,
                    "ContractRevision",
                    "contractRevisionId",
                )
                if input.contract_revision_id is not None
                else None
            )
            svc = LabMeasurementService(gql.db, gql.service_ctx())

            def _do() -> dict[str, str]:
                if input.withdraw:
                    row = svc.withdraw_applicability(m_uuid, candidate_revision_id=c_uuid)
                else:
                    row = svc.record_applicability(
                        m_uuid,
                        candidate_revision_id=c_uuid,
                        contract_revision_id=k_uuid,
                        applicable=input.applicable,
                        rationale=input.rationale,
                    )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="lab.measurement_map_applicability",
                payload={
                    "measurementId": str(m_uuid),
                    "candidateRevisionId": str(c_uuid),
                    "contractRevisionId": str(k_uuid) if k_uuid else None,
                    "applicable": input.applicable,
                    "withdraw": input.withdraw,
                },
                fn=_do,
            )
            gql.db.commit()
            return ApplicabilityMapResult(
                mapping_id=result["id"],
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ApplicabilityMapResult(
                mapping_id=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LabMeasurementsMutation.measurement_record

Source: `services/studio-api/src/studio/api/graphql/schema.py:LabMeasurementsMutation.measurement_record`.

```python
    @strawberry.mutation
    def measurement_record(
        self, info: strawberry.Info, input: MeasurementRecordInput
    ) -> MeasurementResult:
        gql = gql_ctx(info)
        try:
            s_uuid = _gid_uuid(input.sample_id, "LabSample", "sampleId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).record_measurement(
                    s_uuid,
                    method=input.method,
                    repeat_type=input.repeat_type,
                    value=cast(dict[str, Any], input.value),
                    metric=input.metric,
                    value_type=input.value_type,
                    conditions=cast(dict[str, Any] | None, input.conditions),
                    pipeline_version=input.pipeline_version,
                )
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.measurement_record",
                payload={"sampleId": str(s_uuid), "method": input.method},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(MeasurementRow, uuid.UUID(result["id"]))
            return MeasurementResult(
                measurement=Measurement.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return _measurement_error(exc, input.client_mutation_id)
```

## LabMeasurementsMutation.measurement_review

Source: `services/studio-api/src/studio/api/graphql/schema.py:LabMeasurementsMutation.measurement_review`.

```python
    @strawberry.mutation
    def measurement_review(
        self, info: strawberry.Info, input: MeasurementReviewInput
    ) -> MeasurementResult:
        gql = gql_ctx(info)
        try:
            m_uuid = _gid_uuid(input.measurement_id, "Measurement", "measurementId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).review(
                    m_uuid, decision=input.decision, note=input.note
                )
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.measurement_review",
                payload={"measurementId": str(m_uuid), "decision": input.decision},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(MeasurementRow, uuid.UUID(result["id"]))
            return MeasurementResult(
                measurement=Measurement.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return _measurement_error(exc, input.client_mutation_id)
```

## LabMeasurementsMutation.sample_add

Source: `services/studio-api/src/studio/api/graphql/schema.py:LabMeasurementsMutation.sample_add`.

```python
    @strawberry.mutation
    def sample_add(self, info: strawberry.Info, input: SampleAddInput) -> SampleResult:
        gql = gql_ctx(info)
        try:
            b_uuid = _gid_uuid(input.batch_id, "LabBatch", "batchId")

            def _do() -> dict[str, str]:
                row = LabMeasurementService(gql.db, gql.service_ctx()).add_sample(
                    b_uuid,
                    label=input.label,
                    kind=input.kind,
                    payload=cast(dict[str, Any] | None, input.payload),
                )
                return {"id": str(row.id)}

            result = _lab_mutation(
                gql,
                operation="lab.sample_add",
                payload={"batchId": str(b_uuid), "label": input.label},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(LabSampleRow, uuid.UUID(result["id"]))
            return SampleResult(
                sample=LabSample.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return SampleResult(
                sample=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LabMutation.packet_export

Source: `services/studio-api/src/studio/api/graphql/schema.py:LabMutation.packet_export`.

```python
    @strawberry.mutation
    def packet_export(self, info: strawberry.Info, input: PlanIdInput) -> PacketResult:
        """Manual-execution packet — gated by a valid, current release
        approval (AT-0501-1/3)."""
        gql = gql_ctx(info)
        try:
            p_uuid = _gid_uuid(input.plan_id, "ExperimentPlan", "planId")

            def _do() -> dict[str, str]:
                LabPlanService(gql.db, gql.service_ctx()).export_packet(p_uuid)
                return {"id": str(p_uuid)}

            result = _mutate(
                gql,
                key=None,
                operation="lab.packet_export",
                payload={"planId": str(p_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(PlanRow, uuid.UUID(result["id"]))
            return PacketResult(
                packet=JSON(row.packet) if row is not None else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return PacketResult(
                packet=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LabMutation.plan_create

Source: `services/studio-api/src/studio/api/graphql/schema.py:LabMutation.plan_create`.

```python
    @strawberry.mutation
    def plan_create(self, info: strawberry.Info, input: PlanCreateInput) -> PlanResult:
        gql = gql_ctx(info)
        try:
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")
            payload = {"taskId": str(t_uuid), "title": input.title}

            def _do() -> dict[str, str]:
                row = LabPlanService(gql.db, gql.service_ctx()).create(
                    t_uuid,
                    title=input.title,
                    payload=cast(dict[str, Any], input.payload),
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="lab.plan_create",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(PlanRow, uuid.UUID(result["id"]))
            return PlanResult(
                plan=ExperimentPlan.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return PlanResult(
                plan=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LabMutation.plan_review

Source: `services/studio-api/src/studio/api/graphql/schema.py:LabMutation.plan_review`.

```python
    @strawberry.mutation
    def plan_review(self, info: strawberry.Info, input: PlanReviewInput) -> PlanResult:
        gql = gql_ctx(info)
        try:
            p_uuid = _gid_uuid(input.plan_id, "ExperimentPlan", "planId")

            def _do() -> dict[str, str]:
                row = LabPlanService(gql.db, gql.service_ctx()).review(
                    p_uuid, decision=input.decision, rationale=input.rationale
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="lab.plan_review",
                payload={
                    "planId": str(p_uuid),
                    "decision": input.decision,
                    "rationale": input.rationale,
                },
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(PlanRow, uuid.UUID(result["id"]))
            return PlanResult(
                plan=ExperimentPlan.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return PlanResult(
                plan=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LabMutation.plan_submit

Source: `services/studio-api/src/studio/api/graphql/schema.py:LabMutation.plan_submit`.

```python
    @strawberry.mutation
    def plan_submit(self, info: strawberry.Info, input: PlanIdInput) -> PlanResult:
        gql = gql_ctx(info)
        try:
            p_uuid = _gid_uuid(input.plan_id, "ExperimentPlan", "planId")

            def _do() -> dict[str, str]:
                row = LabPlanService(gql.db, gql.service_ctx()).submit(p_uuid)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="lab.plan_submit",
                payload={"planId": str(p_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(PlanRow, uuid.UUID(result["id"]))
            return PlanResult(
                plan=ExperimentPlan.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return PlanResult(
                plan=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LabMutation.plan_update

Source: `services/studio-api/src/studio/api/graphql/schema.py:LabMutation.plan_update`.

```python
    @strawberry.mutation
    def plan_update(self, info: strawberry.Info, input: PlanUpdateInput) -> PlanResult:
        gql = gql_ctx(info)
        try:
            p_uuid = _gid_uuid(input.plan_id, "ExperimentPlan", "planId")

            def _do() -> dict[str, str]:
                row = LabPlanService(gql.db, gql.service_ctx()).update(
                    p_uuid, payload=cast(dict[str, Any], input.payload)
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="lab.plan_update",
                payload={"planId": str(p_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(PlanRow, uuid.UUID(result["id"]))
            return PlanResult(
                plan=ExperimentPlan.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return PlanResult(
                plan=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LearningMutation.evaluation_run_start

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.evaluation_run_start`.

```python
    @strawberry.mutation
    def evaluation_run_start(
        self, info: strawberry.Info, input: EvaluationRunStartInput
    ) -> EvaluationRunResult:
        """Execute the §18.2 matched comparison — both arms on the
        same frozen tasks, tools, context and budget."""
        gql = gql_ctx(info)
        try:
            s_uuid = _gid_uuid(input.evaluation_suite_id, "EvaluationSuite", "evaluationSuiteId")
            r_uuid = _gid_uuid(input.model_release_id, "ModelRelease", "modelReleaseId")
            b_uuid = (
                _gid_uuid(input.baseline_release_id, "ModelRelease", "baselineReleaseId")
                if input.baseline_release_id is not None
                else None
            )
            run = self._eval_service(gql).start_run(
                suite_id=s_uuid,
                model_release_id=r_uuid,
                baseline_release_id=b_uuid,
            )
            gql.db.commit()
            return EvaluationRunResult(
                evaluation_run=EvaluationRunInfo.from_row(run),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return EvaluationRunResult(
                evaluation_run=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LearningMutation.evaluation_suite_create

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.evaluation_suite_create`.

```python
    @strawberry.mutation
    def evaluation_suite_create(
        self, info: strawberry.Info, input: EvaluationSuiteCreateInput
    ) -> EvaluationSuiteResult:
        """Register a versioned suite draft (§18.1) — public contract
        only; hidden targets attach via evaluation_suite_labels."""
        gql = gql_ctx(info)
        try:
            t_uuid = (
                _gid_uuid(input.task_id, "Task", "taskId") if input.task_id is not None else None
            )
            suite = self._eval_service(gql).create_suite(
                name=input.name,
                kind=input.kind,
                task_id=t_uuid,
                tasks=cast(list[dict[str, Any]], input.tasks or []),
                thresholds=cast(list[dict[str, Any]] | None, input.thresholds),
                budget=cast(dict[str, Any] | None, input.budget),
                scoring=cast(dict[str, Any] | None, input.scoring),
                allowed_context=cast(dict[str, Any] | None, input.allowed_context),
                review_rules=cast(dict[str, Any] | None, input.review_rules),
                purpose=input.purpose or "assistant_sft",
            )
            gql.db.commit()
            return EvaluationSuiteResult(
                evaluation_suite=EvaluationSuiteInfo.from_row(suite),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except (DomainError, ValueError) as exc:
            gql.db.rollback()
            payload = (
                _err_payload(exc)
                if isinstance(exc, DomainError)
                else _err_payload(DomainError(ErrorCode.VALIDATION, str(exc)[:300]))
            )
            return EvaluationSuiteResult(
                evaluation_suite=None,
                errors=[payload],
                client_mutation_id=input.client_mutation_id,
            )
```

## LearningMutation.evaluation_suite_freeze

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.evaluation_suite_freeze`.

```python
    @strawberry.mutation
    def evaluation_suite_freeze(
        self, info: strawberry.Info, input: EvaluationSuiteIdInput
    ) -> EvaluationSuiteResult:
        """Freeze the suite: pin the live agent-tool catalog into
        tool_versions and seal the definition digest."""
        gql = gql_ctx(info)
        try:
            s_uuid = _gid_uuid(input.evaluation_suite_id, "EvaluationSuite", "evaluationSuiteId")
            suite = self._eval_service(gql).freeze(s_uuid)
            gql.db.commit()
            return EvaluationSuiteResult(
                evaluation_suite=EvaluationSuiteInfo.from_row(suite),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return EvaluationSuiteResult(
                evaluation_suite=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LearningMutation.evaluation_suite_labels

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.evaluation_suite_labels`.

```python
    @strawberry.mutation
    def evaluation_suite_labels(
        self, info: strawberry.Info, input: EvaluationSuiteLabelsInput
    ) -> EvaluationSuiteResult:
        """Attach hidden targets to a draft suite — write path is
        manage_models; the READ path stays service-principal only."""
        gql = gql_ctx(info)
        try:
            s_uuid = _gid_uuid(input.evaluation_suite_id, "EvaluationSuite", "evaluationSuiteId")
            suite = self._eval_service(gql).set_labels(
                s_uuid, cast(list[dict[str, Any]], input.labels or [])
            )
            gql.db.commit()
            return EvaluationSuiteResult(
                evaluation_suite=EvaluationSuiteInfo.from_row(suite),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except (DomainError, ValueError) as exc:
            gql.db.rollback()
            payload = (
                _err_payload(exc)
                if isinstance(exc, DomainError)
                else _err_payload(DomainError(ErrorCode.VALIDATION, str(exc)[:300]))
            )
            return EvaluationSuiteResult(
                evaluation_suite=None,
                errors=[payload],
                client_mutation_id=input.client_mutation_id,
            )
```

## LearningMutation.model_release_approve

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.model_release_approve`.

```python
    @strawberry.mutation
    def model_release_approve(
        self, info: strawberry.Info, input: ModelReleaseApproveInput
    ) -> ModelReleaseResult:
        """Human grant for a release — ``approve_model`` capability
        only; agents can never call this (grant() enforces it)."""
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.model_release_id, "ModelRelease", "modelReleaseId")
            svc = self._models_service(gql)
            svc.approve(r_uuid, rationale=input.rationale)
            release = svc.get(r_uuid)
            gql.db.commit()
            return self._release_result(release, [], input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return self._release_result(None, [_err_payload(exc)], input.client_mutation_id)
```

## LearningMutation.model_release_convert

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.model_release_convert`.

```python
    @strawberry.mutation
    def model_release_convert(
        self, info: strawberry.Info, input: ModelReleaseConvertInput
    ) -> ModelReleaseResult:
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.model_release_id, "ModelRelease", "modelReleaseId")
            release = self._models_service(gql).convert(
                r_uuid, target_format=input.target_format or "serving-bundle-v1"
            )
            gql.db.commit()
            return self._release_result(release, [], input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return self._release_result(None, [_err_payload(exc)], input.client_mutation_id)
```

## LearningMutation.model_release_promote

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.model_release_promote`.

```python
    @strawberry.mutation
    def model_release_promote(
        self, info: strawberry.Info, input: ModelReleaseIdInput
    ) -> ModelReleaseResult:
        """Atomic approved serving-pointer move (§18.4): one
        transaction re-validates approval + compatibility, supersedes
        the previous release, and moves the pointer."""
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.model_release_id, "ModelRelease", "modelReleaseId")
            release = self._models_service(gql).promote(r_uuid)
            gql.db.commit()
            return self._release_result(release, [], input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return self._release_result(None, [_err_payload(exc)], input.client_mutation_id)
```

## LearningMutation.model_release_register

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.model_release_register`.

```python
    @strawberry.mutation
    def model_release_register(
        self, info: strawberry.Info, input: ModelReleaseRegisterInput
    ) -> ModelReleaseResult:
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.training_run_id, "TrainingRun", "trainingRunId")
            t_uuid = (
                _gid_uuid(input.task_id, "Task", "taskId") if input.task_id is not None else None
            )
            release = self._models_service(gql).register(
                training_run_id=r_uuid,
                name=input.name,
                task_id=t_uuid,
                serving_format=input.serving_format or "peft-adapter",
            )
            gql.db.commit()
            return self._release_result(release, [], input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return self._release_result(None, [_err_payload(exc)], input.client_mutation_id)
```

## LearningMutation.model_release_rollback

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.model_release_rollback`.

```python
    @strawberry.mutation
    def model_release_rollback(
        self, info: strawberry.Info, input: ModelReleaseRollbackInput
    ) -> ModelReleaseResult:
        """Atomic rollback to a known-good release — the pointer moves
        in the same transaction; no schema/data rollback."""
        gql = gql_ctx(info)
        try:
            r_uuid = (
                _gid_uuid(input.model_release_id, "ModelRelease", "modelReleaseId")
                if input.model_release_id is not None
                else None
            )
            release = self._models_service(gql).rollback(r_uuid)
            gql.db.commit()
            return self._release_result(release, [], input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return self._release_result(None, [_err_payload(exc)], input.client_mutation_id)
```

## LearningMutation.model_release_validate

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.model_release_validate`.

```python
    @strawberry.mutation
    def model_release_validate(
        self, info: strawberry.Info, input: ModelReleaseIdInput
    ) -> ModelReleaseResult:
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.model_release_id, "ModelRelease", "modelReleaseId")
            release = self._models_service(gql).validate_release(r_uuid)
            gql.db.commit()
            return self._release_result(release, [], input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return self._release_result(None, [_err_payload(exc)], input.client_mutation_id)
```

## LearningMutation.promotion_approve

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.promotion_approve`.

```python
    @strawberry.mutation
    def promotion_approve(
        self, info: strawberry.Info, input: PromotionApproveInput
    ) -> PromotionDecisionResult:
        """The documented human release decision (§18.3-4): binds
        scope + limitations + the gate verdict into a
        ``model_release_scope`` approval (approve_model capability —
        agents can never grant it)."""
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.model_release_id, "ModelRelease", "modelReleaseId")
            decision = self._promotion_service(gql).approve_scope(
                r_uuid,
                scope=input.scope,
                limitations=input.limitations,
                rationale=input.rationale,
            )
            gql.db.commit()
            return PromotionDecisionResult(
                promotion_decision=PromotionDecisionInfo.from_row(decision),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return PromotionDecisionResult(
                promotion_decision=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LearningMutation.promotion_decide

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.promotion_decide`.

```python
    @strawberry.mutation
    def promotion_decide(
        self, info: strawberry.Info, input: PromotionDecideInput
    ) -> PromotionDecisionResult:
        """Run the §18.4 gate and record the verdict — hard blockers
        refuse promotion; unknown thresholds are stored claim
        blockers, never filled in."""
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.model_release_id, "ModelRelease", "modelReleaseId")
            decision = self._promotion_service(gql).decide(r_uuid)
            gql.db.commit()
            return PromotionDecisionResult(
                promotion_decision=PromotionDecisionInfo.from_row(decision),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return PromotionDecisionResult(
                promotion_decision=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LearningMutation.promotion_promote

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.promotion_promote`.

```python
    @strawberry.mutation
    def promotion_promote(
        self, info: strawberry.Info, input: PromotionPromoteInput
    ) -> PromotionDecisionResult:
        """Gated promotion (§18.4): fresh gate decision → scoped
        approval re-validated → atomic serving-pointer move via the
        CS-0802 registry."""
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.model_release_id, "ModelRelease", "modelReleaseId")
            decision = self._promotion_service(gql).promote(
                r_uuid, scope=input.scope, limitations=input.limitations
            )
            gql.db.commit()
            return PromotionDecisionResult(
                promotion_decision=PromotionDecisionInfo.from_row(decision),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return PromotionDecisionResult(
                promotion_decision=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LearningMutation.session_model_bind

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.session_model_bind`.

```python
    @strawberry.mutation
    def session_model_bind(
        self, info: strawberry.Info, input: SessionModelBindInput
    ) -> SessionBindResult:
        """Serving request for one session — resolves its pinned
        release and requires a fresh compatible verdict
        (AT-0802-1/2)."""
        gql = gql_ctx(info)
        try:
            s_uuid = _gid_uuid(input.session_id, "ResearchSession", "sessionId")
            release, report = self._models_service(gql).bind_session(s_uuid)
            gql.db.commit()
            return SessionBindResult(
                model_release=ModelReleaseInfo.from_row(release),
                validation=JSON(report.model_dump(mode="json")),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return SessionBindResult(
                model_release=None,
                validation=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LearningMutation.snapshot_build

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.snapshot_build`.

```python
    @strawberry.mutation
    def snapshot_build(
        self, info: strawberry.Info, input: DatasetSnapshotBuildInput
    ) -> DatasetSnapshotResult:
        gql = gql_ctx(info)
        try:
            t_uuid = (
                _gid_uuid(input.task_id, "Task", "taskId") if input.task_id is not None else None
            )
            snap = DatasetService(gql.db, gql.service_ctx()).build(
                purpose=input.purpose, name=input.name, task_id=t_uuid
            )
            gql.db.commit()
            return DatasetSnapshotResult(
                snapshot=DatasetSnapshotInfo.from_row(snap),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return DatasetSnapshotResult(
                snapshot=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LearningMutation.snapshot_freeze

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.snapshot_freeze`.

```python
    @strawberry.mutation
    def snapshot_freeze(
        self, info: strawberry.Info, input: DatasetSnapshotIdInput
    ) -> DatasetSnapshotResult:
        gql = gql_ctx(info)
        try:
            s_uuid = _gid_uuid(input.snapshot_id, "DatasetSnapshot", "snapshotId")
            snap = DatasetService(gql.db, gql.service_ctx()).freeze(s_uuid)
            gql.db.commit()
            return DatasetSnapshotResult(
                snapshot=DatasetSnapshotInfo.from_row(snap),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return DatasetSnapshotResult(
                snapshot=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LearningMutation.snapshot_prepare_run

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.snapshot_prepare_run`.

```python
    @strawberry.mutation
    def snapshot_prepare_run(
        self, info: strawberry.Info, input: DatasetSnapshotIdInput
    ) -> DatasetPrepareResult:
        gql = gql_ctx(info)
        try:
            s_uuid = _gid_uuid(input.snapshot_id, "DatasetSnapshot", "snapshotId")
            report = DatasetService(gql.db, gql.service_ctx()).prepare_run(s_uuid)
            gql.db.commit()
            return DatasetPrepareResult(
                report=JSON(report),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return DatasetPrepareResult(
                report=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## LearningMutation.training_run_approve

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.training_run_approve`.

```python
    @strawberry.mutation
    def training_run_approve(
        self, info: strawberry.Info, input: TrainingRunApproveInput
    ) -> TrainingRunResult:
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.training_run_id, "TrainingRun", "trainingRunId")
            run = self._training_service(gql).approve(
                r_uuid, decision=input.decision, rationale=input.rationale
            )
            gql.db.commit()
            return self._training_result(gql, run, [], input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return self._training_result(gql, None, [_err_payload(exc)], input.client_mutation_id)
```

## LearningMutation.training_run_cancel

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.training_run_cancel`.

```python
    @strawberry.mutation
    def training_run_cancel(
        self, info: strawberry.Info, input: TrainingRunIdInput
    ) -> TrainingRunResult:
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.training_run_id, "TrainingRun", "trainingRunId")
            run = self._training_service(gql).cancel(r_uuid)
            gql.db.commit()
            return self._training_result(gql, run, [], input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return self._training_result(gql, None, [_err_payload(exc)], input.client_mutation_id)
```

## LearningMutation.training_run_create

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.training_run_create`.

```python
    @strawberry.mutation
    def training_run_create(
        self, info: strawberry.Info, input: TrainingRunCreateInput
    ) -> TrainingRunResult:
        gql = gql_ctx(info)
        try:
            s_uuid = _gid_uuid(input.snapshot_id, "DatasetSnapshot", "snapshotId")
            t_uuid = (
                _gid_uuid(input.task_id, "Task", "taskId") if input.task_id is not None else None
            )
            run = self._training_service(gql).create(
                snapshot_id=s_uuid,
                name=input.name,
                task_id=t_uuid,
                spec=cast(dict[str, Any] | None, input.spec),
            )
            gql.db.commit()
            return self._training_result(gql, run, [], input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return self._training_result(gql, None, [_err_payload(exc)], input.client_mutation_id)
```

## LearningMutation.training_run_execute

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.training_run_execute`.

```python
    @strawberry.mutation
    def training_run_execute(
        self, info: strawberry.Info, input: TrainingRunExecuteInput
    ) -> TrainingRunResult:
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.training_run_id, "TrainingRun", "trainingRunId")
            a_uuid = _gid_uuid(input.attempt_id, "RunAttempt", "attemptId")
            run = self._training_service(gql).execute(r_uuid, a_uuid)
            gql.db.commit()
            return self._training_result(gql, run, [], input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return self._training_result(gql, None, [_err_payload(exc)], input.client_mutation_id)
```

## LearningMutation.training_run_queue

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.training_run_queue`.

```python
    @strawberry.mutation
    def training_run_queue(
        self, info: strawberry.Info, input: TrainingRunIdInput
    ) -> TrainingRunResult:
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.training_run_id, "TrainingRun", "trainingRunId")
            run = self._training_service(gql).queue(r_uuid)
            gql.db.commit()
            return self._training_result(gql, run, [], input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return self._training_result(gql, None, [_err_payload(exc)], input.client_mutation_id)
```

## LearningMutation.training_run_resume

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.training_run_resume`.

```python
    @strawberry.mutation
    def training_run_resume(
        self, info: strawberry.Info, input: TrainingRunIdInput
    ) -> TrainingRunResult:
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.training_run_id, "TrainingRun", "trainingRunId")
            run = self._training_service(gql).resume(r_uuid)
            gql.db.commit()
            return self._training_result(gql, run, [], input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return self._training_result(gql, None, [_err_payload(exc)], input.client_mutation_id)
```

## LearningMutation.training_run_submit

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.training_run_submit`.

```python
    @strawberry.mutation
    def training_run_submit(
        self, info: strawberry.Info, input: TrainingRunIdInput
    ) -> TrainingRunResult:
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.training_run_id, "TrainingRun", "trainingRunId")
            run = self._training_service(gql).submit(r_uuid)
            gql.db.commit()
            return self._training_result(gql, run, [], input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return self._training_result(gql, None, [_err_payload(exc)], input.client_mutation_id)
```

## LearningMutation.training_run_transition

Source: `services/studio-api/src/studio/api/graphql/schema.py:LearningMutation.training_run_transition`.

```python
    @strawberry.mutation
    def training_run_transition(
        self, info: strawberry.Info, input: TrainingRunTransitionInput
    ) -> TrainingRunResult:
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.training_run_id, "TrainingRun", "trainingRunId")
            run = self._training_service(gql).transition(
                r_uuid, to_state=input.to_state, rationale=input.rationale
            )
            gql.db.commit()
            return self._training_result(gql, run, [], input.client_mutation_id)
        except DomainError as exc:
            gql.db.rollback()
            return self._training_result(gql, None, [_err_payload(exc)], input.client_mutation_id)
```

## MaterialsMutation.grade_create

Source: `services/studio-api/src/studio/api/graphql/schema.py:MaterialsMutation.grade_create`.

```python
    @strawberry.mutation
    def grade_create(
        self, info: strawberry.Info, input: MaterialGradeCreateInput
    ) -> MaterialGradeResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            m_uuid = _gid_uuid(input.material_id, "MaterialIdentity", "materialId")
            payload = {
                "materialId": str(m_uuid),
                "supplier": input.supplier,
                "gradeName": input.grade_name,
                "activeContent": input.active_content,
                "specifications": input.specifications,
            }

            def _do() -> dict[str, str]:
                row = svc.create_grade(
                    material_id=m_uuid,
                    supplier=input.supplier,
                    grade_name=input.grade_name,
                    active_content=cast(dict[str, Any], input.active_content)
                    if input.active_content is not None
                    else None,
                    specifications=cast(dict[str, Any], input.specifications)
                    if input.specifications is not None
                    else None,
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="material.grade_create",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(GradeRow, uuid.UUID(result["id"]))
            return MaterialGradeResult(
                grade=MaterialGrade.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return MaterialGradeResult(
                grade=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## MaterialsMutation.grade_reconcile

Source: `services/studio-api/src/studio/api/graphql/schema.py:MaterialsMutation.grade_reconcile`.

```python
    @strawberry.mutation
    def grade_reconcile(
        self, info: strawberry.Info, input: MaterialGradeReconcileInput
    ) -> MaterialGradeResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            keep = _gid_uuid(input.keep_grade_id, "MaterialGrade", "keepGradeId")
            merge = _gid_uuid(input.merge_grade_id, "MaterialGrade", "mergeGradeId")

            def _do() -> dict[str, str]:
                row = svc.reconcile_grades(
                    keep_grade_id=keep, merge_grade_id=merge, reason=input.reason
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="material.grade_reconcile",
                payload={"keep": str(keep), "merge": str(merge), "reason": input.reason},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(GradeRow, uuid.UUID(result["id"]))
            return MaterialGradeResult(
                grade=MaterialGrade.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return MaterialGradeResult(
                grade=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## MaterialsMutation.identity_create

Source: `services/studio-api/src/studio/api/graphql/schema.py:MaterialsMutation.identity_create`.

```python
    @strawberry.mutation
    def identity_create(
        self, info: strawberry.Info, input: MaterialIdentityCreateInput
    ) -> MaterialIdentityResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            payload = {
                "kind": input.kind,
                "name": input.name,
                "identifiers": input.identifiers,
                "aliases": input.aliases,
                "structure": input.structure,
                "structureFormat": input.structure_format,
                "confidentiality": input.confidentiality,
            }

            def _do() -> dict[str, str]:
                row = svc.create_identity(
                    kind=input.kind,
                    name=input.name,
                    identifiers=cast(list[dict[str, Any]], input.identifiers)
                    if input.identifiers is not None
                    else None,
                    aliases=cast(list[dict[str, Any]], input.aliases)
                    if input.aliases is not None
                    else None,
                    structure=input.structure,
                    structure_format=input.structure_format,
                    confidentiality=input.confidentiality,
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="material.identity_create",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(MaterialRow, uuid.UUID(result["id"]))
            return MaterialIdentityResult(
                identity=MaterialIdentity.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return MaterialIdentityResult(
                identity=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## MaterialsMutation.match_propose

Source: `services/studio-api/src/studio/api/graphql/schema.py:MaterialsMutation.match_propose`.

```python
    @strawberry.mutation
    def match_propose(
        self, info: strawberry.Info, input: MaterialMatchProposeInput
    ) -> MaterialIdentityResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            s_uuid = _gid_uuid(input.source_identity_id, "MaterialIdentity", "sourceIdentityId")
            c_uuid = _gid_uuid(
                input.candidate_identity_id, "MaterialIdentity", "candidateIdentityId"
            )

            def _do() -> dict[str, str]:
                svc.propose_match(
                    source_identity_id=s_uuid,
                    candidate_identity_id=c_uuid,
                    confidence=input.confidence,
                    rationale=input.rationale,
                    proposed_by=input.proposed_by,
                )
                return {"id": str(s_uuid)}

            result = _mutate(
                gql,
                key=None,
                operation="material.match_propose",
                payload={"source": str(s_uuid), "candidate": str(c_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(MaterialRow, uuid.UUID(result["id"]))
            return MaterialIdentityResult(
                identity=MaterialIdentity.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return MaterialIdentityResult(
                identity=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## MaterialsMutation.match_review

Source: `services/studio-api/src/studio/api/graphql/schema.py:MaterialsMutation.match_review`.

```python
    @strawberry.mutation
    def match_review(
        self, info: strawberry.Info, input: MaterialMatchReviewInput
    ) -> MaterialIdentityResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            m_uuid = _gid_uuid(input.match_id, "IdentityMatch", "matchId")

            def _do() -> dict[str, str]:
                row = svc.review_match(
                    match_id=m_uuid, decision=input.decision, rationale=input.rationale
                )
                return {"id": str(row.source_identity_id)}

            result = _mutate(
                gql,
                key=None,
                operation="material.match_review",
                payload={"matchId": str(m_uuid), "decision": input.decision},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(MaterialRow, uuid.UUID(result["id"]))
            return MaterialIdentityResult(
                identity=MaterialIdentity.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return MaterialIdentityResult(
                identity=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## MaterialsMutation.reference_product_create

Source: `services/studio-api/src/studio/api/graphql/schema.py:MaterialsMutation.reference_product_create`.

```python
    @strawberry.mutation
    def reference_product_create(
        self, info: strawberry.Info, input: ReferenceProductCreateInput
    ) -> ReferenceProductResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            payload = {
                "name": input.name,
                "supplier": input.supplier,
                "category": input.category,
                "compositionKnowledge": input.composition_knowledge,
                "aliases": input.aliases,
            }

            def _do() -> dict[str, str]:
                row = svc.create_reference_product(
                    name=input.name,
                    supplier=input.supplier,
                    category=input.category,
                    composition_knowledge=input.composition_knowledge,
                    aliases=cast(list[dict[str, Any]], input.aliases)
                    if input.aliases is not None
                    else None,
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="material.reference_create",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(RefProductRow, uuid.UUID(result["id"]))
            return ReferenceProductResult(
                product=ReferenceProduct.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ReferenceProductResult(
                product=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## MaterialsMutation.reference_revision_draft

Source: `services/studio-api/src/studio/api/graphql/schema.py:MaterialsMutation.reference_revision_draft`.

```python
    @strawberry.mutation
    def reference_revision_draft(
        self, info: strawberry.Info, input: ReferenceRevisionDraftInput
    ) -> ReferenceRevisionResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            p_uuid = _gid_uuid(input.product_id, "ReferenceProduct", "productId")
            payload = {"productId": str(p_uuid), "payload": input.payload}

            def _do() -> dict[str, str]:
                row = svc.draft_reference_revision(
                    product_id=p_uuid, payload=cast(dict[str, Any], input.payload)
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="material.ref_rev_draft",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(RefRevRow, uuid.UUID(result["id"]))
            return ReferenceRevisionResult(
                revision=ReferenceProductRevision.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ReferenceRevisionResult(
                revision=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## MaterialsMutation.reference_revision_freeze

Source: `services/studio-api/src/studio/api/graphql/schema.py:MaterialsMutation.reference_revision_freeze`.

```python
    @strawberry.mutation
    def reference_revision_freeze(
        self, info: strawberry.Info, input: ReferenceRevisionFreezeInput
    ) -> ReferenceRevisionResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            r_uuid = _gid_uuid(input.revision_id, "ReferenceProductRevision", "revisionId")

            def _do() -> dict[str, str]:
                row = svc.freeze_reference_revision(revision_id=r_uuid)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="material.ref_rev_freeze",
                payload={"revisionId": str(r_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(RefRevRow, uuid.UUID(result["id"]))
            return ReferenceRevisionResult(
                revision=ReferenceProductRevision.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ReferenceRevisionResult(
                revision=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## MaterialsMutation.structure_review

Source: `services/studio-api/src/studio/api/graphql/schema.py:MaterialsMutation.structure_review`.

```python
    @strawberry.mutation
    def structure_review(
        self, info: strawberry.Info, input: MaterialStructureReviewInput
    ) -> MaterialIdentityResult:
        gql = gql_ctx(info)
        try:
            svc = MaterialService(gql.db, gql.service_ctx())
            i_uuid = _gid_uuid(input.identity_id, "MaterialIdentity", "identityId")

            def _do() -> dict[str, str]:
                row = svc.review_structure(identity_id=i_uuid)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="material.structure_review",
                payload={"identityId": str(i_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(MaterialRow, uuid.UUID(result["id"]))
            return MaterialIdentityResult(
                identity=MaterialIdentity.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return MaterialIdentityResult(
                identity=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## OptimizationMutation.command

Source: `services/studio-api/src/studio/api/graphql/schema.py:OptimizationMutation.command`.

```python
    @strawberry.mutation
    def command(self, info: strawberry.Info, input: OptimizationCommandInput) -> OptimizationResult:
        from studio.domain.learning.optimization import OptimizationService

        gql = gql_ctx(info)
        try:
            row = OptimizationService(gql.db, gql.service_ctx(), gql.settings).command(
                _gid_uuid(input.campaign_id, "OptimizationCampaign", "campaignId"),
                expected_revision=input.expected_revision,
                key=input.idempotency_key,
                operation=input.operation.value,
                batch_size=input.batch_size,
                experiment_id=input.experiment_id,
                measurement_id=_gid_uuid(input.measurement_id, "Measurement", "measurementId")
                if input.measurement_id
                else None,
                snapshot_id=_gid_uuid(input.snapshot_id, "DatasetSnapshot", "snapshotId")
                if input.snapshot_id
                else None,
                reason=input.reason,
            )
            gql.db.commit()
            task = gql.db.get(TaskRow, row.task_id)
            return OptimizationResult(
                task=Task.from_row(task) if task else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return OptimizationResult(
                task=None, errors=[_err_payload(exc)], client_mutation_id=input.client_mutation_id
            )
```

## OptimizationMutation.create

Source: `services/studio-api/src/studio/api/graphql/schema.py:OptimizationMutation.create`.

```python
    @strawberry.mutation
    def create(self, info: strawberry.Info, input: OptimizationCreateInput) -> OptimizationResult:
        from studio.domain.learning.optimization import OptimizationService

        gql = gql_ctx(info)
        try:
            if not isinstance(input.definition, dict):
                raise DomainError(ErrorCode.VALIDATION, "definition must be an object")
            row = OptimizationService(gql.db, gql.service_ctx(), gql.settings).create(
                _gid_uuid(input.task_id, "Task", "taskId"), input.definition, input.idempotency_key
            )
            gql.db.commit()
            task = gql.db.get(TaskRow, row.task_id)
            return OptimizationResult(
                task=Task.from_row(task) if task else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return OptimizationResult(
                task=None, errors=[_err_payload(exc)], client_mutation_id=input.client_mutation_id
            )
```

## ProviderMutation.cleanup_credentials

Source: `services/studio-api/src/studio/api/graphql/schema.py:ProviderMutation.cleanup_credentials`.

```python
    @strawberry.mutation
    def cleanup_credentials(self, info: strawberry.Info) -> InferenceCredentialCleanupResult:
        gql = gql_ctx(info)
        try:
            pending = ProviderService(gql.db, gql.service_ctx()).cleanup_credentials()
            return InferenceCredentialCleanupResult(pending=pending, errors=[])
        except (DomainError, SQLAlchemyError) as exc:
            gql.db.rollback()
            error = (
                exc
                if isinstance(exc, DomainError)
                else DomainError(
                    ErrorCode.CONFLICT,
                    "credential cleanup could not be completed; retry after unlocking Keychain",
                )
            )
            return InferenceCredentialCleanupResult(pending=True, errors=[_err_payload(error)])
```

## ProviderMutation.delete

Source: `services/studio-api/src/studio/api/graphql/schema.py:ProviderMutation.delete`.

```python
    @strawberry.mutation
    def delete(
        self, info: strawberry.Info, input: InferenceProviderDeleteInput
    ) -> InferenceProviderDeleteResult:
        gql = gql_ctx(info)
        try:
            pending = ProviderService(gql.db, gql.service_ctx()).delete(
                _provider_uuid(input.id), input.expected_revision
            )
            return InferenceProviderDeleteResult(
                deleted=True,
                credential_cleanup_pending=pending,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except (DomainError, SQLAlchemyError) as exc:
            gql.db.rollback()
            error = (
                exc
                if isinstance(exc, DomainError)
                else DomainError(
                    ErrorCode.CONFLICT, "provider could not be removed; reload and retry"
                )
            )
            return InferenceProviderDeleteResult(
                deleted=False,
                credential_cleanup_pending=False,
                errors=[_err_payload(error)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ProviderMutation.save

Source: `services/studio-api/src/studio/api/graphql/schema.py:ProviderMutation.save`.

```python
    @strawberry.mutation
    def save(
        self, info: strawberry.Info, input: InferenceProviderSaveInput
    ) -> InferenceProviderResult:
        gql = gql_ctx(info)
        try:
            # Deliberately no generic idempotency/audit payload containing a
            # write-only API key. Metadata uses revision compare-and-swap.
            row = ProviderService(gql.db, gql.service_ctx()).save(
                provider_id=_provider_uuid(input.id) if input.id else None,
                expected_revision=input.expected_revision,
                name=input.name,
                kind=input.kind,
                base_url=input.base_url,
                model=input.model,
                api_style=input.api_style,
                enabled=input.enabled,
                supports_tools=input.supports_tools,
                api_key=input.api_key,
                clear_api_key=input.clear_api_key,
                client_mutation_id=input.client_mutation_id,
            )
            return InferenceProviderResult(
                provider=InferenceProviderInfo.from_row(row),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except (DomainError, SQLAlchemyError) as exc:
            gql.db.rollback()
            error = (
                exc
                if isinstance(exc, DomainError)
                else DomainError(
                    ErrorCode.CONFLICT, "provider settings could not be committed; reload and retry"
                )
            )
            return InferenceProviderResult(
                provider=None,
                errors=[_err_payload(error)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ProviderMutation.test

Source: `services/studio-api/src/studio/api/graphql/schema.py:ProviderMutation.test`.

```python
    @strawberry.mutation
    def test(
        self, info: strawberry.Info, input: InferenceProviderTestInput
    ) -> InferenceProviderTestResult:
        gql = gql_ctx(info)
        try:
            row = ProviderService(gql.db, gql.service_ctx()).test(_provider_uuid(input.id))
            return InferenceProviderTestResult(
                provider=InferenceProviderInfo.from_row(row),
                status=row.last_test_status,
                detail=row.last_test_detail or "",
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except (DomainError, SQLAlchemyError) as exc:
            gql.db.rollback()
            error = (
                exc
                if isinstance(exc, DomainError)
                else DomainError(ErrorCode.CONFLICT, "provider probe could not be recorded; retry")
            )
            return InferenceProviderTestResult(
                provider=None,
                status="failed",
                detail=error.message,
                errors=[_err_payload(error)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ResearchMutation.message_post

Source: `services/studio-api/src/studio/api/graphql/schema.py:ResearchMutation.message_post`.

```python
    @strawberry.mutation
    def message_post(self, info: strawberry.Info, input: MessagePostInput) -> SessionMessageResult:
        gql = gql_ctx(info)
        try:
            s_uuid = _gid_uuid(input.session_id, "ResearchSession", "sessionId")
            payload = {
                "sessionId": str(s_uuid),
                "role": input.role,
                "kind": input.kind,
                "content": input.content,
            }

            def _do() -> dict[str, str]:
                row = TaskMemoryService(gql.db, gql.service_ctx()).post_message(
                    s_uuid,
                    role=input.role,
                    kind=input.kind or "message",
                    content=input.content,
                    refs=cast(dict[str, Any], input.refs) if input.refs else None,
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="research.message_post",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(SessionMessageRow, uuid.UUID(result["id"]))
            return SessionMessageResult(
                message=SessionMessage.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return SessionMessageResult(
                message=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ResearchMutation.question_raise

Source: `services/studio-api/src/studio/api/graphql/schema.py:ResearchMutation.question_raise`.

```python
    @strawberry.mutation
    def question_raise(
        self, info: strawberry.Info, input: QuestionRaiseInput
    ) -> TaskQuestionResult:
        gql = gql_ctx(info)
        try:
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")
            payload = {"taskId": str(t_uuid), "question": input.question}

            def _do() -> dict[str, str]:
                row = TaskMemoryService(gql.db, gql.service_ctx()).raise_question(
                    t_uuid, question=input.question, blocking=bool(input.blocking)
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="research.question_raise",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(TaskQuestionRow, uuid.UUID(result["id"]))
            return TaskQuestionResult(
                question=TaskQuestion.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return TaskQuestionResult(
                question=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ResearchMutation.question_resolve

Source: `services/studio-api/src/studio/api/graphql/schema.py:ResearchMutation.question_resolve`.

```python
    @strawberry.mutation
    def question_resolve(
        self, info: strawberry.Info, input: QuestionResolveInput
    ) -> TaskQuestionResult:
        gql = gql_ctx(info)
        try:
            q_uuid = _gid_uuid(input.question_id, "TaskQuestion", "questionId")

            def _do() -> dict[str, str]:
                row = TaskMemoryService(gql.db, gql.service_ctx()).resolve_question(
                    q_uuid, resolution=input.resolution
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="research.question_resolve",
                payload={"questionId": str(q_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(TaskQuestionRow, uuid.UUID(result["id"]))
            return TaskQuestionResult(
                question=TaskQuestion.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return TaskQuestionResult(
                question=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ResearchMutation.session_end

Source: `services/studio-api/src/studio/api/graphql/schema.py:ResearchMutation.session_end`.

```python
    @strawberry.mutation
    def session_end(self, info: strawberry.Info, input: SessionEndInput) -> ResearchSessionResult:
        gql = gql_ctx(info)
        try:
            s_uuid = _gid_uuid(input.session_id, "ResearchSession", "sessionId")

            def _do() -> dict[str, str]:
                row = TaskMemoryService(gql.db, gql.service_ctx()).end_session(s_uuid)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="research.session_end",
                payload={"sessionId": str(s_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(ResearchSessionRow, uuid.UUID(result["id"]))
            return ResearchSessionResult(
                session=ResearchSession.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ResearchSessionResult(
                session=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ResearchMutation.session_start

Source: `services/studio-api/src/studio/api/graphql/schema.py:ResearchMutation.session_start`.

```python
    @strawberry.mutation
    def session_start(
        self, info: strawberry.Info, input: SessionStartInput
    ) -> ResearchSessionResult:
        gql = gql_ctx(info)
        try:
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")
            payload = {"taskId": str(t_uuid), "tokenBudget": input.token_budget}

            def _do() -> dict[str, str]:
                kwargs: dict[str, Any] = {}
                if input.token_budget is not None:
                    kwargs["token_budget"] = input.token_budget
                row = TaskMemoryService(gql.db, gql.service_ctx()).start_session(t_uuid, **kwargs)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="research.session_start",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(ResearchSessionRow, uuid.UUID(result["id"]))
            return ResearchSessionResult(
                session=ResearchSession.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return ResearchSessionResult(
                session=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ResearchMutation.summary_create

Source: `services/studio-api/src/studio/api/graphql/schema.py:ResearchMutation.summary_create`.

```python
    @strawberry.mutation
    def summary_create(self, info: strawberry.Info, input: SummaryCreateInput) -> TaskSummaryResult:
        gql = gql_ctx(info)
        try:
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")
            payload = {"taskId": str(t_uuid), "generator": input.generator}

            def _do() -> dict[str, str]:
                row = TaskMemoryService(gql.db, gql.service_ctx()).create_summary(
                    t_uuid,
                    body=input.body,
                    source_ids=list(input.source_ids),
                    generator=input.generator,
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key,
                operation="research.summary_create",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            return TaskSummaryResult(
                summary_id=result["id"],
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return TaskSummaryResult(
                summary_id=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ResearchMutation.turn_cancel

Source: `services/studio-api/src/studio/api/graphql/schema.py:ResearchMutation.turn_cancel`.

```python
    @strawberry.mutation
    def turn_cancel(self, info: strawberry.Info, input: TurnCancelInput) -> TurnCancelResult:
        """Record a cancel marker the running turn observes between
        tool-loop iterations. A late cancel on a finished turn is an
        inert record, not an error — the marker itself is durable."""
        gql = gql_ctx(info)
        try:
            s_uuid = _gid_uuid(input.session_id, "ResearchSession", "sessionId")
            payload = {"sessionId": str(s_uuid), "turnId": input.turn_id}

            def _do() -> dict[str, str]:
                row = TaskMemoryService(gql.db, gql.service_ctx()).post_message(
                    s_uuid,
                    role="user",
                    kind="message",
                    content="cancel requested",
                    refs={"turn_cancel": input.turn_id},
                )
                return {"id": str(row.id)}

            _mutate(
                gql,
                key=input.idempotency_key or f"turn-cancel:{input.turn_id}",
                operation="research.turn_cancel",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            return TurnCancelResult(
                recorded=True,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return TurnCancelResult(
                recorded=False,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## ResearchMutation.turn_request

Source: `services/studio-api/src/studio/api/graphql/schema.py:ResearchMutation.turn_request`.

```python
    @strawberry.mutation
    async def turn_request(
        self, info: strawberry.Info, input: TurnRequestInput
    ) -> TurnRequestResult:
        """Run one explicitly routed, bounded research turn off the ASGI loop."""
        gql = gql_ctx(info)
        try:
            from studio.application.agent_tools.requests import run_research_turn

            ctx = gql.service_ctx()
            turn_id = input.turn_id.strip()
            result = await run_in_threadpool(
                run_research_turn,
                gql.request.app.state.session_factory,
                workspace_id=ctx.workspace_id,
                principal_id=ctx.principal_id,
                auth_session_id=ctx.auth_session_id,
                session_id=_gid_uuid(input.session_id, "ResearchSession", "sessionId"),
                content=input.content,
                turn_id=turn_id,
                idempotency_key=input.idempotency_key,
                provider_id=_provider_uuid(input.provider_id) if input.provider_id else None,
                provider_revision=input.provider_revision,
                allow_provider_data_transfer=input.allow_provider_data_transfer,
            )
            final = result.get("finalMessageId")
            row = gql.db.get(SessionMessageRow, uuid.UUID(final)) if final else None
            return TurnRequestResult(
                turn_id=turn_id,
                finished_reason=result.get("finishedReason"),
                final_message=SessionMessage.from_row(row) if row else None,
                tool_calls=int(result.get("toolCalls") or 0),
                detail=result.get("detail"),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except (DomainError, SQLAlchemyError) as exc:
            gql.db.rollback()
            error = (
                exc
                if isinstance(exc, DomainError)
                else DomainError(
                    ErrorCode.CONFLICT,
                    "research turn could not be committed; retry with the same turn id",
                )
            )
            return TurnRequestResult(
                turn_id=None,
                finished_reason=None,
                final_message=None,
                tool_calls=0,
                detail=None,
                errors=[_err_payload(error)],
                client_mutation_id=input.client_mutation_id,
            )
```

## RunsMutation.describe_structure

Source: `services/studio-api/src/studio/api/graphql/schema.py:RunsMutation.describe_structure`.

```python
    @strawberry.mutation
    async def describe_structure(
        self, info: strawberry.Info, input: DescribeStructureInput
    ) -> RunResult:
        gql = gql_ctx(info)
        try:
            task_id = _gid_uuid(input.task_id, "Task", "taskId")
            ctx = gql.service_ctx()
            ctx.require(CAP_REQUEST_COMPUTE, task_id)
            # Each worker owns its sessions. The engine never blocks the ASGI loop.
            service = StructureRunService(gql.request.app.state.session_factory, gql.settings)
            run_id = await run_in_threadpool(
                service.describe,
                ctx.workspace_id,
                ctx.principal_id,
                ctx.auth_session_id,
                task_id,
                input.smiles,
                input.idempotency_key,
            )
            row = gql.db.get(RunRow, run_id)
            return RunResult(
                run=RunNode.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return RunResult(
                run=None, errors=[_err_payload(exc)], client_mutation_id=input.client_mutation_id
            )
```

## RunsMutation.quick_describe_structure

Source: `services/studio-api/src/studio/api/graphql/schema.py:RunsMutation.quick_describe_structure`.

```python
    @strawberry.mutation
    async def quick_describe_structure(
        self, info: strawberry.Info, input: QuickDescribeStructureInput
    ) -> RunResult:
        gql = gql_ctx(info)
        try:
            ctx = gql.service_ctx()
            ctx.require(CAP_REQUEST_COMPUTE)
            project_id = (
                _gid_uuid(input.project_id, "Project", "projectId") if input.project_id else None
            )
            service = StructureRunService(gql.request.app.state.session_factory, gql.settings)
            run_id = await run_in_threadpool(
                service.quick_describe,
                ctx.workspace_id,
                ctx.principal_id,
                ctx.auth_session_id,
                input.smiles,
                input.idempotency_key,
                project_id,
            )
            row = gql.db.get(RunRow, run_id)
            return RunResult(
                run=RunNode.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return RunResult(
                run=None, errors=[_err_payload(exc)], client_mutation_id=input.client_mutation_id
            )
```

## RunsMutation.request

Source: `services/studio-api/src/studio/api/graphql/schema.py:RunsMutation.request`.

```python
    @strawberry.mutation
    def request(self, info: strawberry.Info, input: RunRequestInput) -> RunResult:
        gql = gql_ctx(info)
        try:
            t_uuid = _gid_uuid(input.task_id, "Task", "taskId")
            payload = {"taskId": str(t_uuid), "kind": input.kind}

            def _do() -> dict[str, str]:
                kwargs: dict[str, Any] = {}
                if input.max_attempts is not None:
                    kwargs["max_attempts"] = input.max_attempts
                row = RunService(gql.db, gql.service_ctx()).request(
                    kind=input.kind,
                    request=cast(dict[str, Any], input.request) if input.request else {},
                    task_id=t_uuid,
                    requires_approval=input.requires_approval,
                    **kwargs,
                )
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=input.idempotency_key or None,
                operation="runs.request",
                payload=payload,
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(RunRow, uuid.UUID(result["id"]))
            return RunResult(
                run=RunNode.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return RunResult(
                run=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## RunsMutation.request_cancel

Source: `services/studio-api/src/studio/api/graphql/schema.py:RunsMutation.request_cancel`.

```python
    @strawberry.mutation
    def request_cancel(self, info: strawberry.Info, input: RunCancelInput) -> RunResult:
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.run_id, "Run", "runId")

            def _do() -> dict[str, str]:
                row = RunService(gql.db, gql.service_ctx()).request_cancel(r_uuid)
                return {"id": str(row.id)}

            result = _mutate(
                gql,
                key=None,
                operation="runs.request_cancel",
                payload={"runId": str(r_uuid)},
                fn=_do,
            )
            gql.db.commit()
            row = gql.db.get(RunRow, uuid.UUID(result["id"]))
            return RunResult(
                run=RunNode.from_row(row) if row else None,
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return RunResult(
                run=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## RunsMutation.request_fallback

Source: `services/studio-api/src/studio/api/graphql/schema.py:RunsMutation.request_fallback`.

```python
    @strawberry.mutation
    def request_fallback(self, info: strawberry.Info, input: RunFallbackInput) -> FallbackResult:
        """Evaluate local feasibility and apply the fallback policy
        (§20.1-20.2, CS-1001). Feasible runs are untouched; infeasible
        runs get a persisted evidence report plus an inert export-review
        proposal — never a submission, transfer or spend (AT-1001-3)."""
        gql = gql_ctx(info)
        try:
            r_uuid = _gid_uuid(input.run_id, "Run", "runId")
            service = FeasibilityService(gql.db, gql.service_ctx())
            decision = service.request_fallback(r_uuid)
            gql.db.commit()
            view = service.fallback_view(r_uuid)
            row = gql.db.get(RunRow, r_uuid)
            return FallbackResult(
                run=RunNode.from_row(row) if row else None,
                decision=decision.decision,
                cloud_authorized=decision.cloud_authorized,
                report=JSON(view["report"]) if view["report"] else None,
                proposal=JSON(view["proposal"]) if view["proposal"] else None,
                cloud=JSON(view["cloud"]),
                errors=[],
                client_mutation_id=input.client_mutation_id,
            )
        except DomainError as exc:
            gql.db.rollback()
            return FallbackResult(
                run=None,
                decision=None,
                cloud_authorized=False,
                report=None,
                proposal=None,
                cloud=None,
                errors=[_err_payload(exc)],
                client_mutation_id=input.client_mutation_id,
            )
```

## AgentWorkspaceService.create_run

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.create_run`.

```python
    def create_run(self, thread_id: uuid.UUID, payload: dict[str, Any]) -> dict[str, Any]:
        thread = self._owned(AgentThread, thread_id, lock=True)
        from studio.domain.agent_workspace.workflows import ResearchWorkflow, WorkflowService

        workflow = self.db.scalar(
            select(ResearchWorkflow).where(
                ResearchWorkflow.thread_id == thread_id,
                ResearchWorkflow.workspace_id == self.ctx.workspace_id,
                ResearchWorkflow.owner_id == self.ctx.principal_id,
            )
        )
        if payload.get("workflowId"):
            workflow = WorkflowService(self.db, self.ctx).get(payload["workflowId"])
            if workflow.thread_id != thread_id:
                raise DomainError(
                    ErrorCode.FORBIDDEN, "Workflow belongs to a different conversation"
                )
        existing = self.db.scalar(
            select(AgentRun.id).where(
                AgentRun.thread_id == thread_id,
                AgentRun.workspace_id == self.ctx.workspace_id,
                AgentRun.owner_id == self.ctx.principal_id,
                AgentRun.status.in_(["queued", "running"]),
            )
        )
        if existing:
            raise DomainError(ErrorCode.CONFLICT, "a run is already active in this thread")
        prompt = payload.get("message")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 32000:
            raise DomainError(ErrorCode.VALIDATION, "message must contain 1-32000 characters")
        role = payload.get("role", "planner")
        if role not in ROLES:
            raise DomainError(ErrorCode.VALIDATION, "invalid agent role")
        provider_id = (
            ident(payload["providerId"])
            if payload.get("providerId")
            else (workflow.provider_id if workflow and not payload.get("localModelId") else None)
        )
        model_id, provider_revision = None, None
        local_model_id = ident(payload["localModelId"]) if payload.get("localModelId") else None
        if provider_id and local_model_id:
            raise DomainError(
                ErrorCode.VALIDATION, "select a provider model or private local model"
            )
        local_fingerprint = None
        if local_model_id:
            from studio.domain.learning.workspace_runtime.models import LearningModel

            if workflow:
                WorkflowService(self.db, self.ctx).require_resource(
                    workflow, "model", local_model_id
                )

            local_model = self.db.scalar(
                select(LearningModel).where(
                    LearningModel.id == local_model_id,
                    LearningModel.workspace_id == self.ctx.workspace_id,
                    LearningModel.owner_id == self.ctx.principal_id,
                )
            )
            if local_model is None:
                raise not_found("private local model")
            if local_model.backend not in {"mlx", "transformers"}:
                raise DomainError(
                    ErrorCode.VALIDATION, "this model backend cannot run the research agent"
                )
            local_fingerprint = hashlib.sha256(
                json.dumps(
                    {"location": local_model.location, "details": local_model.details},
                    sort_keys=True,
                    default=str,
                ).encode()
            ).hexdigest()
            model_id = str(local_model.id)
        if provider_id:
            provider = ProviderService(self.db, self.ctx).get(provider_id)
            if not provider.enabled:
                raise DomainError(ErrorCode.CONFLICT, "provider is disabled")
            if workflow:
                if (
                    provider.id != workflow.provider_id
                    or provider.version != workflow.provider_revision
                ):
                    raise DomainError(
                        ErrorCode.FORBIDDEN,
                        "Workflow provider changed; create a new reviewed workflow",
                    )
            else:
                self.ensure_disclosure(provider)
            models = self.providers()
            selected = next((item for item in models if item["id"] == str(provider.id)), None)
            choices = selected["models"] if selected else []
            desired_model = payload.get("modelId")
            model = next(
                (
                    item
                    for item in choices
                    if item["enabled"]
                    and (
                        item["modelId"] == desired_model if desired_model else role in item["roles"]
                    )
                ),
                None,
            )
            if model is None:
                raise DomainError(ErrorCode.VALIDATION, "select an enabled provider model")
            model_id, provider_revision = model["modelId"], provider.version
        autopilot = payload.get("autopilot") is True or workflow is not None
        if autopilot and not workflow and not self.policy()["autopilot"]["enabled"]:
            raise DomainError(
                ErrorCode.FORBIDDEN, "enable bounded autopilot in Agent settings first"
            )
        run = AgentRun(
            workspace_id=self.ctx.workspace_id,
            owner_id=self.ctx.principal_id,
            thread_id=thread.id,
            provider_id=provider_id,
            provider_revision=provider_revision,
            model_id=model_id,
            role=role,
            status="queued",
            prompt=prompt.strip(),
            autopilot=autopilot,
            checkpoint={
                "step": 0,
                "toolCalls": 0,
                "documents": 0,
                "trainingJobs": 0,
                "costUsd": 0.0,
                "messages": [],
                "localModelId": str(local_model_id) if local_model_id else None,
                "localModelFingerprint": local_fingerprint,
                "workflowId": str(workflow.id) if workflow else None,
            },
            cancel_requested=False,
        )
        self.db.add(run)
        self.db.flush()
        self.db.add(
            AgentMessage(
                workspace_id=self.ctx.workspace_id,
                owner_id=self.ctx.principal_id,
                thread_id=thread.id,
                run_id=run.id,
                role="user",
                kind="message",
                content=prompt.strip(),
                refs={},
                created_at=datetime.now(UTC),
            )
        )
        thread.updated_at = datetime.now(UTC)
        self.db.flush()
        return self.run_json(run)
```

## AgentWorkspaceService.create_thread

Source: `services/studio-api/src/studio/domain/agent_workspace/service.py:AgentWorkspaceService.create_thread`.

```python
    def create_thread(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = ident(payload["taskId"]) if payload.get("taskId") else None
        if task_id:
            task = self.db.scalar(
                select(ResearchTask).where(
                    ResearchTask.id == task_id, ResearchTask.workspace_id == self.ctx.workspace_id
                )
            )
            if task is None:
                raise not_found("task")
            self.ctx.require("read_project", task.project_id)
        notebook_id = ident(payload["notebookId"]) if payload.get("notebookId") else None
        if notebook_id:
            from studio.domain.library.models import Notebook

            notebook = self.db.scalar(
                select(Notebook).where(
                    Notebook.id == notebook_id,
                    Notebook.workspace_id == self.ctx.workspace_id,
                    Notebook.owner_id == self.ctx.principal_id,
                )
            )
            if notebook is None:
                raise not_found("private notebook")
            if not notebook.ai_enabled:
                raise DomainError(ErrorCode.FORBIDDEN, "AI access is disabled for this notebook")
        row = AgentThread(
            workspace_id=self.ctx.workspace_id,
            owner_id=self.ctx.principal_id,
            title=str(payload.get("title") or "New research")[:200],
            task_id=task_id,
            notebook_id=notebook_id,
        )
        self.db.add(row)
        self.db.flush()
        return self.thread_json(row)
```

## CandidateService.create_candidate

Source: `services/studio-api/src/studio/domain/candidates/service.py:CandidateService.create_candidate`.

```python
    def create_candidate(
        self,
        *,
        task_id: uuid.UUID,
        entity_kind: str,
        entity_revision_id: uuid.UUID | None = None,
        hypothesis: str | None = None,
        proposed_differences: list[dict[str, Any]] | None = None,
        evidence_ids: list[str] | None = None,
        contract_revision_id: uuid.UUID | None = None,
        parent_revision_id: uuid.UUID | None = None,
    ) -> CandidateRevision:
        """Agents and users may propose; review stays human."""
        self.ctx.require(CAP_PROPOSE_CANDIDATE)
        task = self.db.execute(
            select(ResearchTask).where(
                ResearchTask.id == task_id,
                ResearchTask.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if task is None:
            raise not_found("task")
        if entity_kind not in ENTITY_KINDS:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"entity_kind must be one of {ENTITY_KINDS}",
                field_path="input.entityKind",
            )
        if parent_revision_id is not None:
            parent = self._candidate(parent_revision_id)
            if parent.task_id != task.id:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "parent candidate belongs to a different task",
                    field_path="input.parentRevisionId",
                )
        payload: dict[str, Any] = {
            "proposedDifferences": proposed_differences or [],
            "evidenceIds": evidence_ids or [],
        }
        current_max = self.db.execute(
            select(func.max(CandidateRevision.revision)).where(CandidateRevision.task_id == task.id)
        ).scalar_one()
        row = CandidateRevision(
            workspace_id=self.ctx.workspace_id,
            task_id=task.id,
            revision=(current_max or 0) + 1,
            status="draft",
            eligibility="not_assessed",
            entity_kind=entity_kind,
            entity_revision_id=entity_revision_id,
            parent_revision_id=parent_revision_id,
            contract_revision_id=contract_revision_id,
            hypothesis=hypothesis,
            payload=payload,
            content_hash=content_hash(
                {
                    **payload,
                    "entityKind": entity_kind,
                    "entityRevisionId": str(entity_revision_id or ""),
                    "hypothesis": hypothesis or "",
                }
            ),
            created_by=self.ctx.principal_id,
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="research_task",
            aggregate_id=task.id,
            event_type="candidate.created",
            payload={
                "taskId": str(task.id),
                "candidateId": str(row.id),
                "entityKind": entity_kind,
            },
        )
        return row
```

## CandidateService.propose_patch

Source: `services/studio-api/src/studio/domain/candidates/service.py:CandidateService.propose_patch`.

```python
    def propose_patch(
        self,
        *,
        candidate_id: uuid.UUID,
        patch: dict[str, Any],
        reason: str | None = None,
    ) -> CandidatePatch:
        """Propose a content patch — explicit and reviewable. Agents
        may propose; applying still requires human review."""
        self.ctx.require(CAP_PROPOSE_CANDIDATE)
        cand = self._candidate(candidate_id)
        if not patch:
            raise DomainError(
                ErrorCode.VALIDATION,
                "patch must not be empty",
                field_path="input.patch",
            )
        row = CandidatePatch(
            workspace_id=self.ctx.workspace_id,
            candidate_id=cand.id,
            status="proposed",
            patch={"ops": patch, "reason": reason} if reason else {"ops": patch},
            proposed_by=self.ctx.principal_kind,
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="candidate_revision",
            aggregate_id=cand.id,
            event_type="candidate.patch_proposed",
            payload={"candidateId": str(cand.id), "patchId": str(row.id)},
        )
        return row
```

## CandidateService.review_candidate

Source: `services/studio-api/src/studio/domain/candidates/service.py:CandidateService.review_candidate`.

```python
    def review_candidate(self, *, candidate_id: uuid.UUID, accept: bool) -> CandidateRevision:
        """Human-only scientific review: submitted → accepted_for_research
        | rejected."""
        self.ctx.require(CAP_REVIEW_SCIENCE)
        _require_human(self.ctx)
        cand = self._candidate(candidate_id)
        if cand.status != "submitted":
            raise DomainError(
                ErrorCode.VALIDATION,
                f"only a submitted candidate can be reviewed ('{cand.status}')",
                field_path="input.candidateId",
            )
        cand.status = "accepted_for_research" if accept else "rejected"
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="candidate_revision",
            aggregate_id=cand.id,
            event_type="candidate.reviewed",
            payload={
                "candidateId": str(cand.id),
                "decision": cand.status,
            },
        )
        audit_record(
            self.db,
            self.ctx,
            action="candidate.review",
            target_type="candidate_revision",
            target_id=cand.id,
            detail={"decision": cand.status},
        )
        return cand
```

## CandidateService.review_patch

Source: `services/studio-api/src/studio/domain/candidates/service.py:CandidateService.review_patch`.

```python
    def review_patch(
        self,
        *,
        patch_id: uuid.UUID,
        accept: bool,
        rejection_reason: str | None = None,
    ) -> CandidatePatch:
        """Human review of a patch (AT-0204-2).

        Reject: patch marked rejected with the reason retained; the
        target candidate's content is *not* touched.
        Accept: a new draft CandidateRevision is created with the
        patched payload — the target row itself stays immutable.
        """
        self.ctx.require(CAP_REVIEW_SCIENCE)
        _require_human(self.ctx)
        patch = self._patch(patch_id)
        if patch.status != "proposed":
            raise DomainError(
                ErrorCode.VALIDATION,
                f"only a proposed patch can be reviewed ('{patch.status}')",
                field_path="input.patchId",
            )
        patch.reviewed_by = self.ctx.principal_id
        patch.reviewed_at = datetime.now(UTC)
        if not accept:
            if not (rejection_reason or "").strip():
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "a rejection reason is required",
                    field_path="input.rejectionReason",
                )
            patch.status = "rejected"
            patch.rejection_reason = rejection_reason
            self.db.flush()
            audit_record(
                self.db,
                self.ctx,
                action="candidate.patch.reject",
                target_type="candidate_patch",
                target_id=patch.id,
                detail={"reason": rejection_reason},
            )
            return patch
        # apply → new revision on the same candidate lineage
        cand = self._candidate(patch.candidate_id)
        ops = patch.patch.get("ops", patch.patch)
        new_payload = self._apply_ops(cand.payload, ops)
        current_max = self.db.execute(
            select(func.max(CandidateRevision.revision)).where(
                CandidateRevision.task_id == cand.task_id
            )
        ).scalar_one()
        new_rev = CandidateRevision(
            workspace_id=self.ctx.workspace_id,
            task_id=cand.task_id,
            revision=(current_max or 0) + 1,
            status="draft",
            eligibility="not_assessed",
            entity_kind=cand.entity_kind,
            entity_revision_id=cand.entity_revision_id,
            parent_revision_id=cand.id,
            contract_revision_id=cand.contract_revision_id,
            hypothesis=cand.hypothesis,
            payload=new_payload,
            content_hash=content_hash(
                {
                    **new_payload,
                    "entityKind": cand.entity_kind,
                    "entityRevisionId": str(cand.entity_revision_id or ""),
                    "hypothesis": cand.hypothesis or "",
                }
            ),
            created_by=self.ctx.principal_id,
        )
        self.db.add(new_rev)
        patch.status = "accepted"
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="candidate_revision",
            aggregate_id=cand.id,
            event_type="candidate.patch_applied",
            payload={
                "candidateId": str(cand.id),
                "patchId": str(patch.id),
                "newRevisionId": str(new_rev.id),
            },
        )
        audit_record(
            self.db,
            self.ctx,
            action="candidate.patch.apply",
            target_type="candidate_patch",
            target_id=patch.id,
            detail={"newRevisionId": str(new_rev.id)},
        )
        return patch
```

## CandidateService.submit_candidate

Source: `services/studio-api/src/studio/domain/candidates/service.py:CandidateService.submit_candidate`.

```python
    def submit_candidate(self, *, candidate_id: uuid.UUID) -> CandidateRevision:
        self.ctx.require(CAP_PROPOSE_CANDIDATE)
        cand = self._candidate(candidate_id)
        if cand.status != "draft":
            raise DomainError(
                ErrorCode.VALIDATION,
                f"only a draft candidate can be submitted ('{cand.status}')",
                field_path="input.candidateId",
            )
        cand.status = "submitted"
        self.db.flush()
        return cand
```

## AnalyticsService.compare

Source: `services/studio-api/src/studio/domain/chemistry/analytics.py:AnalyticsService.compare`.

```python
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
```

## AnalyticsService.ingest

Source: `services/studio-api/src/studio/domain/chemistry/analytics.py:AnalyticsService.ingest`.

```python
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
```

## ClaimService.create_claim

Source: `services/studio-api/src/studio/domain/evidence/claims.py:ClaimService.create_claim`.

```python
    def create_claim(
        self,
        ctx: ServiceContext,
        *,
        kind: str,
        subject: dict[str, Any],
        statement: dict[str, Any],
        locator: dict[str, Any] | None = None,
        original_text: str | None = None,
        conditions: dict[str, Any] | None = None,
    ) -> EvidenceClaim:
        """Non-record claims — inferred suggestions and measured
        outcomes enter proposed and carry their own provenance."""
        ctx.require(CAP_MANAGE_SOURCES)
        if kind not in CLAIM_KINDS:
            raise DomainError(ErrorCode.VALIDATION, f"unknown claim kind {kind}")
        # pg_clean at the persistence boundary — a NUL byte in any
        # caller-supplied text would otherwise crash the INSERT as a
        # raw driver error rather than a clean record (CS-1101).
        claim = EvidenceClaim(
            workspace_id=ctx.workspace_id,
            kind=kind,
            status="proposed",
            subject=pg_clean(subject)[0],
            statement=pg_clean(statement)[0],
            locator=pg_clean(locator)[0],
            original_text=pg_clean(original_text)[0],
            conditions=pg_clean(conditions)[0],
            created_by=ctx.principal_id,
        )
        self.db.add(claim)
        self.db.flush()
        return claim
```

## ClaimService.link

Source: `services/studio-api/src/studio/domain/evidence/claims.py:ClaimService.link`.

```python
    def link(
        self,
        ctx: ServiceContext,
        from_claim_id: uuid.UUID,
        to_claim_id: uuid.UUID,
        relation: str,
        *,
        note: str | None = None,
    ) -> ClaimLink:
        """Record support or contradiction between two claims. A
        contradiction keeps both claims fully visible — neither is
        demoted or hidden (AT-0302-2)."""
        ctx.require(CAP_REVIEW_SCIENCE)
        if relation not in CLAIM_RELATIONS:
            raise DomainError(ErrorCode.VALIDATION, f"relation must be one of {CLAIM_RELATIONS}")
        src = self.get(ctx, from_claim_id)
        dst = self.get(ctx, to_claim_id)
        existing = self.db.execute(
            select(ClaimLink).where(
                ClaimLink.workspace_id == ctx.workspace_id,
                ClaimLink.from_claim_id == src.id,
                ClaimLink.to_claim_id == dst.id,
                ClaimLink.relation == relation,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing  # linking is idempotent
        edge = ClaimLink(
            workspace_id=ctx.workspace_id,
            from_claim_id=src.id,
            to_claim_id=dst.id,
            relation=relation,
            note=note,
            created_by=ctx.principal_id,
        )
        self.db.add(edge)
        self.db.flush()
        return edge
```

## ClaimService.promote_record

Source: `services/studio-api/src/studio/domain/evidence/claims.py:ClaimService.promote_record`.

```python
    def promote_record(
        self,
        ctx: ServiceContext,
        record_id: uuid.UUID,
        *,
        subject: dict[str, Any],
        statement: dict[str, Any],
        conditions: dict[str, Any] | None = None,
    ) -> EvidenceClaim:
        """Extraction review: propose an evidence claim from an
        extracted record. The record is marked accepted (field-level
        acceptance); the *claim* still starts ``proposed`` — ambiguity
        is never auto-accepted (AT-0302-1)."""
        ctx.require(CAP_MANAGE_SOURCES)
        importer = ImportService(self.db, vault=None)  # lookups only
        record = importer.get_record(ctx, record_id)
        if record.status == "rejected":
            raise DomainError(ErrorCode.CONFLICT, "a rejected record cannot be promoted")
        if record.status == "proposed":
            record.status = "accepted"
            record.reviewed_by = ctx.principal_id
            record.reviewed_at = datetime.now(tz=UTC)
        claim = EvidenceClaim(
            workspace_id=ctx.workspace_id,
            kind="document_claim",
            status="proposed",
            subject=pg_clean(subject)[0],
            statement=pg_clean(statement)[0],
            locator=record.locator,
            original_text=record.original_text,
            conditions=pg_clean(conditions)[0],
            source_batch_id=record.batch_id,
            source_record_id=record.id,
            created_by=ctx.principal_id,
        )
        self.db.add(claim)
        self.db.flush()
        return claim
```

## ClaimService.review

Source: `services/studio-api/src/studio/domain/evidence/claims.py:ClaimService.review`.

```python
    def review(self, ctx: ServiceContext, claim_id: uuid.UUID, decision: str) -> EvidenceClaim:
        """Science review accepts or rejects a proposed claim — a
        human judgment, so agent principals are blocked."""
        ctx.require(CAP_REVIEW_SCIENCE)
        if ctx.principal_kind != "user":
            raise DomainError(ErrorCode.FORBIDDEN, "evidence review requires a human principal")
        if decision not in ("accepted", "rejected"):
            raise DomainError(ErrorCode.VALIDATION, "decision must be accepted|rejected")
        claim = self.get(ctx, claim_id)
        if claim.status != "proposed":
            raise DomainError(ErrorCode.CONFLICT, f"claim already {claim.status}")
        claim.status = decision
        claim.reviewed_by = ctx.principal_id
        claim.reviewed_at = datetime.now(tz=UTC)
        self.db.flush()
        return claim
```

## ImportService.import_artifact

Source: `services/studio-api/src/studio/domain/evidence/imports.py:ImportService.import_artifact`.

```python
    def import_artifact(
        self, ctx: ServiceContext, artifact_id: uuid.UUID
    ) -> tuple[ImportBatch, bool]:
        """Run the quarantine pipeline over a committed artifact.
        Returns ``(batch, deduplicated)`` — a repeat import of the same
        bytes with the same parser returns the existing batch without
        duplicating records (AT-0301-3)."""
        artifact = self.db.execute(
            select(Artifact).where(
                Artifact.id == artifact_id,
                Artifact.workspace_id == ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if artifact is None:
            raise not_found("artifact")
        ctx.require(CAP_MANAGE_SOURCES, artifact.access_scope)
        if artifact.upload_state != "committed":
            raise DomainError(
                ErrorCode.CONFLICT,
                f"artifact is {artifact.upload_state} — only committed artifacts can be parsed",
            )
        if artifact.review_state == "revoked":
            raise DomainError(
                ErrorCode.CONFLICT,
                "artifact is revoked — a revoked source cannot re-enter the pipeline",
            )
        rights = artifact.rights or {}
        if rights.get("extraction") == "denied":
            raise DomainError(
                ErrorCode.FORBIDDEN,
                "extraction right is denied for this artifact",
            )

        checksum = artifact.checksum_sha256 or self._checksum(ctx, artifact)
        existing = self.db.execute(
            select(ImportBatch).where(
                ImportBatch.workspace_id == ctx.workspace_id,
                ImportBatch.checksum_sha256 == checksum,
                ImportBatch.parser_version == PARSER_VERSION,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, True

        if self.vault is None:
            raise DomainError(ErrorCode.CONFLICT, "no vault configured for byte reads")
        blob = self.vault.open_blob(ctx.workspace_id, artifact.storage_key)
        with blob:
            data = blob.read()

        findings: list[dict[str, str]] = []
        if rights.get("extraction", "unknown") in ("unknown", None):
            findings.append(
                {
                    "code": "RIGHTS_UNKNOWN",
                    "detail": "extraction right is undecided — records stay quarantined for review",
                }
            )
        detected = detect_type(data, artifact.original_name)
        try:
            report = run_parse(
                data,
                artifact.original_name,
                limits=self.limits,
                isolate=self.isolate,
            )
        except QuarantineError as exc:
            # Typed denial is still recorded — auditable, no records.
            batch = self._new_batch(ctx, artifact, checksum, "quarantined")
            batch.detected_type = detected
            batch.findings = [*findings, {"code": exc.code, "detail": exc.message}]
            self.db.add(batch)
            self.db.flush()
            return batch, False

        findings += report.findings
        status = "parsed" if report.records else "quarantined"
        batch = self._new_batch(ctx, artifact, checksum, status)
        batch.detected_type = detected
        batch.parser_name = report.parser_name
        batch.findings = findings
        batch.record_count = len(report.records)
        self.db.add(batch)
        self.db.flush()
        for rec in report.records:
            # Postgres text/jsonb refuse NUL — scrub at the persistence
            # boundary and flag the record honestly rather than crash
            # the INSERT as a raw driver error (CS-1101).
            locator, s1 = pg_clean(rec.locator)
            text, s2 = pg_clean(rec.original_text)
            payload, s3 = pg_clean(rec.value)
            flags = list(rec.flags or [])
            if s1 or s2 or s3:
                flags = [*flags, "nul_scrubbed"]
            self.db.add(
                ExtractedRecord(
                    workspace_id=ctx.workspace_id,
                    batch_id=batch.id,
                    kind=rec.kind,
                    locator=locator,
                    original_text=text,
                    payload=payload,
                    flags=flags,
                    confidence=rec.confidence,
                )
            )
        artifact.parser_version = PARSER_VERSION
        self.db.flush()
        return batch, False
```

## ImportService.review_record

Source: `services/studio-api/src/studio/domain/evidence/imports.py:ImportService.review_record`.

```python
    def review_record(
        self,
        ctx: ServiceContext,
        record_id: uuid.UUID,
        decision: str,
    ) -> ExtractedRecord:
        """Accept or reject a proposed record — a human review step,
        never automatic (§9.2)."""
        ctx.require(CAP_MANAGE_SOURCES)
        if ctx.principal_kind != "user":
            raise DomainError(
                ErrorCode.FORBIDDEN,
                "import review requires a human principal",
            )
        if decision not in ("accepted", "rejected"):
            raise DomainError(ErrorCode.VALIDATION, "decision must be accepted|rejected")
        record = self.get_record(ctx, record_id)
        if record.status != "proposed":
            raise DomainError(ErrorCode.CONFLICT, f"record already {record.status}")
        record.status = decision
        record.reviewed_by = ctx.principal_id
        record.reviewed_at = datetime.now(tz=UTC)
        self.db.flush()
        return record
```

## RevocationService.revoke

Source: `services/studio-api/src/studio/domain/evidence/revocation.py:RevocationService.revoke`.

```python
    def revoke(
        self, ctx: ServiceContext, artifact_id: uuid.UUID, *, reason: str
    ) -> SourceRevocation:
        """Revoke a source and propagate the supersession. A human
        stewardship act — revocation rewrites review state, it is not
        an agent shortcut."""
        ctx.require(CAP_MANAGE_SOURCES)
        if ctx.principal_kind != "user":
            raise DomainError(
                ErrorCode.FORBIDDEN,
                "source revocation requires a human principal",
            )
        if not (reason or "").strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "a revocation reason is required",
                field_path="input.reason",
            )
        artifact = self._artifact(artifact_id)
        if artifact.review_state == "revoked":
            raise DomainError(
                ErrorCode.CONFLICT,
                "artifact is already revoked",
                field_path="input.artifactId",
            )
        prior = self.db.execute(
            select(SourceRevocation).where(
                SourceRevocation.workspace_id == self.ctx.workspace_id,
                SourceRevocation.artifact_id == artifact.id,
            )
        ).scalar_one_or_none()
        if prior is not None:
            raise DomainError(
                ErrorCode.CONFLICT,
                "artifact already has a revocation record",
                field_path="input.artifactId",
            )

        report = self._scan(artifact)

        artifact.review_state = "revoked"
        revoked_chunks = RetrievalService(self.db).revoke_artifact(ctx, artifact.id)

        batch_ids = [uuid.UUID(b) for b in report["batchIds"]]
        if batch_ids:
            for rec in self.db.execute(
                select(ExtractedRecord).where(
                    ExtractedRecord.workspace_id == self.ctx.workspace_id,
                    ExtractedRecord.batch_id.in_(batch_ids),
                    ExtractedRecord.status != "rejected",
                )
            ).scalars():
                rec.status = "rejected"
                rec.flags = [*rec.flags, "source_revoked"]
            for claim in self.db.execute(
                select(EvidenceClaim).where(
                    EvidenceClaim.workspace_id == self.ctx.workspace_id,
                    EvidenceClaim.source_batch_id.in_(batch_ids),
                    EvidenceClaim.status.in_(["proposed", "accepted"]),
                )
            ).scalars():
                claim.status = "superseded"

        for derived_id in report["affectedDerivedIds"]:
            derived = self.db.get(Artifact, uuid.UUID(derived_id))
            if derived is None:
                continue
            derived.retention = {
                **(derived.retention or {}),
                "lineage_review": "required",
                "lineage_affected_by": str(artifact.id),
            }

        report["chunksRevoked"] = revoked_chunks
        row = SourceRevocation(
            workspace_id=self.ctx.workspace_id,
            artifact_id=artifact.id,
            reason=reason.strip(),
            revoked_by=self.ctx.principal_id,
            report=report,
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="artifact",
            aggregate_id=artifact.id,
            event_type="source.revoked",
            payload={
                "artifactId": str(artifact.id),
                "revocationId": str(row.id),
                "chunksRevoked": revoked_chunks,
            },
        )
        audit_record(
            self.db,
            self.ctx,
            action="source.revoke",
            target_type="artifact",
            target_id=artifact.id,
            detail={"reason": row.reason, "report": report},
        )
        return row
```

## ProviderService.cleanup_credentials

Source: `services/studio-api/src/studio/domain/inference/providers.py:ProviderService.cleanup_credentials`.

```python
    def cleanup_credentials(self) -> bool:
        self._admin()
        return self._cleanup()
```

## ProviderService.delete

Source: `services/studio-api/src/studio/domain/inference/providers.py:ProviderService.delete`.

```python
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
```

## ProviderService.save

Source: `services/studio-api/src/studio/domain/inference/providers.py:ProviderService.save`.

```python
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
```

## ProviderService.test

Source: `services/studio-api/src/studio/domain/inference/providers.py:ProviderService.test`.

```python
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
```

## LabMeasurementService.add_batch

Source: `services/studio-api/src/studio/domain/lab/measurements.py:LabMeasurementService.add_batch`.

```python
    def add_batch(
        self, execution_id: uuid.UUID, *, label: str, payload: dict[str, Any] | None = None
    ) -> LabBatch:
        ex = self._execution(execution_id)
        self.ctx.require(CAP_EDIT_TASK, self._execution_project(ex))
        if ex.status != "in_progress":
            raise DomainError(ErrorCode.CONFLICT, "execution is closed")
        if not label.strip():
            raise DomainError(ErrorCode.VALIDATION, "batch label required")
        batch = LabBatch(
            workspace_id=self.ctx.workspace_id,
            execution_id=execution_id,
            label=label.strip(),
            payload=dict(payload or {}),
        )
        self.db.add(batch)
        self.db.flush()
        return batch
```

## LabMeasurementService.add_sample

Source: `services/studio-api/src/studio/domain/lab/measurements.py:LabMeasurementService.add_sample`.

```python
    def add_sample(
        self,
        batch_id: uuid.UUID,
        *,
        label: str,
        kind: str = "aliquot",
        payload: dict[str, Any] | None = None,
    ) -> LabSample:
        batch = self._batch(batch_id)
        self.ctx.require(
            CAP_EDIT_TASK,
            self._execution_project(self._execution(batch.execution_id)),
        )
        if kind not in SAMPLE_KINDS:
            raise DomainError(ErrorCode.VALIDATION, f"kind must be in {SAMPLE_KINDS}")
        if not label.strip():
            raise DomainError(ErrorCode.VALIDATION, "sample label required")
        sample = LabSample(
            workspace_id=self.ctx.workspace_id,
            batch_id=batch_id,
            label=label.strip(),
            kind=kind,
            payload=dict(payload or {}),
        )
        self.db.add(sample)
        self.db.flush()
        return sample
```

## LabMeasurementService.amend

Source: `services/studio-api/src/studio/domain/lab/measurements.py:LabMeasurementService.amend`.

```python
    def amend(
        self,
        measurement_id: uuid.UUID,
        *,
        reason: str,
        source: str | None = None,
        value: dict[str, Any],
        conditions: dict[str, Any] | None = None,
    ) -> MeasurementAmendment:
        """Correct an accepted measurement via amendment (§14.2,
        AT-0502-3): the original row keeps its value and flips to
        ``superseded`` — never overwritten."""
        m = self._measurement(measurement_id)
        self.ctx.require(CAP_REVIEW_MEASUREMENT, self._measurement_project(m))
        if m.status != "accepted":
            raise DomainError(ErrorCode.CONFLICT, "only an accepted measurement can be amended")
        if not reason.strip():
            raise DomainError(
                ErrorCode.VALIDATION, "amendment reason required", field_path="reason"
            )
        _validate_value(m.value_type, value)
        amd = MeasurementAmendment(
            workspace_id=self.ctx.workspace_id,
            measurement_id=m.id,
            reason=reason.strip(),
            source=source,
            value=dict(value),
            conditions=dict(conditions or {}),
            created_by=self.ctx.principal_id,
        )
        self.db.add(amd)
        self.db.flush()
        m.status = "superseded"
        m.superseded_by = amd.id
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="measurement.amended",
            target_type="measurement",
            target_id=m.id,
            detail={"amendmentId": str(amd.id), "reason": reason.strip()},
        )
        return amd
```

## LabMeasurementService.close_execution

Source: `services/studio-api/src/studio/domain/lab/measurements.py:LabMeasurementService.close_execution`.

```python
    def close_execution(
        self, execution_id: uuid.UUID, *, status: str = "completed"
    ) -> LabExecution:
        ex = self._execution(execution_id)
        self.ctx.require(CAP_EDIT_TASK, self._execution_project(ex))
        if status not in ("completed", "stopped"):
            raise DomainError(ErrorCode.VALIDATION, "status must be completed|stopped")
        if ex.status != "in_progress":
            raise DomainError(ErrorCode.CONFLICT, "execution is already closed")
        ex.status = status
        ex.closed_at = datetime.now(UTC)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="lab_execution.closed",
            target_type="lab_execution",
            target_id=ex.id,
            detail={"status": status},
        )
        return ex
```

## LabMeasurementService.import_historical

Source: `services/studio-api/src/studio/domain/lab/measurements.py:LabMeasurementService.import_historical`.

```python
    def import_historical(self, task_id: uuid.UUID, *, payload: dict[str, Any]) -> LabExecution:
        """Historical experiments may be recorded without preapproval —
        they are marked ``historical`` and can never claim a release
        approval (§14.1)."""
        task = self._task(task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        ex = LabExecution(
            workspace_id=self.ctx.workspace_id,
            plan_id=None,
            task_id=task_id,
            status="in_progress",
            historical=True,
            actual=dict(payload),
            opened_by=self.ctx.principal_id,
        )
        self.db.add(ex)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="lab_execution.historical_import",
            target_type="lab_execution",
            target_id=ex.id,
            detail={"taskId": str(task_id)},
        )
        return ex
```

## LabMeasurementService.open_execution

Source: `services/studio-api/src/studio/domain/lab/measurements.py:LabMeasurementService.open_execution`.

```python
    def open_execution(self, plan_id: uuid.UUID) -> LabExecution:
        """Open a manual execution for an approved plan — the release
        approval is re-verified at open time, so a stale approval
        blocks recording just as it blocks packet export."""
        plan = self._plan(plan_id)
        task = self._task(plan.task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if plan.status != "approved":
            raise DomainError(ErrorCode.CONFLICT, "only an approved plan can be executed")
        LabPlanService(self.db, self.ctx).verify_release_approval(plan)
        ex = LabExecution(
            workspace_id=self.ctx.workspace_id,
            plan_id=plan.id,
            task_id=plan.task_id,
            status="in_progress",
            opened_by=self.ctx.principal_id,
        )
        self.db.add(ex)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="lab_execution.opened",
            target_type="lab_execution",
            target_id=ex.id,
            detail={"planId": str(plan.id)},
        )
        return ex
```

## LabMeasurementService.record_actuals

Source: `services/studio-api/src/studio/domain/lab/measurements.py:LabMeasurementService.record_actuals`.

```python
    def record_actuals(
        self,
        execution_id: uuid.UUID,
        *,
        actual: dict[str, Any] | None = None,
        deviations: list[dict[str, Any]] | None = None,
        observations: str | None = None,
    ) -> LabExecution:
        ex = self._execution(execution_id)
        self.ctx.require(CAP_EDIT_TASK, self._execution_project(ex))
        if ex.status != "in_progress":
            raise DomainError(ErrorCode.CONFLICT, "execution is closed")
        if actual is not None:
            ex.actual = dict(actual)
        if deviations is not None:
            ex.deviations = list(deviations)
        if observations is not None:
            ex.observations = observations
        self.db.flush()
        return ex
```

## LabMeasurementService.record_applicability

Source: `services/studio-api/src/studio/domain/lab/measurements.py:LabMeasurementService.record_applicability`.

```python
    def record_applicability(
        self,
        measurement_id: uuid.UUID,
        *,
        candidate_revision_id: uuid.UUID,
        contract_revision_id: uuid.UUID | None = None,
        applicable: bool,
        rationale: str,
    ) -> EvidenceApplicability:
        """Reviewed evidence→candidate applicability mapping (§12.3,
        PAR-02 §4): the only way evidence without plan/sample lineage
        — historical imports above all — can substantiate a specific
        candidate revision. ``applicable=False`` records the reviewed
        refusal; it never silently participates again. Re-recording a
        pair updates the same row (the unique pair) so the decision
        history stays one row, and a withdrawn mapping can be
        re-reviewed."""
        m = self._measurement(measurement_id)
        self.ctx.require(CAP_REVIEW_MEASUREMENT, self._measurement_project(m))
        if not rationale.strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "applicability mapping requires a rationale",
                field_path="rationale",
            )
        cand = self.db.execute(
            select(CandidateRevision).where(
                CandidateRevision.workspace_id == self.ctx.workspace_id,
                CandidateRevision.id == candidate_revision_id,
            )
        ).scalar_one_or_none()
        if cand is None:
            raise DomainError(
                ErrorCode.NOT_FOUND,
                "candidate revision not found",
                field_path="candidateRevisionId",
            )
        if contract_revision_id is not None:
            contract = self.db.execute(
                select(SuccessContractRevision).where(
                    SuccessContractRevision.workspace_id == self.ctx.workspace_id,
                    SuccessContractRevision.id == contract_revision_id,
                )
            ).scalar_one_or_none()
            if contract is None:
                raise DomainError(
                    ErrorCode.NOT_FOUND,
                    "contract revision not found",
                    field_path="contractRevisionId",
                )
        row = self.db.execute(
            select(EvidenceApplicability).where(
                EvidenceApplicability.workspace_id == self.ctx.workspace_id,
                EvidenceApplicability.measurement_id == m.id,
                EvidenceApplicability.candidate_revision_id == cand.id,
            )
        ).scalar_one_or_none()
        if row is None:
            row = EvidenceApplicability(
                workspace_id=self.ctx.workspace_id,
                measurement_id=m.id,
                candidate_revision_id=cand.id,
            )
            self.db.add(row)
        row.contract_revision_id = contract_revision_id
        row.status = "applicable" if applicable else "not_applicable"
        row.rationale = rationale.strip()
        row.reviewed_by = self.ctx.principal_id
        row.revoked_at = None
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="evidence.applicability_recorded",
            target_type="evidence_applicability",
            target_id=row.id,
            detail={
                "measurementId": str(m.id),
                "candidateRevisionId": str(cand.id),
                "contractRevisionId": str(contract_revision_id)
                if contract_revision_id
                else None,
                "status": row.status,
            },
        )
        return row
```

## LabMeasurementService.record_measurement

Source: `services/studio-api/src/studio/domain/lab/measurements.py:LabMeasurementService.record_measurement`.

```python
    def record_measurement(
        self,
        sample_id: uuid.UUID,
        *,
        method: str,
        repeat_type: str,
        value: dict[str, Any],
        metric: str | None = None,
        value_type: str | None = None,
        conditions: dict[str, Any] | None = None,
        pipeline_version: str | None = None,
    ) -> Measurement:
        sample = self._sample(sample_id)
        batch = self._batch(sample.batch_id)
        ex = self._execution(batch.execution_id)
        self.ctx.require(CAP_EDIT_TASK, self._execution_project(ex))
        if ex.status != "in_progress":
            raise DomainError(ErrorCode.CONFLICT, "execution is closed")
        if not method.strip():
            raise DomainError(ErrorCode.VALIDATION, "method is required", field_path="method")
        if repeat_type not in REPEAT_TYPES:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"repeat_type must be in {REPEAT_TYPES}",
                field_path="repeatType",
            )
        vtype = value_type or (value.get("kind") if isinstance(value, dict) else None)
        if vtype not in MEASUREMENT_VALUE_TYPES:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"value_type must be in {MEASUREMENT_VALUE_TYPES}",
                field_path="valueType",
            )
        _validate_value(vtype, value)
        m = Measurement(
            workspace_id=self.ctx.workspace_id,
            sample_id=sample_id,
            method=method.strip(),
            metric=metric.strip() if metric else None,
            repeat_type=repeat_type,
            value_type=vtype,
            value=dict(value),
            conditions=dict(conditions or {}),
            pipeline_version=pipeline_version,
            created_by=self.ctx.principal_id,
        )
        self.db.add(m)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="measurement.recorded",
            target_type="measurement",
            target_id=m.id,
            detail={"sampleId": str(sample_id), "repeatType": repeat_type},
        )
        return m
```

## LabMeasurementService.review

Source: `services/studio-api/src/studio/domain/lab/measurements.py:LabMeasurementService.review`.

```python
    def review(
        self, measurement_id: uuid.UUID, *, decision: str, note: str | None = None
    ) -> Measurement:
        m = self._measurement(measurement_id)
        self.ctx.require(CAP_REVIEW_MEASUREMENT, self._measurement_project(m))
        if decision not in ("accepted", "rejected"):
            raise DomainError(ErrorCode.VALIDATION, "decision must be accepted|rejected")
        if m.status not in ("proposed",):
            raise DomainError(ErrorCode.CONFLICT, f"measurement in '{m.status}' cannot be reviewed")
        m.status = decision
        m.review_note = note
        m.reviewed_by = self.ctx.principal_id
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="measurement.reviewed",
            target_type="measurement",
            target_id=m.id,
            detail={"decision": decision},
        )
        return m
```

## LabMeasurementService.set_applicability

Source: `services/studio-api/src/studio/domain/lab/measurements.py:LabMeasurementService.set_applicability`.

```python
    def set_applicability(
        self, measurement_id: uuid.UUID, *, applicable: bool, note: str | None = None
    ) -> Measurement:
        """Integrity vs applicability are separate axes (§14.2): a
        deviated measurement may be accepted as raw yet inapplicable to
        the original contract."""
        m = self._measurement(measurement_id)
        self.ctx.require(CAP_REVIEW_MEASUREMENT, self._measurement_project(m))
        m.applicable = applicable
        m.applicability_note = note
        self.db.flush()
        return m
```

## LabMeasurementService.withdraw_applicability

Source: `services/studio-api/src/studio/domain/lab/measurements.py:LabMeasurementService.withdraw_applicability`.

```python
    def withdraw_applicability(
        self, measurement_id: uuid.UUID, *, candidate_revision_id: uuid.UUID
    ) -> EvidenceApplicability:
        """Withdraw a reviewed mapping (PAR-02 §6): the row is kept as
        review history; evaluators treat it as absent and the change
        marks dependent packets for reassessment."""
        m = self._measurement(measurement_id)
        self.ctx.require(CAP_REVIEW_MEASUREMENT, self._measurement_project(m))
        row = self.db.execute(
            select(EvidenceApplicability).where(
                EvidenceApplicability.workspace_id == self.ctx.workspace_id,
                EvidenceApplicability.measurement_id == m.id,
                EvidenceApplicability.candidate_revision_id == candidate_revision_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("applicability mapping")
        row.revoked_at = datetime.now(UTC)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="evidence.applicability_withdrawn",
            target_type="evidence_applicability",
            target_id=row.id,
            detail={
                "measurementId": str(m.id),
                "candidateRevisionId": str(candidate_revision_id),
            },
        )
        return row
```

## LabPlanService.create

Source: `services/studio-api/src/studio/domain/lab/plans.py:LabPlanService.create`.

```python
    def create(self, task_id: uuid.UUID, *, title: str, payload: dict[str, Any]) -> ExperimentPlan:
        task = self._task(task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if not (title or "").strip():
            raise DomainError(ErrorCode.VALIDATION, "title is required", field_path="title")
        if not isinstance(payload, dict):
            raise DomainError(ErrorCode.VALIDATION, "payload must be an object")
        plan = ExperimentPlan(
            workspace_id=self.ctx.workspace_id,
            task_id=task_id,
            title=title.strip(),
            status="draft",
            payload=payload,
            created_by=self.ctx.principal_id,
        )
        self._rebind(plan)
        plan.blockers = self._compute_blockers(task, payload)
        self.db.add(plan)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="experiment_plan.created",
            target_type="experiment_plan",
            target_id=plan.id,
            detail={"taskId": str(task_id)},
        )
        return plan
```

## LabPlanService.export_packet

Source: `services/studio-api/src/studio/domain/lab/plans.py:LabPlanService.export_packet`.

```python
    def export_packet(self, plan_id: uuid.UUID) -> dict[str, Any]:
        """Manual execution packet (§14.1, AT-0501-3): requires a valid
        approval bound to the *current* bound inputs — a stale digest,
        revocation or expiry blocks the export (AT-0501-1)."""
        plan = self._plan(plan_id)
        task = self._task(plan.task_id)
        self.ctx.require(CAP_READ_PROJECT, task.project_id)
        if plan.status != "approved":
            raise DomainError(ErrorCode.CONFLICT, "only an approved plan can produce a packet")
        approval = self.verify_release_approval(plan)
        packet = {
            "planId": str(plan.id),
            "taskId": str(plan.task_id),
            "title": plan.title,
            "executionMode": "manual",
            "label": MANUAL_EXECUTION_LABEL,
            "revisions": {
                "candidateRevisionId": plan.payload.get("candidateRevisionId"),
                "contractRevisionId": plan.payload.get("contractRevisionId"),
                "processRevisionId": plan.payload.get("processRevisionId"),
            },
            "method": plan.payload.get("method"),
            "samplePlan": plan.payload.get("samplePlan"),
            "acceptanceCriteria": plan.payload.get("acceptanceCriteria"),
            "hazardNotes": plan.payload.get("hazardNotes"),
            "resourceNeeds": plan.payload.get("resourceNeeds"),
            "approval": {
                "id": str(approval.id),
                "decidedBy": str(approval.decided_by),
                "decidedAt": approval.created_at.isoformat(),
            },
            "contentDigest": plan.content_digest,
            "exportedAt": datetime.now(UTC).isoformat(),
        }
        plan.packet = packet
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="experiment_plan.packet_exported",
            target_type="experiment_plan",
            target_id=plan.id,
            detail={"approvalId": str(approval.id)},
        )
        return packet
```

## LabPlanService.review

Source: `services/studio-api/src/studio/domain/lab/plans.py:LabPlanService.review`.

```python
    def review(
        self, plan_id: uuid.UUID, *, decision: str, rationale: str | None = None
    ) -> ExperimentPlan:
        """Scientific review (§14.1/§21.5): only a principal holding
        ``approve_experiment`` (a human role — never an agent) may
        decide. Open blockers must be resolved before approval; the
        system lists them instead of inventing input (AT-0501-2)."""
        plan = self._plan(plan_id)
        task = self._task(plan.task_id)
        self.ctx.require(CAP_APPROVE_EXPERIMENT, task.project_id)
        if plan.status != "submitted":
            raise DomainError(ErrorCode.CONFLICT, "only a submitted plan can be reviewed")
        if decision not in ("approved", "rejected"):
            raise DomainError(ErrorCode.VALIDATION, "decision must be approved|rejected")
        blockers = self._compute_blockers(task, plan.payload)
        plan.blockers = blockers
        if decision == "approved" and blockers:
            raise DomainError(
                ErrorCode.CONFLICT,
                "plan has unresolved blockers",
                safe_details={"blockers": blockers},
            )
        approval = grant(
            self.db,
            self.ctx,
            action=RELEASE_ACTION,
            bound_inputs=self._bound_inputs(plan),
            decision=decision,
            rationale=rationale,
        )
        plan.approval_id = approval.id
        plan.status = decision
        plan.packet = None
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="experiment_plan",
            aggregate_id=plan.id,
            event_type="experiment_plan.reviewed",
            payload={
                "planId": str(plan.id),
                "taskId": str(plan.task_id),
                "decision": decision,
                "approvalId": str(approval.id),
            },
        )
        return plan
```

## LabPlanService.submit

Source: `services/studio-api/src/studio/domain/lab/plans.py:LabPlanService.submit`.

```python
    def submit(self, plan_id: uuid.UUID) -> ExperimentPlan:
        plan = self._plan(plan_id)
        task = self._task(plan.task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if plan.status != "draft":
            raise DomainError(ErrorCode.CONFLICT, "only a draft can be submitted")
        plan.status = "submitted"
        plan.blockers = self._compute_blockers(task, plan.payload)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="experiment_plan",
            aggregate_id=plan.id,
            event_type="experiment_plan.submitted",
            payload={
                "planId": str(plan.id),
                "taskId": str(plan.task_id),
                "blockers": plan.blockers,
            },
        )
        return plan
```

## LabPlanService.update

Source: `services/studio-api/src/studio/domain/lab/plans.py:LabPlanService.update`.

```python
    def update(self, plan_id: uuid.UUID, *, payload: dict[str, Any]) -> ExperimentPlan:
        """Editing an approved plan is allowed — it shifts the content
        digest, so the previously granted release approval becomes
        stale at packet export (§14.1, AT-0501-1)."""
        plan = self._plan(plan_id)
        task = self._task(plan.task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if plan.status not in _EDITABLE:
            raise DomainError(ErrorCode.CONFLICT, f"plan in '{plan.status}' cannot be edited")
        if not isinstance(payload, dict):
            raise DomainError(ErrorCode.VALIDATION, "payload must be an object")
        plan.payload = payload
        self._rebind(plan)
        plan.blockers = self._compute_blockers(task, payload)
        plan.packet = None
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="experiment_plan",
            aggregate_id=plan.id,
            event_type="experiment_plan.updated",
            payload={
                "planId": str(plan.id),
                "taskId": str(plan.task_id),
                "contentDigest": plan.content_digest,
            },
        )
        return plan
```

## DatasetService.build

Source: `services/studio-api/src/studio/domain/learning/datasets.py:DatasetService.build`.

```python
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
```

## DatasetService.freeze

Source: `services/studio-api/src/studio/domain/learning/datasets.py:DatasetService.freeze`.

```python
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
```

## DatasetService.prepare_run

Source: `services/studio-api/src/studio/domain/learning/datasets.py:DatasetService.prepare_run`.

```python
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
```

## TransformService.decide

Source: `services/studio-api/src/studio/domain/learning/exports/transform.py:TransformService.decide`.

```python
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
```

## TransformService.payload

Source: `services/studio-api/src/studio/domain/learning/exports/transform.py:TransformService.payload`.

```python
    def payload(self, payload_id: uuid.UUID) -> ExportTransformedPayload:
        """Workspace-scoped fetch for callers that already know the id
        (e.g. the mutation layer re-loading a row post-commit)."""
        return self._payload(payload_id)
```

## TransformService.prepare

Source: `services/studio-api/src/studio/domain/learning/exports/transform.py:TransformService.prepare`.

```python
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
```

## TransformService.review_view

Source: `services/studio-api/src/studio/domain/learning/exports/transform.py:TransformService.review_view`.

```python
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
```

## TransformService.set_classification

Source: `services/studio-api/src/studio/domain/learning/exports/transform.py:TransformService.set_classification`.

```python
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
```

## ModelRegistryService.approve

Source: `services/studio-api/src/studio/domain/learning/models.py:ModelRegistryService.approve`.

```python
    def approve(self, release_id: uuid.UUID, *, rationale: str | None = None) -> Approval:
        """Human-holdable grant: ``approve_model`` capability only —
        agents can never call this (grant() enforces server-side)."""
        release = self._get(release_id)
        approval = grant(
            self.db,
            self.ctx,
            action=_APPROVAL_ACTION,
            bound_inputs=self._bound_inputs(release),
            rationale=rationale,
        )
        release.approval_id = approval.id
        self.db.flush()
        return approval
```

## ModelRegistryService.bind_session

Source: `services/studio-api/src/studio/domain/learning/models.py:ModelRegistryService.bind_session`.

```python
    def bind_session(self, session_id: uuid.UUID) -> tuple[ModelRelease, LoadValidationReport]:
        """Serving request (AT-0802-1/2): resolves the session's pinned
        release — the pin freezes at session start and a pointer move
        never mutates it — then REQUIRES a fresh compatible verdict.
        A mismatched pair raises MODEL_INCOMPATIBLE, never a warning."""
        self.ctx.require(CAP_READ_PROJECT)
        session = self.db.execute(
            select(ResearchSession).where(
                ResearchSession.id == session_id,
                ResearchSession.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if session is None:
            raise not_found("session")
        pin = self.db.execute(
            select(SessionModelPin).where(
                SessionModelPin.session_id == session_id,
                SessionModelPin.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        effective = pin.release_id if pin is not None else None
        if effective is None:
            pointer = self._pointer_row()
            effective = pointer.release_id
        if effective is None:
            raise DomainError(
                ErrorCode.CONFLICT, "no model release is being served for this session"
            )
        release = self._get(effective)
        if release.state not in _SERVABLE:
            raise DomainError(
                ErrorCode.MODEL_INCOMPATIBLE,
                f"pinned release is {release.state} — not servable",
            )
        report = self._validate_now(release)
        if report.status != "compatible":
            raise DomainError(
                ErrorCode.MODEL_INCOMPATIBLE,
                "serving compatibility validation failed",
                safe_details={
                    "releaseId": str(release.id),
                    "checks": [c.name for c in report.checks if not c.ok],
                },
            )
        # Latch: a session that began with no pointer serving (or a
        # legacy session with no pin row at all) pins the release its
        # first successful bind actually used.
        if pin is None:
            pin = SessionModelPin(
                workspace_id=self.ctx.workspace_id,
                session_id=session_id,
                release_id=release.id,
            )
            self.db.add(pin)
            self.db.flush()
        elif pin.release_id is None:
            pin.release_id = release.id
            self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="model_release.bound",
            target_type="research_session",
            target_id=session_id,
            detail={"releaseId": str(release.id), "mode": report.mode},
        )
        return release, report
```

## ModelRegistryService.convert

Source: `services/studio-api/src/studio/domain/learning/models.py:ModelRegistryService.convert`.

```python
    def convert(self, release_id: uuid.UUID, *, target_format: str = BUNDLE_FORMAT) -> ModelRelease:
        """Derive a serving-format conversion artifact (§17.5): the
        bundle embeds the adapter payload + identities, gets its own
        checksum, and carries a parity evaluation proving it loads the
        same weights as the registered pair."""
        self.ctx.require(CAP_MANAGE_MODELS)
        if target_format != BUNDLE_FORMAT:
            raise DomainError(
                ErrorCode.VALIDATION, f"unsupported conversion target {target_format!r}"
            )
        release = self._get(release_id)
        if release.state not in _SERVABLE:
            raise DomainError(
                ErrorCode.CONFLICT, f"release is {release.state}; only live releases convert"
            )
        adapter_bytes = self._artifact_bytes(release.adapter_artifact_id, "adapter")
        base, tokenizer, adapter = self._identities(release)
        steps = [
            {
                "step": "embed-adapter",
                "detail": "safetensors payload embedded verbatim",
                "sha256": release.adapter_sha256,
            },
            {"step": "canonical-json", "detail": "sorted keys, UTF-8, base64 payload"},
        ]
        blob = build_bundle(
            release_id=str(release.id),
            base=base,
            tokenizer=tokenizer,
            adapter=adapter,
            adapter_bytes=adapter_bytes,
            conversion_steps=steps,
        )
        artifact = self._persist_blob(
            blob,
            original_name=f"serving-bundle-{str(release.id)[:8]}.json",
            source_ids=[release.adapter_artifact_id] if release.adapter_artifact_id else [],
        )
        # Parity is evaluated NOW against the bytes just persisted.
        from workers.inference.model_loading.verify import bundle_parity

        parity = bundle_parity(blob, base=base, tokenizer=tokenizer, adapter=adapter)
        release.conversions = [
            *release.conversions,
            {
                "conversionId": str(uuid.uuid4()),
                "artifactId": str(artifact.id),
                "format": BUNDLE_FORMAT,
                "checksum": artifact.checksum_sha256,
                "steps": steps,
                "parity": parity.model_dump(mode="json"),
                "createdAt": _now().isoformat(),
            },
        ]
        if not parity.ok:
            release.validation = {
                **release.validation,
                "conversionParity": "failed",
            }
            self.db.flush()
            raise DomainError(
                ErrorCode.MODEL_INCOMPATIBLE,
                "conversion parity failed — derived artifact does not match the registered pair",
            )
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="model_release.converted",
            target_type="model_release",
            target_id=release.id,
            detail={"format": BUNDLE_FORMAT, "artifactId": str(artifact.id)},
        )
        return release
```

## ModelRegistryService.get

Source: `services/studio-api/src/studio/domain/learning/models.py:ModelRegistryService.get`.

```python
    def get(self, release_id: uuid.UUID) -> ModelRelease:
        self.ctx.require(CAP_READ_PROJECT)
        return self._get(release_id)
```

## ModelRegistryService.promote

Source: `services/studio-api/src/studio/domain/learning/models.py:ModelRegistryService.promote`.

```python
    def promote(self, release_id: uuid.UUID) -> ModelRelease:
        """Atomic promotion (§18.4): ONE transaction — approval
        re-validated, release re-validated, pointer row FOR UPDATE,
        old release superseded, this release promoted, its training run
        (when still at candidate_release) marked ``promoted`` — the
        only path that makes §17.5 ``promoted`` reachable."""
        self.ctx.require(CAP_MANAGE_MODELS)
        release = self._get(release_id)
        if release.state not in _SERVABLE:
            raise DomainError(
                ErrorCode.MODEL_NOT_PROMOTABLE,
                f"release is {release.state}; only validated/promotable releases promote",
            )
        if release.training_run_id is not None:
            run = self.db.get(TrainingRun, release.training_run_id)
            if run is not None and run.state not in ("candidate_release", "promoted"):
                raise DomainError(
                    ErrorCode.MODEL_NOT_PROMOTABLE,
                    f"training run is {run.state}; promotion requires candidate_release",
                )
        approval = require_valid(
            self.db,
            self.ctx,
            action=_APPROVAL_ACTION,
            bound_inputs=self._bound_inputs(release),
        )
        report = self._validate_now(release)
        if report.status != "compatible":
            raise DomainError(
                ErrorCode.MODEL_INCOMPATIBLE,
                "fresh compatibility validation failed — refusing to serve",
                safe_details={"checks": [c.name for c in report.checks if not c.ok]},
            )
        pointer = self._pointer_row()
        previous_id = pointer.release_id
        if previous_id == release.id:
            return release  # already the serving release — idempotent
        if previous_id is not None:
            previous = self.db.get(ModelRelease, previous_id)
            if previous is not None and previous.state == "promoted":
                previous.state = "superseded"
        pointer.release_id = release.id
        pointer.revision = int(pointer.revision) + 1
        pointer.reason = "promote"
        pointer.updated_by = self.ctx.principal_id
        release.state = "promoted"
        release.approval_id = approval.id
        if release.training_run_id is not None:
            run = self.db.get(TrainingRun, release.training_run_id)
            if run is not None and run.state == "candidate_release":
                # The registry's guarded path is the only allowed way
                # to reach §17.5 ``promoted`` — direct service calls
                # still raise MODEL_NOT_PROMOTABLE.
                run.state = "promoted"
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="model_release.promoted",
            target_type="model_release",
            target_id=release.id,
            detail={
                "pointerRevision": pointer.revision,
                "superseded": str(previous_id) if previous_id else None,
                "approvalId": str(approval.id),
            },
        )
        return release
```

## ModelRegistryService.register

Source: `services/studio-api/src/studio/domain/learning/models.py:ModelRegistryService.register`.

```python
    def register(
        self,
        *,
        training_run_id: uuid.UUID,
        name: str,
        task_id: uuid.UUID | None = None,
        serving_format: str = "peft-adapter",
    ) -> ModelRelease:
        """Register a release from a training run's persisted lineage.

        Reads the run's resolved config + result artifacts (CS-0801) —
        the adapter's recorded base/tokenizer binding comes from what
        training actually measured, not caller claims. Registration runs
        the first compatibility validation immediately."""
        self.ctx.require(CAP_MANAGE_MODELS, task_id)
        run = self.db.execute(
            select(TrainingRun).where(
                TrainingRun.id == training_run_id,
                TrainingRun.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if run is None:
            raise not_found("training run")
        if run.state in ("failed", "cancelled", "blocked", "draft"):
            raise DomainError(
                ErrorCode.CONFLICT,
                f"training run is {run.state} — nothing to register",
            )
        if run.adapter_artifact_id is None or run.result_artifact_id is None:
            raise DomainError(
                ErrorCode.CONFLICT,
                "training run has no persisted adapter/result — cannot register",
            )
        from workers.inference.model_loading import runtime as load_runtime

        outcome = json.loads(self._artifact_bytes(run.result_artifact_id, "result").decode("utf-8"))
        # Base identity comes from the run's approved spec; the
        # adapter's recorded binding (what training actually measured)
        # comes from result.json — never from caller claims.
        base_cfg = (run.spec or {}).get("model") or {}
        adapter_cfg = (run.spec or {}).get("adapter") or {}
        base_sha = outcome.get("base_sha256") or ""
        tok_sha = outcome.get("tokenizer_sha256") or ""
        if not base_sha or not tok_sha or not outcome.get("adapter_sha256"):
            raise DomainError(
                ErrorCode.CONFLICT,
                "training result lacks recorded base/tokenizer/adapter digests — "
                "compatibility binding cannot be established",
            )
        release = ModelRelease(
            workspace_id=self.ctx.workspace_id,
            task_id=task_id or run.task_id,
            name=name[:160],
            state="registered",
            snapshot_id=run.snapshot_id,
            training_run_id=run.id,
            adapter_artifact_id=run.adapter_artifact_id,
            base_model_id=str(base_cfg.get("base_model_id") or ""),
            architecture=str(base_cfg.get("architecture") or ""),
            init_seed=int(base_cfg.get("init_seed") or 0),
            base_sha256=base_sha,
            license_id=str(base_cfg.get("license_id") or ""),
            parameter_count=None,
            tokenizer_kind="char-v1",
            tokenizer_sha256=tok_sha,
            adapter_sha256=str(outcome["adapter_sha256"]),
            adapter_method=str(adapter_cfg.get("method") or "lora"),
            adapter_config=adapter_cfg,
            adapter_base_sha256=base_sha,
            adapter_tokenizer_sha256=tok_sha,
            adapter_architecture=str(base_cfg.get("architecture") or ""),
            serving_format=serving_format,
            conversions=[],
            capability=_capability_labels(load_engine_live=load_runtime.available()),
            provenance={
                "lineage": {
                    "snapshotId": str(run.snapshot_id),
                    "trainingRunId": str(run.id),
                    "adapterArtifactId": str(run.adapter_artifact_id),
                    "resultArtifactId": str(run.result_artifact_id),
                },
                "createdBy": str(self.ctx.principal_id),
                "createdAt": _now().isoformat(),
            },
            created_by=self.ctx.principal_id,
        )
        self.db.add(release)
        self.db.flush()
        self._validate_now(release)
        audit_record(
            self.db,
            self.ctx,
            action="model_release.registered",
            target_type="model_release",
            target_id=release.id,
            detail={
                "trainingRunId": str(run.id),
                "state": release.state,
                "validation": release.validation.get("status"),
            },
        )
        return release
```

## ModelRegistryService.rollback

Source: `services/studio-api/src/studio/domain/learning/models.py:ModelRegistryService.rollback`.

```python
    def rollback(self, release_id: uuid.UUID | None = None) -> ModelRelease:
        """Atomic rollback to a known-good release (§18.4,
        AT-0802-3): the pointer moves back in the same transaction —
        no schema/data rollback, the previous release stays with valid
        rights/lineage, and audit history is never overwritten."""
        self.ctx.require(CAP_MANAGE_MODELS)
        pointer = self._pointer_row()
        target: ModelRelease | None = None
        if release_id is not None:
            target = self._get(release_id)
        else:
            candidates = (
                self.db.execute(
                    select(ModelRelease)
                    .where(
                        ModelRelease.workspace_id == self.ctx.workspace_id,
                        ModelRelease.state == "superseded",
                    )
                    .order_by(ModelRelease.updated_at.desc(), ModelRelease.id.desc())
                )
                .scalars()
                .all()
            )
            for candidate in candidates:
                if candidate.id != pointer.release_id:
                    target = candidate
                    break
        if target is None:
            raise DomainError(ErrorCode.CONFLICT, "no known-good release to roll back to")
        if target.state not in _SERVABLE:
            raise DomainError(
                ErrorCode.CONFLICT,
                f"rollback target is {target.state}; needs a validated/superseded release",
            )
        report = self._validate_now(target)
        if report.status != "compatible":
            raise DomainError(
                ErrorCode.MODEL_INCOMPATIBLE,
                "rollback target no longer validates — pick another release",
                safe_details={"checks": [c.name for c in report.checks if not c.ok]},
            )
        previous_id = pointer.release_id
        if previous_id == target.id:
            return target
        if previous_id is not None:
            previous = self.db.get(ModelRelease, previous_id)
            if previous is not None and previous.state == "promoted":
                previous.state = "superseded"
        pointer.release_id = target.id
        pointer.revision = int(pointer.revision) + 1
        pointer.reason = "rollback"
        pointer.updated_by = self.ctx.principal_id
        target.state = "promoted"
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="model_release.rollback",
            target_type="model_release",
            target_id=target.id,
            detail={
                "pointerRevision": pointer.revision,
                "from": str(previous_id) if previous_id else None,
            },
        )
        return target
```

## ModelRegistryService.validate_release

Source: `services/studio-api/src/studio/domain/learning/models.py:ModelRegistryService.validate_release`.

```python
    def validate_release(self, release_id: uuid.UUID) -> ModelRelease:
        """Re-run compatibility validation and persist the verdict."""
        self.ctx.require(CAP_MANAGE_MODELS)
        release = self._get(release_id)
        self._validate_now(release)
        audit_record(
            self.db,
            self.ctx,
            action="model_release.validated",
            target_type="model_release",
            target_id=release.id,
            detail={"status": release.validation.get("status")},
        )
        return release
```

## OptimizationService.command

Source: `services/studio-api/src/studio/domain/learning/optimization.py:OptimizationService.command`.

```python
    def command(
        self,
        campaign_id: uuid.UUID,
        *,
        expected_revision: int,
        key: str,
        operation: Literal["recommend", "cancelled", "failed", "observed"],
        batch_size: int = 1,
        experiment_id: str | None = None,
        measurement_id: uuid.UUID | None = None,
        snapshot_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> OptimizationCampaign:
        row = self._get(campaign_id)
        if operation != "recommend" and self.ctx.principal_kind != "user":
            raise DomainError(
                ErrorCode.FORBIDDEN,
                "only humans can record campaign lifecycle decisions",
            )
        self.ctx.require(
            CAP_REQUEST_COMPUTE if operation == "recommend" else CAP_REVIEW_SCIENCE, row.task_id
        )
        self.ctx.require(CAP_MANAGE_MODELS, row.task_id)
        digest = request_digest(
            {
                "operation": operation,
                "batchSize": batch_size,
                "experimentId": experiment_id,
                "measurementId": str(measurement_id),
                "snapshotId": str(snapshot_id),
                "reason": reason,
            }
        )
        if not 1 <= len(key) <= 100:
            raise DomainError(ErrorCode.VALIDATION, "idempotency envelope exceeded")
        if key in row.commands:
            if row.commands[key] != digest:
                raise DomainError(
                    ErrorCode.IDEMPOTENCY_MISMATCH, "command key reused with changed parameters"
                )
            return row
        if len(row.commands) >= 1000:
            raise DomainError(ErrorCode.VALIDATION, "idempotency envelope exceeded")
        if row.revision != expected_revision:
            raise DomainError(
                ErrorCode.REVISION_CONFLICT, "campaign revision changed; reload before retrying"
            )
        campaign = self._load(row)
        try:
            if operation == "recommend":
                if experiment_id or measurement_id or snapshot_id or reason:
                    raise ValueError("recommend cannot submit outcomes or lifecycle edits")
                if not self.settings.profile_optimization:
                    raise DomainError(
                        ErrorCode.ENGINE_UNAVAILABLE, "optimization profile is disabled"
                    )
                campaign.recommend(IsolatedBayBE(), batch_size)
            else:
                if not experiment_id:
                    raise ValueError("experiment id required")
                outcome, source_hash = None, None
                if operation == "observed":
                    if not measurement_id or not snapshot_id:
                        raise ValueError("observation requires measurement and frozen snapshot ids")
                    outcome, source_hash = self._measurement(
                        row, campaign, experiment_id, measurement_id, snapshot_id
                    )
                elif measurement_id or snapshot_id:
                    raise ValueError("cancelled/failed is not an observation")
                campaign.transition(
                    experiment_id,
                    operation,
                    outcome=outcome,
                    measurement_id=str(measurement_id) if measurement_id else None,
                    snapshot_id=str(snapshot_id) if snapshot_id else None,
                    source_hash=source_hash,
                    reason=reason,
                )
        except EngineFailure as exc:
            raise DomainError(ErrorCode(exc.code), exc.message) from exc
        except (ValueError, ValidationError) as exc:
            raise DomainError(ErrorCode.VALIDATION, str(exc)) from exc
        row.replay = campaign.state.model_dump(mode="json")
        row.commands = {**row.commands, key: digest}
        row.revision += 1
        self.db.flush()
        record(
            self.db,
            self.ctx,
            action=f"optimization.{operation}",
            target_type="optimization_campaign",
            target_id=row.id,
            detail={"revision": row.revision},
        )
        return row
```

## OptimizationService.create

Source: `services/studio-api/src/studio/domain/learning/optimization.py:OptimizationService.create`.

```python
    def create(
        self, task_id: uuid.UUID, definition: dict[str, Any], key: str
    ) -> OptimizationCampaign:
        if self.ctx.principal_kind != "user":
            raise DomainError(ErrorCode.FORBIDDEN, "only humans can freeze a campaign definition")
        self.ctx.require(CAP_REVIEW_SCIENCE, task_id)
        self.ctx.require(CAP_MANAGE_MODELS, task_id)
        try:
            spec = CampaignSpec.model_validate(definition)
        except ValidationError as exc:
            raise DomainError(
                ErrorCode.ENGINE_UNSUPPORTED_INPUT,
                "unsupported campaign parameters/targets/constraints; nothing was dropped",
            ) from exc
        if not 1 <= len(key) <= 100:
            raise DomainError(ErrorCode.VALIDATION, "bounded idempotency key required")
        # Serialize create with the parent task lock; duplicate retries cannot create two rows.
        task = self.db.scalar(
            select(ResearchTask)
            .where(ResearchTask.id == task_id, ResearchTask.workspace_id == self.ctx.workspace_id)
            .with_for_update()
        )
        if task is None:
            raise not_found("task")
        old = self.db.scalar(
            select(OptimizationCampaign).where(
                OptimizationCampaign.workspace_id == self.ctx.workspace_id,
                OptimizationCampaign.task_id == task_id,
                OptimizationCampaign.creation_key == key,
            )
        )
        if old:
            if old.spec_digest != spec.digest():
                raise DomainError(
                    ErrorCode.IDEMPOTENCY_MISMATCH,
                    "creation key reused with a different definition",
                )
            return old
        if task.workflow_state != "active":
            raise DomainError(ErrorCode.CONFLICT, "campaign creation requires an active task")
        contract = (
            self.db.get(SuccessContractRevision, task.current_contract_revision_id)
            if task.current_contract_revision_id
            else None
        )
        if (
            not contract
            or contract.workspace_id != self.ctx.workspace_id
            or contract.status != "frozen"
        ):
            raise DomainError(
                ErrorCode.CONFLICT, "optimization requires a frozen task success contract"
            )
        metrics = contract.payload.get("metrics", [])
        if contract.payload.get("hard_constraints"):
            raise DomainError(
                ErrorCode.ENGINE_UNSUPPORTED_INPUT,
                "contract-level hard constraints need a reviewed mapping; none were dropped",
            )
        matching = [
            m
            for m in metrics
            if (
                m.get("id") == spec.target.name
                and m.get("unit") == spec.target.unit
                and str(m.get("method_revision_id")) == spec.target.method
            )
        ]
        if len(matching) != 1 or matching[0].get("value_kind") != "numeric":
            raise DomainError(
                ErrorCode.VALIDATION,
                "target metric, unit and method must match the pinned contract",
            )
        definition = matching[0]
        operator = str(definition.get("operator", ""))
        compatible_mode = {
            "gte": "maximize",
            "lte": "minimize",
            "eq": "match",
            "between": "match",
        }.get(operator)
        if spec.target.mode != compatible_mode:
            raise DomainError(
                ErrorCode.ENGINE_UNSUPPORTED_INPUT,
                "target direction lacks a reviewed contract mapping",
            )
        if spec.target.mode == "match":
            cutoffs = spec.target.match_bounds
            values = [Decimal(v) for v in definition.get("target_values", [])]
            if (
                not cutoffs
                or (operator == "between" and tuple(values) != cutoffs)
                or (operator == "eq" and (len(values) != 1 or sum(cutoffs) / 2 != values[0]))
            ):
                raise DomainError(
                    ErrorCode.ENGINE_UNSUPPORTED_INPUT,
                    "match transformation conflicts with frozen metric thresholds",
                )
        row = OptimizationCampaign(
            workspace_id=self.ctx.workspace_id,
            task_id=task_id,
            contract_revision_id=contract.id,
            definition=spec.model_dump(mode="json"),
            spec_digest=spec.digest(),
            replay=Campaign(spec).state.model_dump(mode="json"),
            revision=1,
            creation_key=key,
            commands={},
            created_by=self.ctx.principal_id,
        )
        self.db.add(row)
        self.db.flush()
        record(
            self.db,
            self.ctx,
            action="optimization.created",
            target_type="optimization_campaign",
            target_id=row.id,
        )
        return row
```

## EvaluationService.create_suite

Source: `services/studio-api/src/studio/domain/learning/promotion.py:EvaluationService.create_suite`.

```python
    def create_suite(
        self,
        *,
        name: str,
        kind: str,
        task_id: uuid.UUID | None = None,
        tasks: list[dict[str, Any]],
        thresholds: list[dict[str, Any]] | None = None,
        budget: dict[str, Any] | None = None,
        scoring: dict[str, Any] | None = None,
        allowed_context: dict[str, Any] | None = None,
        review_rules: dict[str, Any] | None = None,
        purpose: str = "assistant_sft",
    ) -> EvaluationSuite:
        """Register a suite draft — the public contract only; hidden
        targets are attached by ``set_labels`` and hashed per task."""
        self.ctx.require(CAP_MANAGE_MODELS, task_id)
        if kind not in ("development", "final"):
            raise DomainError(ErrorCode.VALIDATION, "kind must be development|final")
        latest = self.db.execute(
            select(EvaluationSuite.version)
            .where(
                EvaluationSuite.workspace_id == self.ctx.workspace_id,
                EvaluationSuite.name == name,
            )
            .order_by(EvaluationSuite.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        version = 1 if latest is None else int(latest) + 1
        definition = EvalSuiteDef(
            name=name,
            version=version,
            purpose=purpose,
            kind=kind,
            tasks=[dict(t) for t in tasks],
            thresholds=[dict(t) for t in (thresholds or [])],
            budget=dict(budget or {}),
            scoring=dict(scoring or {}),
            allowed_context=dict(allowed_context or {}),
            review_rules=dict(review_rules or {}),
        ).model_dump(mode="json")
        suite = EvaluationSuite(
            workspace_id=self.ctx.workspace_id,
            task_id=task_id,
            name=name,
            version=version,
            purpose=purpose,
            kind=kind,
            state="draft",
            definition=definition,
            digest=_definition_digest(definition),
            capability=self._suite_capability(),
            provenance={"source": "manual", "createdBy": str(self.ctx.principal_id)},
            created_by=self.ctx.principal_id,
        )
        self.db.add(suite)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="evaluation.suite_created",
            target_type="evaluation_suite",
            target_id=suite.id,
            detail={"name": name, "version": version, "kind": kind},
        )
        return suite
```

## EvaluationService.freeze

Source: `services/studio-api/src/studio/domain/learning/promotion.py:EvaluationService.freeze`.

```python
    def freeze(self, suite_id: uuid.UUID) -> EvaluationSuite:
        """Pin the suite: every task must be labelled, the live agent
        tool catalog is snapshotted into ``tool_versions``, and the
        definition digest becomes the suite's frozen identity."""
        suite = self._get_suite(suite_id)
        self.ctx.require(CAP_MANAGE_MODELS, suite.task_id)
        if suite.state != "draft":
            raise DomainError(ErrorCode.CONFLICT, "suite is already frozen")
        tasks = suite.definition.get("tasks", [])
        unlabeled = [t["example_id"] for t in tasks if not t.get("target_hash")]
        if unlabeled:
            raise DomainError(
                ErrorCode.VALIDATION,
                "every task needs a hidden label before freeze",
                safe_details={"unlabeled": unlabeled},
            )
        catalog = default_registry().catalog()
        definition = dict(suite.definition)
        definition["tool_versions"] = {
            "tools": [{"name": d["name"], "digest": _definition_digest(d)} for d in catalog],
            "catalog_digest": _definition_digest(catalog),
        }
        suite.definition = definition
        suite.digest = _definition_digest(definition)
        suite.state = "frozen"
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="evaluation.suite_frozen",
            target_type="evaluation_suite",
            target_id=suite.id,
            detail={"digest": suite.digest[:16]},
        )
        return suite
```

## EvaluationService.set_labels

Source: `services/studio-api/src/studio/domain/learning/promotion.py:EvaluationService.set_labels`.

```python
    def set_labels(
        self,
        suite_id: uuid.UUID,
        labels: list[dict[str, Any]],
    ) -> EvaluationSuite:
        """Attach hidden targets to a draft suite (write path is
        ``manage_models``; the READ path stays service-only). Each
        label hashes into its task's ``target_hash`` — the definition
        binds labels without carrying them."""
        suite = self._get_suite(suite_id)
        self.ctx.require(CAP_MANAGE_MODELS, suite.task_id)
        if suite.state != "draft":
            raise DomainError(ErrorCode.CONFLICT, "labels attach only to a draft suite")
        task_ids = {t["example_id"] for t in suite.definition.get("tasks", [])}
        seen: dict[str, str] = {}
        for raw in labels:
            target = EvalTarget.model_validate(raw)
            if target.example_id not in task_ids:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    f"label for unknown example '{target.example_id}'",
                )
            if target.example_id in seen:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    f"duplicate label for '{target.example_id}'",
                )
            row = self.db.execute(
                select(EvaluationLabel).where(
                    EvaluationLabel.workspace_id == self.ctx.workspace_id,
                    EvaluationLabel.suite_id == suite.id,
                    EvaluationLabel.example_id == target.example_id,
                )
            ).scalar_one_or_none()
            payload = target.model_dump(mode="json")
            payload.pop("example_id", None)
            # the stored form is what the hash binds — a verifier can
            # reproduce target_hash from the label row alone.
            seen[target.example_id] = _target_digest(payload)
            if row is None:
                row = EvaluationLabel(
                    workspace_id=self.ctx.workspace_id,
                    suite_id=suite.id,
                    example_id=target.example_id,
                    target=payload,
                )
                self.db.add(row)
            else:
                row.target = payload
        # Rehash: each labelled task records its target digest.
        definition = dict(suite.definition)
        tasks = [dict(t) for t in definition.get("tasks", [])]
        for task in tasks:
            digest = seen.get(task["example_id"])
            if digest:
                task["target_hash"] = digest
        definition["tasks"] = tasks
        suite.definition = definition
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="evaluation.labels_set",
            target_type="evaluation_suite",
            target_id=suite.id,
            detail={"labels": len(seen)},
        )
        return suite
```

## EvaluationService.start_run

Source: `services/studio-api/src/studio/domain/learning/promotion.py:EvaluationService.start_run`.

```python
    def start_run(
        self,
        *,
        suite_id: uuid.UUID,
        model_release_id: uuid.UUID,
        baseline_release_id: uuid.UUID | None = None,
    ) -> EvaluationRun:
        """Execute the §18.2 matched comparison: frozen suite, digest
        verified, both arms on the same tasks/tools/budget. Refuses
        honestly when no eval backend is installed — no fabricated
        scores ever stand in for a run."""
        suite = self._get_suite(suite_id)
        self.ctx.require(CAP_MANAGE_MODELS, suite.task_id)
        if suite.state != "frozen":
            raise DomainError(ErrorCode.CONFLICT, "suite must be frozen before a run")
        if _definition_digest(suite.definition) != suite.digest:
            raise DomainError(
                ErrorCode.CONFLICT,
                "suite definition drifted from its frozen digest — re-freeze a new version",
            )
        release = self._get_release(model_release_id)
        baseline = None
        if baseline_release_id is not None:
            baseline = self._get_release(baseline_release_id)
        capability = self.backend.capability()
        if capability is None:
            raise DomainError(
                ErrorCode.ENGINE_UNAVAILABLE,
                "no evaluation runtime installed — the matched comparison cannot fabricate scores",
            )
        definition = self._suite_def(suite)
        targets = self._targets_for_run(suite)
        missing_labels = [t.example_id for t in definition.tasks if t.example_id not in targets]
        run = EvaluationRun(
            workspace_id=self.ctx.workspace_id,
            suite_id=suite.id,
            suite_digest=suite.digest,
            model_release_id=release.id,
            baseline_release_id=baseline.id if baseline else None,
            state="running",
            backend=dict(capability),
            comparison={},
            contamination={},
            blockers=[],
            capability={
                "dataStatus": "fixture_only",
                "scientificStatus": "not_validated",
                "engineCapability": capability,
                "labelAccess": "evaluation service principal only",
            },
            created_by=self.ctx.principal_id,
        )
        self.db.add(run)
        self.db.flush()
        run.contamination = self._contamination(suite, release, targets)
        if missing_labels:
            run.state = "failed"
            run.error = {
                "code": "missing_labels",
                "message": "tasks without hidden labels cannot be scored",
                "examples": missing_labels,
            }
            self.db.flush()
            return run
        try:
            report = run_matched_comparison(
                suite=definition,
                targets=targets,
                backend=self.backend,
                tool_names=default_registry().names(),
            )
            report = report.model_copy(update={"suite_digest": suite.digest})
        except Exception as exc:  # engine failure is a run state, not a crash
            run.state = "failed"
            run.error = {"code": "engine_failure", "message": str(exc)[:300]}
            self.db.flush()
            return run
        artifact = self._persist_blob(
            json.dumps(report.model_dump(mode="json"), indent=1).encode(),
            original_name=f"eval-report-{run.id}.json",
            source_ids=[release.id],
        )
        run.report_artifact_id = artifact.id
        run.comparison = report.model_dump(mode="json")
        run.blockers = self._run_blockers(run)
        run.state = "completed"
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="evaluation.run_completed",
            target_type="evaluation_run",
            target_id=run.id,
            detail={
                "suiteId": str(suite.id),
                "releaseId": str(release.id),
                "verdict": report.verdict,
            },
        )
        return run
```

## PromotionService.approve_scope

Source: `services/studio-api/src/studio/domain/learning/promotion.py:PromotionService.approve_scope`.

```python
    def approve_scope(
        self,
        release_id: uuid.UUID,
        *,
        scope: str,
        limitations: list[str] | None = None,
        rationale: str | None = None,
    ) -> PromotionDecision:
        """The documented human release decision (§18.3-4): binds
        scope + limitations + the exact gate verdict into a
        ``model_release_scope`` approval (``approve_model`` capability
        — agents can never grant it)."""
        release = self._get(release_id)
        decision = self.db.execute(
            select(PromotionDecision)
            .where(
                PromotionDecision.workspace_id == self.ctx.workspace_id,
                PromotionDecision.model_release_id == release.id,
            )
            .order_by(PromotionDecision.created_at.desc(), PromotionDecision.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if decision is None:
            raise DomainError(
                ErrorCode.VALIDATION,
                "no promotion decision on record — run promotion_decide first",
            )
        bound = self._scope_bound_inputs(release, scope, list(limitations or []), decision)
        approval = grant(
            self.db,
            self.ctx,
            action=_SCOPE_APPROVAL_ACTION,
            bound_inputs=bound,
            rationale=rationale,
        )
        decision.approval_id = approval.id
        card = dict(decision.model_card)
        card["scope"] = scope
        card["approvedLimitations"] = list(limitations or [])
        decision.model_card = card
        self.db.flush()
        return decision
```

## PromotionService.decide

Source: `services/studio-api/src/studio/domain/learning/promotion.py:PromotionService.decide`.

```python
    def decide(self, release_id: uuid.UUID) -> PromotionDecision:
        """Run the §18.4 gate and record the verdict row.

        Hard blockers refuse promotion outright; claim blockers are
        stored promotion blockers — they bar any improvement claim and
        must be bound into the scoped release approval (§18.3)."""
        self.ctx.require(CAP_MANAGE_MODELS)
        release = self._get(release_id)
        blockers: list[dict[str, Any]] = []
        run_row: EvaluationRun | None = None

        # 1. lineage: dataset snapshot + rights/digest/drift (§18.4.1)
        run = None
        snapshot = None
        if release.training_run_id is not None:
            run = self.db.get(TrainingRun, release.training_run_id)
        if run is None:
            blockers.append(
                {
                    "kind": "lineage_incomplete",
                    "severity": _BLOCKER_HARD,
                    "detail": "release has no training run lineage",
                }
            )
        else:
            snapshot = self.db.get(DatasetSnapshot, run.snapshot_id)
            if snapshot is None:
                blockers.append(
                    {
                        "kind": "lineage_incomplete",
                        "severity": _BLOCKER_HARD,
                        "detail": "training run's dataset snapshot missing",
                    }
                )
            else:
                if snapshot.state != "frozen":
                    blockers.append(
                        {
                            "kind": "dataset_not_frozen",
                            "severity": _BLOCKER_HARD,
                            "detail": "dataset snapshot is not frozen",
                        }
                    )
                if snapshot.digest != run.snapshot_digest:
                    blockers.append(
                        {
                            "kind": "dataset_digest_drift",
                            "severity": _BLOCKER_HARD,
                            "detail": "snapshot digest drifted from the approved digest",
                        }
                    )

        # 2. training run must stand at candidate_release (§17.5)
        if run is not None and run.state not in ("candidate_release", "promoted"):
            blockers.append(
                {
                    "kind": "run_not_candidate",
                    "severity": _BLOCKER_HARD,
                    "detail": f"training run is {run.state}; promotion requires candidate_release",
                }
            )

        # 3. stored load/conversion validation verdict (§18.4.3) —
        #    promote() re-validates fresh via the registry.
        validation = release.validation or {}
        if validation.get("status") not in ("compatible", None):
            blockers.append(
                {
                    "kind": "validation_incompatible",
                    "severity": _BLOCKER_HARD,
                    "detail": f"latest validation verdict: {validation.get('status')}",
                }
            )
        if validation.get("status") is None:
            blockers.append(
                {
                    "kind": "validation_missing",
                    "severity": _BLOCKER_HARD,
                    "detail": "no compatibility validation on record",
                }
            )

        # 4. matched baseline comparison on a final-kind suite (§18.4.4)
        eval_run = self._latest_final_run(release)
        comparison: dict[str, Any] = {}
        suite: EvaluationSuite | None = None
        if eval_run is None:
            blockers.append(
                {
                    "kind": "missing_evaluation",
                    "severity": _BLOCKER_HARD,
                    "detail": "no completed final-kind evaluation run for this release",
                }
            )
        else:
            run_row = eval_run
            suite = self.db.get(EvaluationSuite, eval_run.suite_id)
            comparison = eval_run.comparison or {}
            if eval_run.suite_digest != (suite.digest if suite else ""):
                blockers.append(
                    {
                        "kind": "suite_drift",
                        "severity": _BLOCKER_HARD,
                        "detail": "the run's suite digest no longer matches the suite",
                    }
                )
            contamination = eval_run.contamination or {}
            if contamination.get("contaminated"):
                blockers.append(
                    {
                        "kind": "contamination",
                        "severity": _BLOCKER_HARD,
                        "detail": "; ".join(contamination.get("findings", []))[:400],
                    }
                )
            safety = (comparison.get("safety_regression") or {}).get("new_failures") or []
            if safety:
                blockers.append(
                    {
                        "kind": "safety_regression",
                        "severity": _BLOCKER_HARD,
                        "detail": f"new safety/privacy failures vs baseline: {safety}",
                    }
                )
            verdict = comparison.get("verdict")
            # §19.4: rising training performance with flat-or-worse
            # held-out performance is a failed promotion (AT-0803-1).
            if verdict != "improved":
                blockers.append(
                    {
                        "kind": "held_out_not_improved",
                        "severity": _BLOCKER_HARD,
                        "detail": (
                            f"held-out verdict '{verdict}': candidate aggregate "
                            f"{(comparison.get('aggregate') or {}).get('candidate')} vs "
                            f"baseline {(comparison.get('aggregate') or {}).get('baseline')}"
                        ),
                    }
                )
            denominators = comparison.get("denominators") or {}
            expected = (denominators.get("expected") or {}).get("candidate") or 0
            evaluated = (denominators.get("evaluated") or {}).get("candidate") or 0
            if expected and evaluated < expected:
                blockers.append(
                    {
                        "kind": "evaluation_incomplete",
                        "severity": _BLOCKER_HARD,
                        "detail": f"candidate evaluated {evaluated}/{expected} examples",
                    }
                )
            for th in comparison.get("thresholds") or []:
                if th.get("status") == "unknown":
                    blockers.append(
                        {
                            "kind": "unknown_threshold",
                            "severity": _BLOCKER_CLAIM,
                            "detail": (
                                f"metric '{th.get('metric')}' has no declared "
                                "acceptance value (U14) — stored blocker, never filled in"
                            ),
                        }
                    )
                elif th.get("status") == "fail":
                    blockers.append(
                        {
                            "kind": "threshold_fail",
                            "severity": _BLOCKER_HARD,
                            "detail": (
                                f"metric '{th.get('metric')}' observed "
                                f"{th.get('observed')} failed "
                                f"{th.get('direction')} {th.get('value')}"
                            ),
                        }
                    )

        eligible = not any(b["severity"] == _BLOCKER_HARD for b in blockers)
        model_card = self._model_card(release, run_row, suite, blockers, eligible)
        digest = hashlib.sha256(
            _canonical(
                {
                    "releaseId": str(release.id),
                    "evaluationRunId": str(run_row.id) if run_row else None,
                    "eligible": eligible,
                    "blockers": blockers,
                }
            )
        ).hexdigest()
        decision = PromotionDecision(
            workspace_id=self.ctx.workspace_id,
            model_release_id=release.id,
            evaluation_run_id=run_row.id if run_row else None,
            eligible=eligible,
            blockers=blockers,
            model_card=model_card,
            decision_digest=digest,
            created_by=self.ctx.principal_id,
        )
        self.db.add(decision)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="promotion.decision",
            target_type="model_release",
            target_id=release.id,
            detail={
                "eligible": eligible,
                "blockers": len(blockers),
                "evaluationRunId": str(run_row.id) if run_row else None,
            },
        )
        return decision
```

## PromotionService.promote

Source: `services/studio-api/src/studio/domain/learning/promotion.py:PromotionService.promote`.

```python
    def promote(
        self,
        release_id: uuid.UUID,
        *,
        scope: str,
        limitations: list[str] | None = None,
    ) -> PromotionDecision:
        """Gated promotion (§18.4): fresh decision → hard blockers
        refuse (AT-0803-1) → scoped approval re-validated at execution
        time → ``ModelRegistryService.promote`` performs its own
        release approval + compatibility re-check + atomic pointer
        move. Training runs never self-approve — the human
        ``approve_model`` grants do."""
        self.ctx.require(CAP_MANAGE_MODELS)
        release = self._get(release_id)
        decision = self.decide(release_id)
        hard = [b for b in decision.blockers if b["severity"] == _BLOCKER_HARD]
        if hard:
            raise DomainError(
                ErrorCode.MODEL_NOT_PROMOTABLE,
                "promotion blocked by the evaluation gate",
                safe_details={
                    "blockers": hard,
                    "decisionId": str(decision.id),
                },
            )
        bound = self._scope_bound_inputs(release, scope, list(limitations or []), decision)
        approval = require_valid(
            self.db,
            self.ctx,
            action=_SCOPE_APPROVAL_ACTION,
            bound_inputs=bound,
        )
        from studio.domain.learning.models import ModelRegistryService

        registry = ModelRegistryService(self.db, self.ctx, self.settings, vault=self.vault)
        registry.promote(release.id)
        decision.approval_id = approval.id
        card = dict(decision.model_card)
        card["scope"] = scope
        card["approvedLimitations"] = list(limitations or [])
        decision.model_card = card
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="promotion.executed",
            target_type="model_release",
            target_id=release.id,
            detail={
                "decisionId": str(decision.id),
                "scopeApprovalId": str(approval.id),
            },
        )
        return decision
```

## TrainingRunService.approve

Source: `services/studio-api/src/studio/domain/learning/sft.py:TrainingRunService.approve`.

```python
    def approve(
        self, run_id: uuid.UUID, *, decision: str, rationale: str | None = None
    ) -> TrainingRun:
        """Bind an approval to this run's exact inputs (§21.1 — the
        caller must hold ``approve_model``; agents never do)."""
        run = self._get(run_id)
        if run.state != "awaiting_approval":
            raise DomainError(
                ErrorCode.CONFLICT,
                f"training run is {run.state}, not awaiting_approval",
            )
        inputs = self._bound_inputs(run)
        approval = grant(
            self.db,
            self.ctx,
            action=_APPROVAL_ACTION,
            bound_inputs=inputs,
            decision=decision,
            rationale=rationale,
        )
        run.approval_id = approval.id
        run.bound_digest = bound_digest(inputs)
        if decision == "rejected":
            self._transition(run, "rejected")
        run.provenance = {
            **run.provenance,
            "approvalId": str(approval.id),
            "approvedBy": str(self.ctx.principal_id),
            "approvedAt": _now().isoformat(),
            "decision": decision,
        }
        self.db.flush()
        return run
```

## TrainingRunService.cancel

Source: `services/studio-api/src/studio/domain/learning/sft.py:TrainingRunService.cancel`.

```python
    def cancel(self, run_id: uuid.UUID) -> TrainingRun:
        """Cancel: pre-queue states stop immediately; a queued attempt
        is dropped and confirmed dead (nothing was executing); a
        running attempt is flagged cancel_requested — the executing
        thread's cancel event kills the container and lands the run in
        ``cancelled`` with its harvested checkpoint (AT-0801-3)."""
        self.ctx.require(CAP_MANAGE_MODELS)
        run = self._get(run_id)
        if run.state in ("draft", "dataset_validated", "awaiting_approval"):
            self._transition(run, "cancelled")
        elif run.state == "queued" and run.run_id is not None:
            self.runs.request_cancel(run.run_id)
            self.runs.confirm_cancelled(run.run_id)
            self.admission.release(run.run_id)
            self._transition(run, "cancelled")
        elif run.state == "running" and run.run_id is not None:
            self.runs.request_cancel(run.run_id)
        self.db.flush()
        return run
```

## TrainingRunService.create

Source: `services/studio-api/src/studio/domain/learning/sft.py:TrainingRunService.create`.

```python
    def create(
        self,
        *,
        snapshot_id: uuid.UUID,
        name: str,
        task_id: uuid.UUID | None = None,
        spec: dict[str, Any] | None = None,
    ) -> TrainingRun:
        """draft → dataset_validated (or blocked): builds the SFT
        dataset from the frozen snapshot and persists dataset + config
        artifacts. No training bytes are read for any other purpose."""
        self.ctx.require(CAP_MANAGE_MODELS, task_id)
        snap = self.db.execute(
            select(DatasetSnapshot).where(
                DatasetSnapshot.id == snapshot_id,
                DatasetSnapshot.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if snap is None:
            raise not_found("dataset snapshot")
        if task_id is not None:
            task = self.db.execute(
                select(ResearchTask).where(
                    ResearchTask.id == task_id,
                    ResearchTask.workspace_id == self.ctx.workspace_id,
                )
            ).scalar_one_or_none()
            if task is None:
                raise not_found("task")
        try:
            parsed = SftTrainSpec.model_validate(_merge_spec(spec))
        except Exception as exc:
            raise DomainError(ErrorCode.VALIDATION, f"invalid training spec: {exc}") from exc

        from workers.training.sft import runtime as sft_runtime

        run = TrainingRun(
            workspace_id=self.ctx.workspace_id,
            task_id=task_id,
            name=name[:160],
            state="draft",
            snapshot_id=snap.id,
            snapshot_digest=snap.digest,
            spec=parsed.model_dump(mode="json"),
            spec_digest=parsed.digest(),
            provenance={
                "createdBy": str(self.ctx.principal_id),
                "createdAt": _now().isoformat(),
                "chain": [],
            },
            capability=_capability_labels(
                image_available=sft_runtime.available(),
                composition=(snap.manifest or {})
                .get("provenance", {})
                .get("evidenceOrigin", {})
                .get("composition"),
            ),
            created_by=self.ctx.principal_id,
        )
        self.db.add(run)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="training_run.created",
            target_type="training_run",
            target_id=run.id,
            detail={"snapshotId": str(snap.id), "specDigest": run.spec_digest},
        )
        self._validate_dataset(run, snap)
        return run
```

## TrainingRunService.execute

Source: `services/studio-api/src/studio/domain/learning/sft.py:TrainingRunService.execute`.

```python
    def execute(
        self,
        run_id: uuid.UUID,
        attempt_id: uuid.UUID,
        *,
        cancel: threading.Event | None = None,
    ) -> TrainingRun:
        """queued → running → completed/failed/cancelled. The full
        eligibility gate runs BEFORE any dataset bytes leave the vault
        (AT-0801-2); artifacts land vault-scoped on completion."""
        if not self.settings.profile_training:
            raise DomainError(
                ErrorCode.ENGINE_UNAVAILABLE,
                "training profile is disabled (STUDIO_PROFILE_TRAINING=0)",
            )
        run = self._get(run_id)
        if run.state not in ("queued", "running"):
            raise DomainError(
                ErrorCode.CONFLICT, f"training run is {run.state}, not queued/running"
            )
        if self._gate(run, stage="execute"):
            return run
        if run.run_id is None:
            raise DomainError(ErrorCode.CONFLICT, "training run has no execution run attached")

        self.runs.accept_attempt(
            run_id=run.run_id, attempt_id=attempt_id, external_id=f"sft-{attempt_id}"
        )
        self.runs.start_attempt(run_id=run.run_id, attempt_id=attempt_id)
        if run.state == "queued":
            self._transition(run, "running")

        dataset_artifact = self.db.get(Artifact, run.dataset_artifact_id)
        if dataset_artifact is None:
            raise DomainError(ErrorCode.NOT_FOUND, "dataset artifact missing")
        # --- the only place dataset bytes are read: after all gates ---
        with self.vault.open_blob(self.ctx.workspace_id, dataset_artifact.storage_key) as f:
            dataset_bytes = f.read()

        resume_files: dict[str, bytes] | None = None
        spec = SftTrainSpec.model_validate(run.spec)
        if run.resume_from:
            resume_files = self._checkpoint_files(run, run.resume_from["checkpoint"])
            spec = spec.model_copy(
                update={
                    "resume": SftResumeSpec(
                        checkpoint_sha256=run.resume_from["checkpoint"]["sha256"],
                        from_step=run.resume_from["checkpoint"]["step"],
                        source_run_id=run.resume_from["sourceRunId"],
                        source_attempt_id=run.resume_from["sourceAttemptId"],
                    )
                }
            )

        from workers.training.sft import runtime as sft_runtime

        try:
            result = sft_runtime.IsolatedSft().train(
                spec, dataset=dataset_bytes, resume_files=resume_files, cancel=cancel
            )
        except TrainerFailure as exc:
            self._finish_exec(run, "failed", {"code": exc.code, "message": exc.message})
            self._transition(run, "failed")
            run.error = {"code": exc.code, "message": exc.message}
            self.db.flush()
            return run

        outcome = result.outcome
        # Persist harvested artifacts — checkpoints, telemetry, config,
        # adapter, result — all confidential vault blobs (§17.5).
        self._persist_run_artifacts(run, result)
        if outcome is not None:
            run.telemetry = {
                "stepsCompleted": outcome.steps_completed,
                "trainExamples": outcome.train_examples,
                "evalExamples": outcome.eval_examples,
                "finalTrainLoss": outcome.final_train_loss,
                "finalEvalLoss": outcome.final_eval_loss,
                "tail": outcome.telemetry_tail,
            }

        if result.status == "succeeded" and outcome is not None and outcome.usable:
            self._finish_exec(
                run,
                "succeeded",
                {
                    "adapter_sha256": outcome.adapter_sha256,
                    "steps_completed": outcome.steps_completed,
                    "parameter_proof": outcome.parameter_proof.model_dump(mode="json")
                    if outcome.parameter_proof
                    else None,
                },
            )
            self._transition(run, "completed")
        elif result.status == "cancelled":
            self._finish_exec(run, "cancelled", None)
            self._transition(run, "cancelled")
        elif result.status == "timed_out":
            self._finish_exec(run, "timed_out", {"code": "RUN_TIMEOUT"})
            self._transition(run, "failed")
            run.error = {"code": "RUN_TIMEOUT", "message": "training run timed out"}
        else:
            code = (result.error or {}).get("code", "training_failed")
            self._finish_exec(run, "failed", result.error or {"code": code})
            self._transition(run, "failed")
            run.error = result.error or {"code": code, "message": "trainer failed"}
        self.db.flush()
        return run
```

## TrainingRunService.queue

Source: `services/studio-api/src/studio/domain/learning/sft.py:TrainingRunService.queue`.

```python
    def queue(self, run_id: uuid.UUID) -> TrainingRun:
        """awaiting_approval → queued: approval re-checked, resources
        admitted, execution Run created (§13.6, AT-0801-2)."""
        self.ctx.require(CAP_MANAGE_MODELS)
        if not self.settings.profile_training:
            raise DomainError(
                ErrorCode.ENGINE_UNAVAILABLE,
                "training profile is disabled (STUDIO_PROFILE_TRAINING=0)",
            )
        run = self._get(run_id)
        if run.state != "awaiting_approval":
            raise DomainError(
                ErrorCode.CONFLICT,
                f"training run is {run.state}, not awaiting_approval",
            )
        if self._gate(run, stage="queue"):
            return run

        exec_run = self.runs.request(
            kind="sft_training",
            request={
                "schema_version": "1",
                "training_run_id": str(run.id),
                "snapshot_id": str(run.snapshot_id),
                "snapshot_digest": run.snapshot_digest,
                "dataset_digest": run.dataset_digest,
                "spec_digest": run.spec_digest,
                "dataset_artifact_id": str(run.dataset_artifact_id),
                "resume": run.resume_from,
            },
            task_id=run.task_id,
            max_attempts=1,
        )
        decision = self.admission.admit(exec_run.id, _envelope(run.spec), queue_name=_QUEUE_NAME)
        run.run_id = exec_run.id
        if not decision.admitted:
            # The execution run was blocked by admission; mirror the
            # reason onto the training run honestly.
            self._block(
                run,
                "insufficient_local_resources",
                "resource admission denied the training run",
                {"execRunId": str(exec_run.id)},
            )
            self.db.flush()
            return run
        self._transition(run, "queued")
        audit_record(
            self.db,
            self.ctx,
            action="training_run.queued",
            target_type="training_run",
            target_id=run.id,
            detail={"runId": str(exec_run.id)},
        )
        self.db.flush()
        return run
```

## TrainingRunService.resume

Source: `services/studio-api/src/studio/domain/learning/sft.py:TrainingRunService.resume`.

```python
    def resume(self, run_id: uuid.UUID) -> TrainingRun:
        """cancelled/failed → queued from the newest harvested
        checkpoint; the resume source + config are recorded so outputs
        stay attributable (AT-0801-3)."""
        self.ctx.require(CAP_MANAGE_MODELS)
        run = self._get(run_id)
        if run.state not in ("cancelled", "failed"):
            raise DomainError(
                ErrorCode.CONFLICT,
                f"training run is {run.state}; only cancelled/failed can resume",
            )
        if not run.checkpoints:
            raise DomainError(
                ErrorCode.CONFLICT, "no checkpoint to resume from — nothing was persisted"
            )
        latest = sorted(run.checkpoints, key=lambda c: c["step"])[-1]
        # Re-validate the approval for the SAME bound inputs — the
        # resume does not change dataset/spec digests.
        require_valid(
            self.db, self.ctx, action=_APPROVAL_ACTION, bound_inputs=self._bound_inputs(run)
        )
        source_run_id = str(run.run_id) if run.run_id else "unknown"
        run.resume_from = {
            "checkpoint": latest,
            "fromStep": latest["step"],
            "sourceRunId": source_run_id,
            "sourceAttemptId": latest.get("attemptId", source_run_id),
            "resumedAt": _now().isoformat(),
        }
        run.provenance = {
            **run.provenance,
            "chain": [
                *run.provenance.get("chain", []),
                {
                    "event": "resume",
                    "fromStep": latest["step"],
                    "checkpointSha256": latest["sha256"],
                    "sourceRunId": source_run_id,
                    "resumedBy": str(self.ctx.principal_id),
                    "resumedAt": _now().isoformat(),
                },
            ],
        }
        run.error = None
        # Re-queue: admit + enqueue a fresh execution Run.
        exec_run = self.runs.request(
            kind="sft_training",
            request={
                "schema_version": "1",
                "training_run_id": str(run.id),
                "snapshot_id": str(run.snapshot_id),
                "snapshot_digest": run.snapshot_digest,
                "dataset_digest": run.dataset_digest,
                "spec_digest": run.spec_digest,
                "dataset_artifact_id": str(run.dataset_artifact_id),
                "resume": run.resume_from,
            },
            task_id=run.task_id,
            max_attempts=1,
        )
        decision = self.admission.admit(exec_run.id, _envelope(run.spec), queue_name=_QUEUE_NAME)
        run.run_id = exec_run.id
        if not decision.admitted:
            self._block(
                run,
                "insufficient_local_resources",
                "resource admission denied the resume",
                {"execRunId": str(exec_run.id)},
            )
            self.db.flush()
            return run
        self._transition(run, "queued")
        audit_record(
            self.db,
            self.ctx,
            action="training_run.resumed",
            target_type="training_run",
            target_id=run.id,
            detail={"fromStep": latest["step"], "checkpointSha256": latest["sha256"]},
        )
        self.db.flush()
        return run
```

## TrainingRunService.submit

Source: `services/studio-api/src/studio/domain/learning/sft.py:TrainingRunService.submit`.

```python
    def submit(self, run_id: uuid.UUID) -> TrainingRun:
        """dataset_validated → awaiting_approval."""
        self.ctx.require(CAP_MANAGE_MODELS)
        run = self._get(run_id)
        self._transition(run, "awaiting_approval")
        run.provenance = {
            **run.provenance,
            "submittedBy": str(self.ctx.principal_id),
            "submittedAt": _now().isoformat(),
        }
        audit_record(
            self.db,
            self.ctx,
            action="training_run.submitted",
            target_type="training_run",
            target_id=run.id,
            detail={"specDigest": run.spec_digest},
        )
        self.db.flush()
        return run
```

## TrainingRunService.transition

Source: `services/studio-api/src/studio/domain/learning/sft.py:TrainingRunService.transition`.

```python
    def transition(
        self, run_id: uuid.UUID, *, to_state: str, rationale: str | None = None
    ) -> TrainingRun:
        """Reviewer-driven lifecycle moves: completed → evaluating →
        candidate_release → rejected. ``promoted`` is reachable only via
        the CS-0802 model registry's approved pointer move — a reviewer
        can never promote a run directly here."""
        self.ctx.require(CAP_REVIEW_SCIENCE)
        run = self._get(run_id)
        if to_state == "promoted":
            raise DomainError(
                ErrorCode.MODEL_NOT_PROMOTABLE,
                "promotion requires the model registry's approved serving pointer",
            )
        if to_state not in REVIEWER_STATES:
            raise DomainError(
                ErrorCode.VALIDATION, f"cannot transition a run into '{to_state}' manually"
            )
        self._transition(run, to_state)
        run.provenance = {
            **run.provenance,
            "chain": [
                *run.provenance.get("chain", []),
                {
                    "event": "transition",
                    "to": to_state,
                    "by": str(self.ctx.principal_id),
                    "at": _now().isoformat(),
                    "rationale": rationale,
                },
            ],
        }
        audit_record(
            self.db,
            self.ctx,
            action="training_run.transition",
            target_type="training_run",
            target_id=run.id,
            detail={"to": to_state},
        )
        self.db.flush()
        return run
```

## LearningWorkspaceService._prepare_job

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService._prepare_job`.

```python
    def _prepare_job(
        self, payload: dict[str, Any]
    ) -> tuple[str, LearningDataset, LearningModel | None, dict[str, Any]]:
        kind = payload.get("kind", "sft")
        if kind not in KINDS:
            raise DomainError(ErrorCode.VALIDATION, "Unknown learning job kind")
        dataset = self._owned(LearningDataset, str(payload.get("datasetId", "")))
        if dataset.state != "frozen":
            raise DomainError(
                ErrorCode.VALIDATION, "Freeze the validated dataset before starting a job"
            )
        check_dataset_sources(self.db, dataset)
        self.authorize_dataset_training(str(dataset.id))
        model = (
            self._owned(LearningModel, str(payload["modelId"])) if payload.get("modelId") else None
        )
        if kind != "chemprop" and model is None:
            raise DomainError(ErrorCode.VALIDATION, "Select a local model for this job")
        if model and model.details.get("license", "unknown") == "unknown":
            raise DomainError(
                ErrorCode.DATA_RIGHTS_UNKNOWN, "Declare the base model's license before training"
            )
        raw_config = payload.get("config") or {}
        if not isinstance(raw_config, dict):
            raise DomainError(ErrorCode.VALIDATION, "config must be a JSON object")
        config = dict(raw_config)
        if config.get("executionTarget", "local") not in {"local", "remote"}:
            raise DomainError(ErrorCode.VALIDATION, "executionTarget must be local or remote")
        if kind == "chemprop" and "epochs" in config:
            config["maxSteps"] = config["epochs"]
        backend = "chemprop" if kind == "chemprop" else (model.backend if model else "transformers")
        config["backend"] = backend
        device = config.get("device", "auto")
        if device not in {"auto", "cpu", "cuda", "mps"}:
            raise DomainError(ErrorCode.VALIDATION, "device must be auto, cpu, cuda or mps")
        if backend == "mlx" and device not in {"auto", "mps"}:
            raise DomainError(
                ErrorCode.ENGINE_UNSUPPORTED_INPUT, "MLX training uses Metal; choose auto or mps"
            )
        try:
            for name, default, lower, upper in [
                ("maxSteps", 20, 1, 100_000),
                ("batchSize", 1, 1, 128),
                ("maxTokens", 256, 16, 8192),
                ("maxSeconds", 3600, 10, 86_400),
                ("saveEvery", 10, 1, 1000),
                ("seed", 0, 0, 2**31 - 1),
                ("rank", 8, 1, 128),
                ("numGenerations", 2, 2, 16),
                ("ensembleSize", 2, 1, 8),
                ("hiddenDim", 64, 32, 2048),
                ("depth", 2, 1, 12),
            ]:
                value = int(config.get(name, default))
                if not lower <= value <= upper:
                    raise ValueError(f"{name} must be between {lower} and {upper}")
                config[name] = value
            learning_rate = float(config.get("learningRate", 1e-5))
            if not 0 < learning_rate <= 0.01:
                raise ValueError("learningRate must be between 0 and 0.01")
            config["learningRate"] = learning_rate
        except (ValueError, TypeError) as exc:
            raise DomainError(ErrorCode.VALIDATION, str(exc)) from exc
        expected_backend = {
            "dpo": {"transformers"},
            "grpo": {"transformers"},
            "molecular_transfer": {"reinvent"},
            "molecular_rl": {"reinvent"},
            "predict": {"chemprop"},
            "evaluate": {"mlx", "transformers", "chemprop"},
            "sft": {"mlx", "transformers"},
            "chemprop": {"chemprop"},
        }
        if backend not in expected_backend[kind]:
            raise DomainError(
                ErrorCode.VALIDATION, f"{kind} is unsupported by the selected backend"
            )
        if kind == "molecular_transfer" and config["maxSteps"] > 1000:
            raise DomainError(
                ErrorCode.VALIDATION, "Molecular transfer supports at most 1000 epochs"
            )
        training_rows = [r for r in dataset.rows if dataset.splits.get(r["id"]) == "train"]
        if kind == "chemprop":
            if len(training_rows) > 20_000 or any(
                len(str(row.get("smiles", ""))) > 512 for row in dataset.rows
            ):
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "Property jobs support at most 20,000 train rows and 512-character SMILES",
                )
            task = config.get("propertyTask", "regression")
            if task not in {"regression", "classification"}:
                raise DomainError(
                    ErrorCode.VALIDATION, "propertyTask must be regression or classification"
                )
            if task == "classification":
                labels = {row["target"] for row in training_rows if "target" in row}
                if labels != {0.0, 1.0} or any(
                    row.get("target") not in {0.0, 1.0} for row in dataset.rows
                ):
                    raise DomainError(
                        ErrorCode.VALIDATION,
                        "Binary classification requires 0/1 labels and both classes "
                        "in the train partition",
                    )
            config["propertyTask"] = task
        needed = {
            "sft": ("prompt", "response"),
            "dpo": ("prompt", "chosen", "rejected"),
            "grpo": ("prompt", "expected"),
            "chemprop": ("smiles", "target"),
            "molecular_transfer": ("smiles",),
            "molecular_rl": ("smiles",),
        }.get(kind, ())
        if kind == "sft":
            compatible_rows = [
                row
                for row in training_rows
                if row.get("messages") or (row.get("prompt") and row.get("response"))
            ]
        else:
            compatible_rows = [row for row in training_rows if all(key in row for key in needed)]
        if needed and (not training_rows or len(compatible_rows) != len(training_rows)):
            raise DomainError(
                ErrorCode.VALIDATION, f"Train rows require fields: {', '.join(needed)}"
            )
        if kind in {"chemprop", "predict"} or (kind == "evaluate" and backend == "chemprop"):
            for key in ("unit", "method", "property"):
                values = {str(row[key]) for row in dataset.rows if row.get(key)}
                if len(values) > 1:
                    raise DomainError(
                        ErrorCode.VALIDATION, f"One property job cannot mix {key} contexts"
                    )
            if dataset.source.get("kind") == "external_computed":
                computation = dataset.source["externalComputation"]
                for config_key, source_key in (
                    ("target", "property"),
                    ("unit", "unit"),
                    ("method", "method"),
                ):
                    if config_key in config and str(config[config_key]) != str(
                        computation[source_key]
                    ):
                        raise DomainError(
                            ErrorCode.VALIDATION,
                            f"{config_key} must match the retained dataset property context",
                        )
                    config[config_key] = computation[source_key]
            conditions = {
                json.dumps(row["conditions"], sort_keys=True)
                for row in dataset.rows
                if row.get("conditions")
            }
            if len(conditions) > 1:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "One property model requires consistent temperature, "
                    "pressure and process conditions",
                )
            if not re.fullmatch(
                r"[A-Za-z][A-Za-z0-9_.-]{0,95}", str(config.get("target", "property"))
            ):
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "Property name must be an identifier of at most 96 characters",
                )
            for field, maximum in (("unit", 64), ("method", 300)):
                if (
                    not 1
                    <= len(str(config.get(field, "1" if field == "unit" else "custom_dataset")))
                    <= maximum
                ):
                    raise DomainError(
                        ErrorCode.VALIDATION, f"{field} exceeds the property context limit"
                    )
            if kind == "chemprop" and config["maxSteps"] > 300:
                raise DomainError(ErrorCode.VALIDATION, "Property training supports 1-300 epochs")
            if model is not None and backend == "chemprop":
                scope = model.details.get("scope") or {}
                for field, scope_key in (
                    ("property", "name"),
                    ("unit", "unit"),
                    ("method", "method"),
                ):
                    actual = {str(row[field]) for row in dataset.rows if row.get(field)}
                    if actual and actual != {str(scope.get(scope_key))}:
                        raise DomainError(
                            ErrorCode.MODEL_INCOMPATIBLE,
                            f"Dataset {field} differs from the trained property model",
                        )
                trained_conditions = {
                    json.dumps(value, sort_keys=True)
                    for value in model.details.get("trainingConditions", [])
                }
                if (
                    conditions
                    and trained_conditions
                    and not conditions.issubset(trained_conditions)
                ):
                    raise DomainError(
                        ErrorCode.MODEL_INCOMPATIBLE,
                        "Dataset conditions differ from the trained property model",
                    )
        if kind == "evaluate":
            final_rows = [row for row in dataset.rows if dataset.splits.get(row["id"]) == "final"]
            required = ("smiles", "target") if backend == "chemprop" else ()
            if not final_rows or any(not all(key in row for key in required) for row in final_rows):
                raise DomainError(
                    ErrorCode.VALIDATION, "Evaluation requires compatible labelled final rows"
                )
            if backend != "chemprop" and any(
                not row.get("messages")
                and not (row.get("prompt") and (row.get("response") or row.get("expected")))
                for row in final_rows
            ):
                raise DomainError(
                    ErrorCode.VALIDATION, "Assistant final rows need prompts and reference answers"
                )
        if kind == "molecular_rl":
            if config.get("reward", "qed") not in {"qed", "molecular_weight", "logp"}:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "Molecular RL reward must be qed, molecular_weight or logp",
                )
        if kind == "grpo":
            if config.get("reward", "exact_match") != "exact_match":
                raise DomainError(
                    ErrorCode.ENGINE_UNSUPPORTED_INPUT,
                    "GRPO currently supports a grounded exact_match reward",
                )
            config["reward"] = "exact_match"
        # Request payload cannot inject arbitrary executable options or environment values.
        allowed = {
            "backend",
            "maxSteps",
            "batchSize",
            "maxTokens",
            "maxSeconds",
            "saveEvery",
            "seed",
            "rank",
            "learningRate",
            "reward",
            "target",
            "unit",
            "method",
            "ensembleSize",
            "hiddenDim",
            "depth",
            "device",
            "executionTarget",
            "resumeCheckpoint",
            "numGenerations",
            "rewardMin",
            "rewardMax",
            "propertyTask",
        }
        config = {k: v for k, v in config.items() if k in allowed}
        if backend == "chemprop":
            # The narrow Chemprop adapter uses its pinned engine schedule. Do not
            # record an assistant trainer's learning-rate field as if it were used.
            config.pop("learningRate", None)
            config["learningRateSchedule"] = {
                "engine": "chemprop-2.3.1-default",
                "initial": 0.0001,
                "maximum": 0.001,
                "final": 0.0001,
                "warmupEpochs": 2,
            }
        if config.get("executionTarget") == "remote":
            self.authorize_dataset_egress(str(dataset.id))
        return str(kind), dataset, model, config
```

## LearningWorkspaceService.create_job

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.create_job`.

```python
    def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        kind, dataset, model, config = self._prepare_job(payload)
        preflight = self.preflight_job(payload)
        ready = preflight["ready"]
        storage = preflight["estimated"]
        ready = ready and storage["available"]
        if payload.get("workflowId"):
            config["workflowId"] = str(payload["workflowId"])
            config["requiredFreeBytes"] = storage["requiredFreeBytes"]
        from studio.domain.agent_workspace.workflows import admit_job, record_job

        workflow, seconds = (
            admit_job(self.db, self.ctx, payload, "training")
            if ready
            else (None, int(config["maxSeconds"]))
        )
        if workflow is not None:
            config = {**config, "workflowId": str(workflow.id), "maxSeconds": seconds}
        row = LearningJob(
            workspace_id=self.ctx.workspace_id,
            owner_id=self.ctx.principal_id,
            name=_text(payload.get("name") or f"{kind} · {dataset.name}", "Job name"),
            kind=kind,
            dataset_id=dataset.id,
            model_id=model.id if model else None,
            state="queued" if ready else "blocked",
            config=config,
            result={
                "datasetDigest": dataset.digest,
                "dataKind": dataset.data_kind,
                "scientificStatus": "not_validated",
                "storagePreflight": storage,
                "preflight": preflight,
            },
            events=[],
            error=None
            if ready
            else "; ".join(
                item["message"] for item in preflight["checks"] if item["status"] == "fail"
            ),
        )
        self.db.add(row)
        self.db.flush()
        record_job(self.db, workflow, row.id, "training", seconds)
        return self._job(row)
```

## LearningWorkspaceService.import_dataset

Source: `services/studio-api/src/studio/domain/learning/workspace.py:LearningWorkspaceService.import_dataset`.

```python
    def import_dataset(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = _text(payload.get("name"), "Dataset name")
        kind = payload.get("dataKind", "experimental")
        rights = payload.get("rights", "unknown")
        if kind not in {"experimental", "literature", "computed", "synthetic", "user_authored"}:
            raise DomainError(ErrorCode.VALIDATION, "Unknown dataKind")
        if rights not in {"owned", "allowed", "unknown", "denied"}:
            raise DomainError(ErrorCode.VALIDATION, "Unknown training rights")
        source = payload.get("source") or {}
        if not isinstance(source, dict) or len(json.dumps(source)) > 20_000:
            raise DomainError(
                ErrorCode.VALIDATION, "Source provenance must be bounded JSON metadata"
            )
        try:
            rows, report = validate_import(payload)
        except ImportError as exc:
            raise DomainError(
                ErrorCode.ENGINE_UNAVAILABLE, "Install RDKit to validate molecular datasets"
            ) from exc
        except (ValueError, TypeError) as exc:
            raise DomainError(ErrorCode.VALIDATION, str(exc)) from exc
        row = LearningDataset(
            workspace_id=self.ctx.workspace_id,
            owner_id=self.ctx.principal_id,
            name=name,
            data_kind=kind,
            rights=rights,
            rows=rows,
            report=report,
            source=source,
            digest=digest({"rows": rows, "kind": kind, "rights": rights, "source": source}),
            state="validated" if rows else "rejected",
            splits={},
        )
        self.db.add(row)
        self.db.flush()
        return self._dataset(row, full=True)
```

## validate_import

Source: `services/studio-api/src/studio/domain/learning/workspace_runtime/data.py:validate_import`.

```python
def validate_import(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    content = payload.get("content")
    if not isinstance(content, str):
        raise ValueError("content must be UTF-8 text")
    mapping = payload.get("mapping") or {}
    if not isinstance(mapping, dict):
        raise ValueError("mapping must map field names to source columns")
    parsed = _parse(content, str(payload.get("format", "csv")).lower())
    rows: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    duplicates = 0
    seen: set[str] = set()
    for index, original in enumerate(parsed, 1):
        try:
            if "_parseError" in original:
                raise ValueError(original["_parseError"])
            record: dict[str, Any] = {"id": f"row-{index}", "sourceRow": index}
            for key in (
                "smiles",
                "target",
                "prompt",
                "response",
                "chosen",
                "rejected",
                "expected",
                "unit",
                "method",
                "documentId",
                "psmiles",
                "polymerId",
                "property",
                "sourceId",
                "metadata",
                "conditions",
                "sourceRefs",
                "evaluation",
                "messages",
                "tools",
            ):
                source_key = mapping.get(key, key)
                if source_key and source_key in original and original[source_key] is not None:
                    value = original[source_key]
                    if len(str(value)) > MAX_CELL:
                        raise ValueError(f"{key} exceeds {MAX_CELL} characters")
                    record[key] = value
            for key in ("metadata", "conditions", "sourceRefs", "evaluation", "tools"):
                if key in record and isinstance(record[key], str):
                    record[key] = json.loads(record[key])
            if "messages" in record:
                record["messages"] = chat_record(record["messages"])
            if "tools" in record and (
                not isinstance(record["tools"], list) or len(record["tools"]) > 128
            ):
                raise ValueError("tools must be a bounded list")
            metadata_columns = payload.get("metadataColumns", [])
            if not isinstance(metadata_columns, list) or len(metadata_columns) > 30:
                raise ValueError("metadataColumns must contain at most 30 columns")
            if metadata_columns:
                record["metadata"] = {
                    **(record.get("metadata") or {}),
                    **{str(key): original[key] for key in metadata_columns if key in original},
                }
            defaults = payload.get("defaults") or {}
            if not isinstance(defaults, dict):
                raise ValueError("defaults must be a metadata object")
            for key in ("unit", "method", "property", "conditions"):
                if key not in record and key in defaults:
                    record[key] = copy.deepcopy(defaults[key])
            if not record.get("smiles") and record.get("psmiles"):
                record["smiles"] = str(record["psmiles"])
            if record.get("smiles"):
                record["originalSmiles"] = str(record["smiles"])
                record.update(canonical_structure(str(record["smiles"])))
            if "target" in record and str(record["target"]).strip():
                value = float(record["target"])
                if not math.isfinite(value):
                    raise ValueError("Target must be a finite number")
                record["target"] = value
            elif "target" in record:
                del record["target"]
            if not record.get("smiles") and not record.get("prompt") and not record.get("messages"):
                raise ValueError("A row needs a valid SMILES structure, prompt or conversation")
            if record.get("chosen") and not record.get("rejected"):
                raise ValueError("Preference data requires both chosen and rejected responses")
            # Equal records retain exactly one identity; conflicting measurements remain visible.
            signature = digest(
                {k: v for k, v in record.items() if k not in {"id", "sourceRow", "originalSmiles"}}
            )
            if signature in seen:
                duplicates += 1
                continue
            seen.add(signature)
            rows.append(record)
        except (ValueError, TypeError, KeyError) as exc:
            rejects.append({"row": index, "reason": str(exc)[:300]})
    counts = Counter("molecular" if "smiles" in row else "assistant" for row in rows)
    return rows, {
        "total": len(parsed),
        "accepted": len(rows),
        "rejected": len(rejects),
        "duplicates": duplicates,
        "rejections": rejects[:1000],
        "rowKinds": dict(counts),
        "validation": "structure_and_schema",
        "scientificStatus": "not_validated",
    }
```

## CreateNotebook

Source: `services/studio-api/src/studio/domain/library/contracts.py:CreateNotebook`.

```python
class CreateNotebook(Contract):
    title: str = Field(min_length=1, max_length=300)
    folder_id: str | None = None
```

## CreatePage

Source: `services/studio-api/src/studio/domain/library/contracts.py:CreatePage`.

```python
class CreatePage(Contract):
    notebook_id: str
    title: str = Field(min_length=1, max_length=300)
    kind: Literal["note", "recipe", "formula", "smiles"] = "note"
    content: PageContent = Field(default_factory=PageContent)
    citations: list[Citation] = Field(default_factory=list, max_length=100)
```

## PageContent

Source: `services/studio-api/src/studio/domain/library/contracts.py:PageContent`.

```python
class PageContent(Contract):
    markdown: str = Field(default="", max_length=500_000)
    ingredients: list[Ingredient] = Field(default_factory=list, max_length=500)
    steps: list[str] = Field(default_factory=list, max_length=500)
    latex: str = Field(default="", max_length=20_000)
    smiles: str = Field(default="", max_length=10_000)
    variables: dict[str, str | float] = Field(default_factory=dict, max_length=100)
```

## UpdatePage

Source: `services/studio-api/src/studio/domain/library/contracts.py:UpdatePage`.

```python
class UpdatePage(Contract):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: PageContent | None = None
    citations: list[Citation] | None = Field(default=None, max_length=100)
    expected_revision: int = Field(ge=1)
```

## LibraryService.create_notebook

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.create_notebook`.

```python
    def create_notebook(
        self, title: str, folder_id: uuid.UUID | str | None = None
    ) -> dict[str, Any]:
        folder = self._get(LibraryFolder, folder_id) if folder_id else None
        row = Notebook(**self._new(), title=_title(title), folder_id=folder.id if folder else None)
        self.db.add(row)
        self.db.flush()
        return self._record(row)
```

## LibraryService.create_page

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.create_page`.

```python
    def create_page(
        self,
        notebook_id: uuid.UUID | str,
        title: str,
        kind: str = "note",
        content: dict[str, Any] | None = None,
        citations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        notebook = self._get(Notebook, notebook_id)
        if kind not in {"note", "recipe", "formula", "smiles"}:
            raise DomainError(ErrorCode.VALIDATION, "unsupported notebook page kind")
        row = NotebookPage(
            **self._new(),
            notebook_id=notebook.id,
            title=_title(title),
            kind=kind,
            content=_content(content or {}),
            citations=self._citations(citations or []),
        )
        self.db.add(row)
        self.db.flush()
        self._revision(row)
        return self._record(row)
```

## LibraryService.update_page

Source: `services/studio-api/src/studio/domain/library/service.py:LibraryService.update_page`.

```python
    def update_page(
        self,
        ident: uuid.UUID | str,
        expected_revision: int,
        *,
        title: str | None = None,
        content: dict[str, Any] | None = None,
        citations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        row = self._get(NotebookPage, ident)
        if row.version != expected_revision:
            raise revision_conflict("notebook page")
        values: dict[str, Any] = {}
        if title is not None:
            values["title"] = _title(title)
        if content is not None:
            values["content"] = _content(content)
        if citations is not None:
            values["citations"] = self._citations(citations)
        self._change(row, expected_revision, **values)
        self._revision(row)
        self._invalidate("page", row.id)
        return self._record(row)
```

## FormulationService.accept_process_revision

Source: `services/studio-api/src/studio/domain/materials/formulations.py:FormulationService.accept_process_revision`.

```python
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
```

## FormulationService.accept_revision

Source: `services/studio-api/src/studio/domain/materials/formulations.py:FormulationService.accept_revision`.

```python
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
```

## FormulationService.create_family

Source: `services/studio-api/src/studio/domain/materials/formulations.py:FormulationService.create_family`.

```python
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
```

## FormulationService.draft_process_revision

Source: `services/studio-api/src/studio/domain/materials/formulations.py:FormulationService.draft_process_revision`.

```python
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
```

## FormulationService.draft_revision

Source: `services/studio-api/src/studio/domain/materials/formulations.py:FormulationService.draft_revision`.

```python
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
```

## MaterialService.create_grade

Source: `services/studio-api/src/studio/domain/materials/service.py:MaterialService.create_grade`.

```python
    def create_grade(
        self,
        *,
        material_id: uuid.UUID,
        supplier: str,
        grade_name: str,
        active_content: dict[str, Any] | None = None,
        specifications: dict[str, Any] | None = None,
    ) -> MaterialGrade:
        """Register a commercial grade. ``active_content`` is a
        Quantity DTO — its basis is validated, never assumed."""
        self.ctx.require(CAP_MANAGE_SOURCES)
        self._identity(material_id)
        if not supplier.strip() or not grade_name.strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "supplier and grade_name are required",
                field_path="input.gradeName",
            )
        if active_content is not None:
            # validates unit + required basis inside the DTO
            Quantity.from_dto(active_content)
        row = MaterialGrade(
            workspace_id=self.ctx.workspace_id,
            material_id=material_id,
            supplier=supplier.strip(),
            grade_name=grade_name.strip(),
            active_content=active_content,
            specifications=specifications or {},
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="material_grade",
            aggregate_id=row.id,
            event_type="material.grade_created",
            payload={"gradeId": str(row.id), "materialId": str(material_id)},
        )
        audit_record(
            self.db,
            self.ctx,
            action="material.grade.create",
            target_type="material_grade",
            target_id=row.id,
        )
        return row
```

## MaterialService.create_identity

Source: `services/studio-api/src/studio/domain/materials/service.py:MaterialService.create_identity`.

```python
    def create_identity(
        self,
        *,
        kind: str,
        name: str,
        identifiers: list[dict[str, Any]] | None = None,
        structure: str | None = None,
        structure_format: str | None = None,
        aliases: list[dict[str, Any]] | None = None,
        confidentiality: str = "internal",
    ) -> MaterialIdentity:
        """Register an identity. A structure entered here is
        *unreviewed* — it cannot feed structure-required tools until
        ``review_structure`` (or an accepted match path) marks it."""
        self.ctx.require(CAP_MANAGE_SOURCES)
        if kind not in MATERIAL_KINDS:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"kind must be one of {', '.join(MATERIAL_KINDS)}",
                field_path="input.kind",
            )
        if not name.strip():
            raise DomainError(ErrorCode.VALIDATION, "name is required", field_path="input.name")
        if confidentiality not in CONFIDENTIALITY:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"confidentiality must be one of {', '.join(CONFIDENTIALITY)}",
                field_path="input.confidentiality",
            )
        for ident in identifiers or []:
            if not ident.get("scheme") or not ident.get("value"):
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "each identifier needs a scheme and a value",
                    field_path="input.identifiers",
                )
        status = "unreviewed" if structure else "none"
        row = MaterialIdentity(
            workspace_id=self.ctx.workspace_id,
            kind=kind,
            name=name.strip(),
            identifiers=identifiers or [],
            structure=structure,
            structure_format=structure_format if structure else None,
            structure_status=status,
            aliases=aliases or [],
            confidentiality=confidentiality,
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="material_identity",
            aggregate_id=row.id,
            event_type="material.identity_created",
            payload={"identityId": str(row.id), "kind": kind},
        )
        audit_record(
            self.db,
            self.ctx,
            action="material.identity.create",
            target_type="material_identity",
            target_id=row.id,
            detail={"kind": kind},
        )
        return row
```

## MaterialService.create_reference_product

Source: `services/studio-api/src/studio/domain/materials/service.py:MaterialService.create_reference_product`.

```python
    def create_reference_product(
        self,
        *,
        name: str,
        supplier: str | None = None,
        category: str | None = None,
        composition_knowledge: str = "unknown",
        aliases: list[dict[str, Any]] | None = None,
        documentation_artifact_ids: list[str] | None = None,
    ) -> ReferenceProduct:
        self.ctx.require(CAP_MANAGE_SOURCES)
        if composition_knowledge not in COMPOSITION_KNOWLEDGE:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"composition_knowledge must be one of {', '.join(COMPOSITION_KNOWLEDGE)}",
                field_path="input.compositionKnowledge",
            )
        if not name.strip():
            raise DomainError(ErrorCode.VALIDATION, "name is required", field_path="input.name")
        row = ReferenceProduct(
            workspace_id=self.ctx.workspace_id,
            name=name.strip(),
            supplier=supplier,
            category=category,
            composition_knowledge=composition_knowledge,
            aliases=aliases or [],
            documentation_artifact_ids=documentation_artifact_ids or [],
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="reference_product",
            aggregate_id=row.id,
            event_type="material.reference_created",
            payload={"productId": str(row.id)},
        )
        audit_record(
            self.db,
            self.ctx,
            action="material.reference.create",
            target_type="reference_product",
            target_id=row.id,
        )
        return row
```

## MaterialService.draft_reference_revision

Source: `services/studio-api/src/studio/domain/materials/service.py:MaterialService.draft_reference_revision`.

```python
    def draft_reference_revision(
        self, *, product_id: uuid.UUID, payload: dict[str, Any]
    ) -> ReferenceProductRevision:
        """New content revision. When composition is unknown the
        payload must not carry an ingredient list — a purchased
        product with no recipe has *no* composition (AT-0203-1)."""
        self.ctx.require(CAP_MANAGE_SOURCES)
        product = self._product(product_id)
        knowledge = payload.get("compositionKnowledge", product.composition_knowledge)
        composition = payload.get("composition")
        if knowledge == "unknown" and composition:
            raise DomainError(
                ErrorCode.VALIDATION,
                "compositionKnowledge is 'unknown' — an ingredient list "
                "cannot be recorded; leave composition empty",
                field_path="input.payload.composition",
            )
        current_max = self.db.execute(
            select(func.max(ReferenceProductRevision.revision)).where(
                ReferenceProductRevision.product_id == product.id
            )
        ).scalar_one()
        row = ReferenceProductRevision(
            workspace_id=self.ctx.workspace_id,
            product_id=product.id,
            revision=(current_max or 0) + 1,
            status="draft",
            payload=payload,
            content_hash=content_hash(payload),
            created_by=self.ctx.principal_id,
        )
        self.db.add(row)
        self.db.flush()
        return row
```

## MaterialService.freeze_reference_revision

Source: `services/studio-api/src/studio/domain/materials/service.py:MaterialService.freeze_reference_revision`.

```python
    def freeze_reference_revision(self, *, revision_id: uuid.UUID) -> ReferenceProductRevision:
        """Freeze a draft revision: becomes the product's current
        revision; any prior frozen revision supersedes (the DB
        trigger's only legal transition)."""
        self.ctx.require(CAP_MANAGE_SOURCES)
        rev = self.db.execute(
            select(ReferenceProductRevision).where(
                ReferenceProductRevision.id == revision_id,
                ReferenceProductRevision.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if rev is None:
            raise not_found("reference product revision")
        product = self._product(rev.product_id)
        if rev.status != "draft":
            raise DomainError(
                ErrorCode.VALIDATION,
                f"only a draft revision can be frozen (status is '{rev.status}')",
                field_path="input.revisionId",
            )
        prior = self.db.execute(
            select(ReferenceProductRevision).where(
                ReferenceProductRevision.product_id == product.id,
                ReferenceProductRevision.status == "frozen",
            )
        ).scalar_one_or_none()
        if prior is not None:
            prior.status = "superseded"
            self.db.flush()
        rev.status = "frozen"
        self.db.flush()
        product.current_revision_id = rev.id
        product.composition_knowledge = rev.payload.get(
            "compositionKnowledge", product.composition_knowledge
        )
        product.version += 1
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="material.reference.freeze",
            target_type="reference_product_revision",
            target_id=rev.id,
            detail={"revision": rev.revision},
        )
        return rev
```

## MaterialService.propose_match

Source: `services/studio-api/src/studio/domain/materials/service.py:MaterialService.propose_match`.

```python
    def propose_match(
        self,
        *,
        source_identity_id: uuid.UUID,
        candidate_identity_id: uuid.UUID,
        confidence: Decimal | str | None = None,
        rationale: str | None = None,
        proposed_by: str = "user",
    ) -> IdentityMatch:
        """A registry match is always a *proposal* first — imports and
        agents may propose; only review accepts (§5)."""
        self.ctx.require(CAP_MANAGE_SOURCES)
        self._identity(source_identity_id)
        self._identity(candidate_identity_id)
        if source_identity_id == candidate_identity_id:
            raise DomainError(ErrorCode.VALIDATION, "an identity cannot match itself")
        row = IdentityMatch(
            workspace_id=self.ctx.workspace_id,
            source_identity_id=source_identity_id,
            candidate_identity_id=candidate_identity_id,
            status="proposed",
            confidence=Decimal(confidence) if confidence is not None else None,
            rationale=rationale,
            proposed_by=proposed_by,
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="material_identity",
            aggregate_id=source_identity_id,
            event_type="material.match_proposed",
            payload={
                "matchId": str(row.id),
                "sourceIdentityId": str(source_identity_id),
                "candidateIdentityId": str(candidate_identity_id),
            },
        )
        return row
```

## MaterialService.reconcile_grades

Source: `services/studio-api/src/studio/domain/materials/service.py:MaterialService.reconcile_grades`.

```python
    def reconcile_grades(
        self, *, keep_grade_id: uuid.UUID, merge_grade_id: uuid.UUID, reason: str
    ) -> MaterialGrade:
        """The *only* merge path: an explicit reviewed reconciliation
        that records where the merged grade now points."""
        if self.ctx.principal_kind != "user":
            raise forbidden("grade reconciliation (human review required)")
        self.ctx.require(CAP_REVIEW_SCIENCE)
        if not reason:
            raise DomainError(
                ErrorCode.VALIDATION,
                "reconciliation requires a reason",
                field_path="input.reason",
            )
        keep = self._grade(keep_grade_id)
        merge = self._grade(merge_grade_id)
        merge.reconciled_into = keep.id
        merge.version += 1
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="material.grade.reconcile",
            target_type="material_grade",
            target_id=merge.id,
            detail={"into": str(keep.id), "reason": reason},
        )
        return merge
```

## MaterialService.review_match

Source: `services/studio-api/src/studio/domain/materials/service.py:MaterialService.review_match`.

```python
    def review_match(
        self, *, match_id: uuid.UUID, decision: str, rationale: str | None = None
    ) -> IdentityMatch:
        """Accept or reject a proposed match — human science review
        only."""
        if self.ctx.principal_kind != "user":
            raise forbidden("identity-match review (human review required)")
        self.ctx.require(CAP_REVIEW_SCIENCE)
        row = self.db.execute(
            select(IdentityMatch).where(
                IdentityMatch.id == match_id,
                IdentityMatch.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("identity match")
        if decision not in ("accepted", "rejected"):
            raise DomainError(
                ErrorCode.VALIDATION,
                "decision must be accepted or rejected",
                field_path="input.decision",
            )
        if row.status != "proposed":
            raise DomainError(
                ErrorCode.VALIDATION,
                f"match is already '{row.status}'",
                field_path="input.matchId",
            )
        row.status = decision
        row.reviewed_by = self.ctx.principal_id
        row.reviewed_at = datetime.now(UTC)
        row.rationale = rationale or row.rationale
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="material_identity",
            aggregate_id=row.source_identity_id,
            event_type="material.match_reviewed",
            payload={"matchId": str(row.id), "decision": decision},
        )
        audit_record(
            self.db,
            self.ctx,
            action="material.match.review",
            target_type="identity_match",
            target_id=row.id,
            detail={"decision": decision},
        )
        return row
```

## MaterialService.review_structure

Source: `services/studio-api/src/studio/domain/materials/service.py:MaterialService.review_structure`.

```python
    def review_structure(self, *, identity_id: uuid.UUID) -> MaterialIdentity:
        """Mark an identity's structure reviewed (human science review)
        — after this, structure-required tools may consume it."""
        if self.ctx.principal_kind != "user":
            raise forbidden("structure review (human review required)")
        self.ctx.require(CAP_REVIEW_SCIENCE)
        row = self._identity(identity_id)
        if not row.structure:
            raise DomainError(
                ErrorCode.MISSING_IDENTITY,
                "no structure to review",
                safe_details={"identityId": str(identity_id)},
            )
        row.structure_status = "reviewed"
        row.evidence_status = "reviewed"
        row.version += 1
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="material.identity.review_structure",
            target_type="material_identity",
            target_id=row.id,
        )
        return row
```

## ProjectService.create

Source: `services/studio-api/src/studio/domain/projects/service.py:ProjectService.create`.

```python
    def create(self, *, slug: str, name: str, description: str | None = None) -> Project:
        self.ctx.require(CAP_EDIT_TASK)
        if not slug.strip():
            raise DomainError(ErrorCode.VALIDATION, "slug is required", field_path="input.slug")
        if not name.strip():
            raise DomainError(ErrorCode.VALIDATION, "name is required", field_path="input.name")
        project = Project(
            workspace_id=self.ctx.workspace_id,
            slug=slug.strip(),
            name=name.strip(),
            description=description,
        )
        self.db.add(project)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="project",
            aggregate_id=project.id,
            event_type="project.created",
            payload={"projectId": str(project.id), "slug": project.slug},
        )
        audit_record(
            self.db,
            self.ctx,
            action="project.create",
            target_type="project",
            target_id=project.id,
            detail={"slug": project.slug},
        )
        return project
```

## ProjectService.research_inbox

Source: `services/studio-api/src/studio/domain/projects/service.py:ProjectService.research_inbox`.

```python
    def research_inbox(self) -> Project:
        """Reuse one active inbox without requiring a project setup step."""
        self.ctx.require(CAP_READ_PROJECT)
        self.ctx.require(CAP_EDIT_TASK)
        self.db.execute(
            select(Workspace).where(Workspace.id == self.ctx.workspace_id).with_for_update()
        ).scalar_one()
        project = self.db.execute(
            select(Project)
            .where(
                Project.workspace_id == self.ctx.workspace_id,
                Project.slug == "research-inbox",
                Project.status == "active",
            )
            .order_by(Project.created_at, Project.id)
            .limit(1)
        ).scalar_one_or_none()
        if project is not None:
            return project
        return self.create(
            slug="research-inbox",
            name="Research inbox",
            description="Research tasks organized automatically when no project is selected.",
        )
```

## FeasibilityService.fallback_view

Source: `services/studio-api/src/studio/domain/runs/feasibility.py:FeasibilityService.fallback_view`.

```python
    def fallback_view(self, run_id: uuid.UUID) -> dict[str, Any]:
        """The whole fallback surface for one run: latest evidence
        report, proposal state (unapproved by default), and the honest
        cloud capability — for the UI and API clients."""
        runs = RunService(self.db, self.ctx)
        run = runs.get(run_id)
        self.ctx.require(CAP_REQUEST_COMPUTE, run.task_id)
        report = self.latest_report(run.id)
        proposal = self.latest_proposal(run.id)
        return {
            "run": {
                "id": str(run.id),
                "kind": run.kind,
                "status": run.status,
                "taskId": str(run.task_id) if run.task_id else None,
                "error": run.error,
            },
            "report": self.report_to_dict(report) if report else None,
            "proposal": self.proposal_to_dict(proposal) if proposal else None,
            "cloud": cloud_capability(),
        }
```

## FeasibilityService.request_fallback

Source: `services/studio-api/src/studio/domain/runs/feasibility.py:FeasibilityService.request_fallback`.

```python
    def request_fallback(
        self,
        run_id: uuid.UUID,
        *,
        hardware: dict[str, Any] | None = None,
    ) -> FallbackDecision:
        """Evaluate, record, and apply the fallback policy.

        Feasible → the run is left untouched and no proposal exists;
        'prefer cloud' is never an input (AT-1001-1). Infeasible → the
        run is blocked with reasons (when still pending) and an export
        review *proposal* is created. The proposal is inert: it has no
        payload, no recipient, no provider call and no spend (§20.2).
        """
        run = self._lock_run(run_id)
        self.ctx.require(CAP_REQUEST_COMPUTE, run.task_id)
        report, evaluation = self._evaluate_locked(run, hardware)
        if evaluation.verdict == VERDICT_FEASIBLE:
            audit_record(
                self.db,
                self.ctx,
                action="run.fallback_local_feasible",
                target_type="run",
                target_id=run.id,
                detail={"reportId": str(report.id)},
            )
            return FallbackDecision(
                decision=DECISION_LOCAL_FEASIBLE,
                report_id=report.id,
                reason="a compatible local configuration fits — no export review is proposed",
            )

        proposal = self._propose_export(run, report)
        if run.status in ("requested", "awaiting_approval"):
            RunService(self.db, self.ctx).block(
                run.id,
                reason="local_infeasible",
                detail={
                    "reportId": str(report.id),
                    "reasons": evaluation.reasons,
                    "missing": evaluation.missing,
                },
            )
        audit_record(
            self.db,
            self.ctx,
            action="run.export_review_proposed",
            target_type="run",
            target_id=run.id,
            detail={"reportId": str(report.id), "proposalId": str(proposal.id)},
        )
        return FallbackDecision(
            decision=DECISION_EXPORT_PROPOSED,
            report_id=report.id,
            proposal_id=proposal.id,
            reason="no approved compatible local configuration fits",
        )
```

## RunService.request

Source: `services/studio-api/src/studio/domain/runs/queue.py:RunService.request`.

```python
    def request(
        self,
        *,
        kind: str,
        request: dict[str, Any],
        task_id: uuid.UUID | None = None,
        max_attempts: int = 3,
        deadline_at: datetime | None = None,
        requires_approval: bool = False,
    ) -> Run:
        """Persist a requested run. ``request`` must serialize to at
        most ``MAX_REQUEST_BYTES`` of canonical JSON — it carries
        scoped record IDs and bounded metadata, never payloads."""
        self.ctx.require("request_compute", task_id)
        if not isinstance(request, dict):
            raise DomainError(ErrorCode.VALIDATION, "request must be an object")
        encoded = canonical_json(request).encode()
        if len(encoded) > MAX_REQUEST_BYTES:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"run request exceeds {MAX_REQUEST_BYTES} bytes of bounded metadata",
                field_path="request",
            )
        if task_id is not None:
            from studio.persistence.models import ResearchTask

            task = self.db.execute(
                select(ResearchTask).where(
                    ResearchTask.workspace_id == self.ctx.workspace_id,
                    ResearchTask.id == task_id,
                )
            ).scalar_one_or_none()
            if task is None:
                raise not_found("task")
        run = Run(
            workspace_id=self.ctx.workspace_id,
            task_id=task_id,
            kind=kind,
            status="awaiting_approval" if requires_approval else "requested",
            request=request,
            request_digest=request_digest(request),
            requested_by=self.ctx.principal_id,
            max_attempts=max_attempts,
            deadline_at=deadline_at,
        )
        self.db.add(run)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="run.requested",
            target_type="run",
            target_id=run.id,
            detail={"kind": kind, "digest": run.request_digest},
        )
        return run
```

## RunService.request_cancel

Source: `services/studio-api/src/studio/domain/runs/queue.py:RunService.request_cancel`.

```python
    def request_cancel(self, run_id: uuid.UUID) -> Run:
        """queued/running -> cancel_requested. Visible until execution
        actually stops; an acknowledgment is not proof the children
        stopped (§7.3)."""
        run = self._get_for_update(run_id)
        self._transition(run, "cancel_requested")
        run.cancel_requested_at = datetime.now(UTC)
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="run",
            aggregate_id=run.id,
            event_type="run.cancel.requested",
            payload={"runId": str(run.id)},
        )
        self.db.flush()
        return run
```

## validate_draft_payload

Source: `services/studio-api/src/studio/domain/tasks/contract.py:validate_draft_payload`.

```python
def validate_draft_payload(payload: Any) -> None:
    """Structural validation for a contract *draft* (§11.1).

    Rejects malformed known vocabulary and revision-identity keys.
    Unknown top-level fields are preserved on the draft — they are
    explicit unknowns for review, not silently evaluable content.
    Raises ``DomainError`` with a client-safe field path.
    """
    path = "input.payload"
    if not isinstance(payload, dict):
        raise _err(path, "contract payload must be an object")
    owned = sorted(k for k in payload if k in ROW_OWNED_FIELDS)
    if owned:
        raise _err(
            f"{path}.{owned[0]}",
            "payload must not carry revision identity fields "
            f"({', '.join(owned)}) — the service assigns them",
        )
    version = payload.get("schema_version")
    if version is not None and (
        not isinstance(version, str) or version not in SUPPORTED_SCHEMA_VERSIONS
    ):
        raise _err(
            f"{path}.schema_version",
            f"unsupported contract schema_version {version!r}; "
            f"this service writes {sorted(SUPPORTED_SCHEMA_VERSIONS)}",
        )

    mode = payload.get("mode")
    if mode is not None and (not isinstance(mode, str) or mode not in CONTRACT_MODES):
        raise _err(f"{path}.mode", f"unknown contract mode {mode!r}")
    target_kind = payload.get("target_kind")
    if target_kind is not None and (
        not isinstance(target_kind, str) or target_kind not in CONTRACT_TARGET_KINDS
    ):
        raise _err(
            f"{path}.target_kind", f"unknown contract target_kind {target_kind!r}"
        )
    scope = payload.get("matching_scope")
    if scope is not None and (
        not isinstance(scope, str) or scope not in CONTRACT_MATCH_SCOPES
    ):
        raise _err(
            f"{path}.matching_scope",
            f"unknown contract matching_scope {scope!r}",
        )
    for key in ("baseline_revision_id", "reference_revision_id", "approval_id"):
        _check_uuid(payload.get(key), f"{path}.{key}")
    if "objective" in payload and payload["objective"] is not None and not isinstance(
        payload["objective"], str
    ):
        raise _err(f"{path}.objective", "objective must be a string")
    if "fixture_only" in payload and not isinstance(payload["fixture_only"], bool):
        raise _err(f"{path}.fixture_only", "fixture_only must be a boolean")

    metrics = payload.get("metrics")
    if metrics is not None:
        if not isinstance(metrics, list):
            raise _err(f"{path}.metrics", "metrics must be a list")
        for i, raw in enumerate(metrics):
            _validate_metric(raw, f"{path}.metrics[{i}]")

    legacy = payload.get(LEGACY_REQUIRED_METRICS_KEY)
    if legacy is not None and not isinstance(legacy, list):
        raise _err(
            f"{path}.{LEGACY_REQUIRED_METRICS_KEY}",
            "legacy requiredMetrics must be a list",
        )

    for key in ("hard_constraints", "hardConstraints", "constraints"):
        gates = payload.get(key)
        if gates is None:
            continue
        if not isinstance(gates, list):
            raise _err(f"{path}.{key}", f"{key} must be a list")
        for i, raw in enumerate(gates):
            _validate_constraint(raw, f"{path}.{key}[{i}]")

    warnings = payload.get("warnings")
    if warnings is not None and (
        not isinstance(warnings, list)
        or any(not isinstance(w, str) for w in warnings)
    ):
        raise _err(f"{path}.warnings", "warnings must be a list of strings")

    unknowns = payload.get("unknowns")
    if unknowns is not None and (
        not isinstance(unknowns, list)
        or any(not isinstance(u, str) for u in unknowns)
    ):
        raise _err(f"{path}.unknowns", "unknowns must be a list of strings")
```

## validate_freeze_payload

Source: `services/studio-api/src/studio/domain/tasks/contract.py:validate_freeze_payload`.

```python
def validate_freeze_payload(payload: Any) -> None:
    """The gate freeze actually needs (§11.1, pack SuccessContract
    frozen rules): a fully canonical payload — every resolved metric
    identified and bound, no declared unknowns, no unknown top-level
    fields. Unknown content stays a draft for review instead of
    freezing into a contract that only looks assessable."""
    validate_draft_payload(payload)
    path = "input.payload"
    unknown_fields = sorted(
        k for k in payload if k not in KNOWN_TOP_LEVEL_FIELDS
    )
    if unknown_fields:
        raise _err(
            f"{path}.{unknown_fields[0]}",
            "unknown contract field(s) cannot be frozen silently "
            f"({', '.join(unknown_fields)}) — review them or save a "
            "successor draft",
        )
    declared_unknowns = payload.get("unknowns") or []
    if declared_unknowns:
        raise _err(
            f"{path}.unknowns",
            "a contract with declared unknowns cannot be frozen — "
            f"resolve: {', '.join(declared_unknowns)}",
        )
    resolved = resolve_metrics(payload)
    if not resolved.metrics:
        raise _err(
            f"{path}.metrics",
            "a contract without evaluable metrics cannot be frozen",
        )
    for i, metric in enumerate(resolved.metrics):
        ident = metric.get("id") or metric.get("name") or metric.get("label")
        if not ident:
            raise _err(
                f"{path}.metrics[{i}]",
                "a frozen metric needs an id, name or label",
            )
        try:
            bound = metric_bound(metric)
        except DomainError as exc:
            raise _err(
                f"{path}.metrics[{i}]",
                f"metric {ident!r} bound is not parseable: {exc.message}",
            ) from None
        if bound is None:
            raise _err(
                f"{path}.metrics[{i}]",
                f"metric {ident!r} carries no bound — a contract clause "
                "must state operator and target (missing stays missing; "
                "it is never defaulted)",
            )
```

## TaskMemoryService.create_summary

Source: `services/studio-api/src/studio/domain/tasks/memory.py:TaskMemoryService.create_summary`.

```python
    def create_summary(
        self,
        task_id: uuid.UUID,
        *,
        body: str,
        source_ids: list[str],
        generator: str,
    ) -> TaskSummary:
        """Persist a derived summary pinned to the *current* contract
        revision and its source IDs. The summary never writes back —
        there is deliberately no apply/update path from a summary into
        structured state (§10.1)."""
        task = self._task(task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if not (body or "").strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "summary body must not be empty",
                field_path="input.body",
            )
        if not (generator or "").strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "generator (model/version or 'deterministic') is required",
                field_path="input.generator",
            )
        coverage: dict[str, int] = {"claims": 0, "decisions": 0, "chunks": 0}
        claim_ids = {
            str(c.id)
            for c in self.db.execute(
                select(EvidenceClaim).where(EvidenceClaim.workspace_id == self.ctx.workspace_id)
            ).scalars()
        }
        decision_ids = {
            str(d.id)
            for d in self.db.execute(
                select(TaskDecision).where(
                    TaskDecision.workspace_id == self.ctx.workspace_id,
                    TaskDecision.task_id == task.id,
                )
            ).scalars()
        }
        for sid in source_ids:
            if sid in claim_ids:
                coverage["claims"] += 1
            elif sid in decision_ids:
                coverage["decisions"] += 1
            else:
                coverage["chunks"] += 1
        row = TaskSummary(
            workspace_id=self.ctx.workspace_id,
            task_id=task.id,
            contract_revision_id=task.current_contract_revision_id,
            body=body,
            source_ids=source_ids,
            coverage=coverage,
            generator=generator,
            created_by=self.ctx.principal_id,
        )
        self.db.add(row)
        self.db.flush()
        audit_record(
            self.db,
            self.ctx,
            action="task.summary.create",
            target_type="task_summary",
            target_id=row.id,
            detail={"taskId": str(task.id), "generator": generator},
        )
        return row
```

## TaskMemoryService.end_session

Source: `services/studio-api/src/studio/domain/tasks/memory.py:TaskMemoryService.end_session`.

```python
    def end_session(self, session_id: uuid.UUID) -> ResearchSession:
        """Close a session with a structured end snapshot — counts and
        IDs, not prose that could be mistaken for canonical state."""
        session = self._session(session_id)
        task = self._task(session.task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if session.status != "active":
            raise DomainError(
                ErrorCode.CONFLICT,
                f"session is already '{session.status}'",
                field_path="input.sessionId",
            )
        open_q = self.db.execute(
            select(func.count(TaskQuestion.id)).where(
                TaskQuestion.workspace_id == self.ctx.workspace_id,
                TaskQuestion.task_id == task.id,
                TaskQuestion.status == "open",
            )
        ).scalar_one()
        decisions = self.db.execute(
            select(func.count(TaskDecision.id)).where(
                TaskDecision.workspace_id == self.ctx.workspace_id,
                TaskDecision.task_id == task.id,
            )
        ).scalar_one()
        candidate_ids = [
            str(c.id)
            for c in self.db.execute(
                select(CandidateRevision).where(
                    CandidateRevision.workspace_id == self.ctx.workspace_id,
                    CandidateRevision.task_id == task.id,
                )
            ).scalars()
        ]
        session.status = "ended"
        session.ended_at = datetime.now(UTC)
        session.end_snapshot = {
            "contractRevisionId": (
                str(task.current_contract_revision_id)
                if task.current_contract_revision_id
                else None
            ),
            "openQuestions": open_q,
            "decisionCount": decisions,
            "candidateRevisionIds": candidate_ids,
        }
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="research_session",
            aggregate_id=session.id,
            event_type="session.ended",
            payload={"taskId": str(task.id)},
        )
        return session
```

## TaskMemoryService.post_message

Source: `services/studio-api/src/studio/domain/tasks/memory.py:TaskMemoryService.post_message`.

```python
    def post_message(
        self,
        session_id: uuid.UUID,
        *,
        role: str,
        kind: str = "message",
        content: str,
        refs: dict[str, Any] | None = None,
    ) -> SessionMessage:
        session = self._session(session_id)
        task = self._task(session.task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if session.status != "active":
            raise DomainError(
                ErrorCode.CONFLICT,
                "cannot post to an ended session",
                field_path="input.sessionId",
            )
        if role not in ("user", "assistant", "system", "tool"):
            raise DomainError(
                ErrorCode.VALIDATION,
                f"unknown message role '{role}'",
                field_path="input.role",
            )
        if kind not in ("message", "proposal", "tool_call", "tool_result", "rationale"):
            raise DomainError(
                ErrorCode.VALIDATION,
                f"unknown message kind '{kind}'",
                field_path="input.kind",
            )
        if not (content or "").strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "message content must not be empty",
                field_path="input.content",
            )
        row = SessionMessage(
            workspace_id=self.ctx.workspace_id,
            session_id=session.id,
            role=role,
            kind=kind,
            content=content,
            refs=refs or {},
            created_by=self.ctx.principal_id,
        )
        self.db.add(row)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="research_session",
            aggregate_id=session.id,
            event_type="session.message.posted",
            payload={
                "sessionId": str(session.id),
                "taskId": str(session.task_id),
                "messageId": str(row.id),
                "role": role,
                "kind": kind,
                "content": content,
                "refs": refs or {},
            },
        )
        return row
```

## TaskMemoryService.raise_question

Source: `services/studio-api/src/studio/domain/tasks/memory.py:TaskMemoryService.raise_question`.

```python
    def raise_question(
        self, task_id: uuid.UUID, *, question: str, blocking: bool = False
    ) -> TaskQuestion:
        task = self._task(task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if not (question or "").strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "question must not be empty",
                field_path="input.question",
            )
        row = TaskQuestion(
            workspace_id=self.ctx.workspace_id,
            task_id=task.id,
            question=question,
            blocking=blocking,
            status="open",
            raised_by=self.ctx.principal_id,
        )
        self.db.add(row)
        self.db.flush()
        return row
```

## TaskMemoryService.resolve_question

Source: `services/studio-api/src/studio/domain/tasks/memory.py:TaskMemoryService.resolve_question`.

```python
    def resolve_question(self, question_id: uuid.UUID, *, resolution: str) -> TaskQuestion:
        row = self.db.execute(
            select(TaskQuestion).where(
                TaskQuestion.id == question_id,
                TaskQuestion.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise not_found("task question")
        task = self._task(row.task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if row.status != "open":
            raise DomainError(
                ErrorCode.CONFLICT,
                f"question is already '{row.status}'",
                field_path="input.questionId",
            )
        if not (resolution or "").strip():
            raise DomainError(
                ErrorCode.VALIDATION,
                "a resolution is required",
                field_path="input.resolution",
            )
        row.status = "resolved"
        row.resolution = resolution
        row.resolved_at = datetime.now(UTC)
        self.db.flush()
        return row
```

## TaskMemoryService.start_session

Source: `services/studio-api/src/studio/domain/tasks/memory.py:TaskMemoryService.start_session`.

```python
    def start_session(
        self, task_id: uuid.UUID, *, token_budget: int = DEFAULT_TOKEN_BUDGET
    ) -> ResearchSession:
        """Compile the context manifest and open a session anchored to
        it (§11.1) — resumption is from this snapshot, not an empty
        chat."""
        if token_budget <= 0:
            raise DomainError(
                ErrorCode.VALIDATION,
                "token budget must be positive",
                field_path="input.tokenBudget",
            )
        task = self._task(task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        items, _ = self.collect_items(task)
        selected, omitted, over_budget = compile_manifest(items, token_budget)
        manifest = ContextManifest(
            workspace_id=self.ctx.workspace_id,
            task_id=task.id,
            contract_revision_id=task.current_contract_revision_id,
            compiler_version=COMPILER_VERSION,
            token_budget=token_budget,
            token_estimate=sum(i.tokens for i in selected),
            over_budget=over_budget,
            items=[
                {
                    "kind": i.kind,
                    "refId": i.ref_id,
                    "text": i.text,
                    "tokens": i.tokens,
                    "pinned": i.pinned,
                }
                for i in selected
            ],
            omitted=[{"kind": i.kind, "refId": i.ref_id, "tokens": i.tokens} for i in omitted],
            warnings=[
                {"kind": i.kind, "refId": i.ref_id, "text": i.text} for i in selected if i.pinned
            ],
            created_by=self.ctx.principal_id,
        )
        self.db.add(manifest)
        self.db.flush()
        session = ResearchSession(
            workspace_id=self.ctx.workspace_id,
            task_id=task.id,
            start_manifest_id=manifest.id,
            start_contract_revision_id=task.current_contract_revision_id,
            status="active",
            started_by=self.ctx.principal_id,
        )
        self.db.add(session)
        self.db.flush()
        # §17.5: the session pins the model release it begins with;
        # a later serving-pointer move never re-anchors it (AT-0802-2).
        from studio.domain.learning.models import pin_session_start

        pin_session_start(self.db, workspace_id=self.ctx.workspace_id, session_id=session.id)
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="research_session",
            aggregate_id=session.id,
            event_type="session.started",
            payload={"taskId": str(task.id), "manifestId": str(manifest.id)},
        )
        return session
```

## TaskService.close

Source: `services/studio-api/src/studio/domain/tasks/service.py:TaskService.close`.

```python
    def close(
        self,
        *,
        task_id: uuid.UUID,
        closure_decision: str,
        packet: dict[str, Any] | None = None,
        candidate_revision_id: uuid.UUID | None = None,
    ) -> ResearchTask:
        """Close with a recorded closure decision (§7.1).

        Human reviewers only: an agent principal is denied even if it
        somehow holds review_science, and supported_success additionally
        needs the frozen-contract evidence gates. When the task carries
        more than one research-accepted candidate the reviewer must name
        the candidate the close binds to — the evaluator never picks one
        by revision (PAR-02 §5-6).
        """
        task = self._task(task_id)
        if self.ctx.principal_kind != "user":
            raise forbidden("task closure (human review required)")
        self.ctx.require(CAP_REVIEW_SCIENCE)
        if task.workflow_state != "awaiting_review":
            raise DomainError(
                ErrorCode.VALIDATION,
                "task must be awaiting_review to close",
                field_path="input.taskId",
            )
        if closure_decision not in TASK_CLOSURES:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"closureDecision must be one of {', '.join(TASK_CLOSURES)}",
                field_path="input.closureDecision",
            )
        accepted = self._accepted_candidates(task)
        if len(accepted) > 1 and candidate_revision_id is None:
            raise DomainError(
                ErrorCode.VALIDATION,
                "multiple accepted candidates — close requires an explicit "
                "candidateRevisionId binding the report the reviewer saw",
                field_path="input.candidateRevisionId",
                safe_details={
                    "candidateRevisionIds": [str(c.id) for c in accepted]
                },
            )
        bound_packet = self._closeout_packet(
            task, candidate_revision_id=candidate_revision_id
        )
        if closure_decision == "supported_success":
            self._success_evidence_gate(bound_packet)
        elif closure_decision == "supported_failure":
            self._failure_evidence_gate(bound_packet, packet)
        prior_contract = task.current_contract_revision_id
        task.workflow_state = "closed"
        task.closure_decision = closure_decision
        task.version += 1
        self.db.flush()
        self._decision(
            task,
            "closure",
            {
                "closureDecision": closure_decision,
                "contractRevisionId": str(prior_contract) if prior_contract else None,
                "candidateRevisionId": bound_packet.get("candidateRevisionId"),
                "evaluationCycle": task.evaluation_cycle,
                "packet": bound_packet,
                "reviewerPacket": packet or {},
            },
        )
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="task",
            aggregate_id=task.id,
            event_type="task.closed",
            payload={
                "taskId": str(task.id),
                "closureDecision": closure_decision,
                "contractRevisionId": str(prior_contract) if prior_contract else None,
                "evaluationCycle": task.evaluation_cycle,
            },
        )
        audit_record(
            self.db,
            self.ctx,
            action="task.close",
            target_type="task",
            target_id=task.id,
            detail={"closureDecision": closure_decision},
        )
        return task
```

## TaskService.create

Source: `services/studio-api/src/studio/domain/tasks/service.py:TaskService.create`.

```python
    def create(
        self,
        *,
        project_id: uuid.UUID,
        title: str,
        mode: str,
        objective: str | None = None,
        target_kind: str | None = None,
        mode_inputs: dict[str, Any] | None = None,
    ) -> ResearchTask:
        """Create a draft task. Mode-required inputs may be absent — they
        persist as unresolved, never filled with made-up values (§11)."""
        self.ctx.require(CAP_EDIT_TASK, project_id)
        if mode not in TASK_MODES:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"mode must be one of {', '.join(TASK_MODES)}",
                field_path="input.mode",
            )
        if target_kind is not None and target_kind not in TARGET_KINDS:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"targetKind must be one of {', '.join(TARGET_KINDS)}",
                field_path="input.targetKind",
            )
        scope = (mode_inputs or {}).get("matchScope")
        if scope is not None and scope not in MATCH_SCOPES:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"matchScope must be one of {', '.join(MATCH_SCOPES)}",
                field_path="input.modeInputs.matchScope",
            )
        if not title.strip():
            raise DomainError(ErrorCode.VALIDATION, "title is required", field_path="input.title")
        task = ResearchTask(
            workspace_id=self.ctx.workspace_id,
            project_id=project_id,
            owner_id=self.ctx.principal_id,
            mode=mode,
            target_kind=target_kind or "unknown",
            title=title.strip(),
            objective=objective,
            mode_inputs=mode_inputs or {},
            workflow_state="draft",
            reviewer_id=None,
        )
        self.db.add(task)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="task",
            aggregate_id=task.id,
            event_type="task.created",
            payload={"taskId": str(task.id), "projectId": str(project_id)},
        )
        audit_record(
            self.db,
            self.ctx,
            action="task.create",
            target_type="task",
            target_id=task.id,
            detail={"mode": mode},
        )
        return task
```

## TaskService.draft_contract

Source: `services/studio-api/src/studio/domain/tasks/service.py:TaskService.draft_contract`.

```python
    def draft_contract(
        self, *, task_id: uuid.UUID, payload: dict[str, Any]
    ) -> SuccessContractRevision:
        """New contract draft (rev = max+1). Thresholds live in the
        payload; unresolved fields stay unresolved.

        The canonical contract schema is validated before anything is
        written (PAR-01): malformed vocabulary is rejected, but a draft
        may carry explicit unknown top-level fields for review —
        nothing missing is ever filled with a scientific default."""
        validate_draft_payload(payload)
        # Lock the task row: concurrent draft/freezes must serialize so
        # revision = max+1 cannot race the (task_id, revision) unique
        # constraint into a bare IntegrityError (CS-1201).
        task = self._task(task_id, for_update=True)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        current_max = self.db.execute(
            select(func.max(SuccessContractRevision.revision)).where(
                SuccessContractRevision.task_id == task.id
            )
        ).scalar_one()
        rev = SuccessContractRevision(
            workspace_id=self.ctx.workspace_id,
            task_id=task.id,
            revision=(current_max or 0) + 1,
            status="draft",
            payload=payload,
            content_hash=content_hash(payload),
            created_by=self.ctx.principal_id,
        )
        self.db.add(rev)
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="task",
            aggregate_id=task.id,
            event_type="contract.drafted",
            payload={"taskId": str(task.id), "revisionId": str(rev.id)},
        )
        return rev
```

## TaskService.freeze_contract

Source: `services/studio-api/src/studio/domain/tasks/service.py:TaskService.freeze_contract`.

```python
    def freeze_contract(self, *, revision_id: uuid.UUID) -> SuccessContractRevision:
        """Freeze a draft revision: it becomes the task's current
        contract; any prior frozen revision supersedes (immutable —
        the DB trigger guarantees the status-only transition)."""
        rev = self.db.execute(
            select(SuccessContractRevision).where(
                SuccessContractRevision.id == revision_id,
                SuccessContractRevision.workspace_id == self.ctx.workspace_id,
            )
        ).scalar_one_or_none()
        if rev is None:
            raise not_found("contract revision")
        # Lock the task row (same lock point as draft_contract) so the
        # status check + version bump serialize against concurrent
        # contract writes on this task (CS-1201).
        task = self._task(rev.task_id, for_update=True)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if rev.status != "draft":
            raise DomainError(
                ErrorCode.VALIDATION,
                f"only a draft revision can be frozen (status is '{rev.status}')",
                field_path="input.revisionId",
            )
        # Freeze is the action that binds the contract for evaluation:
        # require the payload to be fully canonical — every resolved
        # metric identified and bound, no declared unknowns, no unknown
        # top-level fields. Anything short stays a draft for review
        # instead of silently freezing (PAR-01).
        validate_freeze_payload(rev.payload)
        prior = self.db.execute(
            select(SuccessContractRevision).where(
                SuccessContractRevision.task_id == task.id,
                SuccessContractRevision.status == "frozen",
            )
        ).scalar_one_or_none()
        if prior is not None:
            prior.status = "superseded"  # the only legal transition
            self.db.flush()
        rev.status = "frozen"
        self.db.flush()
        task.current_contract_revision_id = rev.id
        task.version += 1
        self.db.flush()
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="task",
            aggregate_id=task.id,
            event_type="contract.frozen",
            payload={"taskId": str(task.id), "revisionId": str(rev.id)},
        )
        audit_record(
            self.db,
            self.ctx,
            action="contract.freeze",
            target_type="success_contract_revision",
            target_id=rev.id,
            detail={"revision": rev.revision},
        )
        return rev
```

## TaskService.reopen

Source: `services/studio-api/src/studio/domain/tasks/service.py:TaskService.reopen`.

```python
    def reopen(self, *, task_id: uuid.UUID, reason: str) -> ResearchTask:
        """Reopen a closed task: records the decision, keeps the prior
        closure packet linked to its contract, new evaluation cycle."""
        task = self._task(task_id)
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if task.workflow_state != "closed":
            raise DomainError(
                ErrorCode.VALIDATION,
                "only a closed task can be reopened",
                field_path="input.taskId",
            )
        if not reason:
            raise DomainError(
                ErrorCode.VALIDATION,
                "reopening requires a reason",
                field_path="input.reason",
            )
        prior = {
            "closureDecision": task.closure_decision,
            "contractRevisionId": (
                str(task.current_contract_revision_id)
                if task.current_contract_revision_id
                else None
            ),
            "evaluationCycle": task.evaluation_cycle,
        }
        task.workflow_state = "active"
        task.closure_decision = None
        task.evaluation_cycle += 1
        task.version += 1
        self.db.flush()
        self._decision(task, "reopen", {"reason": reason, "priorClosure": prior})
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="task",
            aggregate_id=task.id,
            event_type="task.reopened",
            payload={"taskId": str(task.id), "reason": reason},
        )
        audit_record(
            self.db,
            self.ctx,
            action="task.reopen",
            target_type="task",
            target_id=task.id,
            detail={"reason": reason},
        )
        return task
```

## TaskService.transition

Source: `services/studio-api/src/studio/domain/tasks/service.py:TaskService.transition`.

```python
    def transition(
        self,
        *,
        task_id: uuid.UUID,
        to_state: str,
        reason: str | None = None,
        expected_version: int | None = None,
    ) -> ResearchTask:
        """Workflow transition (not closure). Compare-and-swap on
        ``expected_version`` when provided (§5.3)."""
        task = self._task(task_id)
        if to_state == "closed":
            raise DomainError(
                ErrorCode.VALIDATION,
                "closing requires the taskClose command with a closure decision",
                field_path="input.toState",
            )
        if to_state not in TASK_STATES:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"unknown state '{to_state}'",
                field_path="input.toState",
            )
        allowed = ALLOWED_TRANSITIONS[task.workflow_state]
        if to_state not in allowed:
            raise DomainError(
                ErrorCode.VALIDATION,
                f"transition {task.workflow_state} -> {to_state} is not allowed",
                field_path="input.toState",
            )
        self.ctx.require(CAP_EDIT_TASK, task.project_id)
        if expected_version is not None and task.version != expected_version:
            raise revision_conflict("task")
        kind = "state_change"
        if task.workflow_state == "awaiting_review" and to_state == "active":
            if not reason:
                raise DomainError(
                    ErrorCode.VALIDATION,
                    "returning to active requires a review reason",
                    field_path="input.reason",
                )
            kind = "review_return"
        task.workflow_state = to_state
        task.version += 1
        self.db.flush()
        self._decision(task, kind, {"toState": to_state, "reason": reason})
        publish(
            self.db,
            self.ctx.workspace_id,
            aggregate_type="task",
            aggregate_id=task.id,
            event_type="task.transitioned",
            payload={
                "taskId": str(task.id),
                "toState": to_state,
                "reason": reason,
            },
        )
        audit_record(
            self.db,
            self.ctx,
            action="task.transition",
            target_type="task",
            target_id=task.id,
            detail={"toState": to_state},
        )
        return task
```
