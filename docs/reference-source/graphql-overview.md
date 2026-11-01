# GraphQL transport and conventions

Core project/task, evidence, lab, run, model and export commands use Strawberry GraphQL at `/graphql`. Private workspace aliases also exist here alongside newer REST services. The committed schema is the full wire contract; the [query](graphql-query.md), [mutation](graphql-mutation.md) and [type](graphql-types.md) articles are generated from it.

## Transport and access

Send a JSON POST containing `query`, optional `variables`, and optional `operationName` to the loopback API. Strawberry also accepts its supported query transport; use POST for commands. The interactive GraphQL IDE is disabled. FastAPI `/docs`, `/redoc` and `/openapi.json` are disabled in the application, so this offline reference is the documentation entrypoint.

Session-cookie/Bearer precedence, loopback Host/Origin checks and server-side capability ceilings are the same as the [REST transport](rest-overview.md). GraphQL constructs authentication lazily inside resolvers: an authentication or authorization failure may appear as a GraphQL error within an HTTP 200 response. Inspect both top-level errors and mutation payload errors.

```graphql
query HelpExample {
  viewer { __typename }
}
```

This example is read-only and illustrative. Help does not run it or obtain credentials.

## Command examples

These examples are parsed and type-checked against the committed schema during reference generation. They are not executed. Replace variables with the canonical IDs returned by your own workspace and review the command's preconditions before sending it. The example idempotency keys must be unique for independent real commands.

Create a project using required nonempty slug/name fields:

```graphql
mutation HelpCreateProject {
  projectCreate(input: {
    slug: "synthetic-help-example"
    name: "Synthetic Help example"
    idempotencyKey: "help-example-project-create"
  }) {
    project { id }
    errors { code message fieldPath retryable }
  }
}
```

Freeze a reviewed complete draft. The variable must be an existing draft contract revision ID; unresolved metrics/unknowns cause a validation failure:

```graphql
mutation HelpFreezeContract($revision: ID!) {
  contractFreeze(input: {
    revisionId: $revision
    idempotencyKey: "help-example-contract-freeze"
  }) {
    contractRevision { id }
    errors { code message fieldPath retryable }
  }
}
```

Request a local molecular descriptor calculation through a mutation namespace. Runtime/profile admission still applies:

```graphql
mutation HelpDescribeStructure {
  runs {
    quickDescribeStructure(input: {
      smiles: "CCO"
      idempotencyKey: "help-example-describe-ethanol"
    }) {
      run { id }
      errors { code message fieldPath retryable }
    }
  }
}
```

Record a measurement through two namespace levels. Supply an accessible real sample ID and record only the measurement you actually made; values here are synthetic formatting examples:

```graphql
mutation HelpRecordMeasurement($sample: ID!, $value: JSON!) {
  lab {
    measurements {
      measurementRecord(input: {
        sampleId: $sample
        method: "synthetic-example-method"
        repeatType: "technical"
        value: $value
      }) {
        __typename
      }
    }
  }
}
```

## IDs, connections and revisions

Use canonical Relay IDs returned by GraphQL for arguments declared `ID`; do not substitute REST UUIDs or manufacture cross-workspace IDs. Node lookup and connections validate scope. Read each operation's declared argument types, because some fields intentionally use UUID/scalar or JSON inputs instead.

Connections use bounded keyset pagination, opaque cursors and `pageInfo`. Unsupported backward pagination is rejected by the relevant resolver. Cursor signatures bind scope/filter/order; reuse a cursor with its original query and filters. Defaults and permitted arguments are listed in each declaration.

Commands expose their own input types. Supply `expectedVersion`/revision and `idempotencyKey` only where declared. Reusing an idempotency key with a different payload returns `IDEMPOTENCY_MISMATCH`; stale versions require reload and review. Approval may be invalidated by changed digests, scope, provider configuration or other reviewed state. `clientMutationId` is correlation, not authorization.

## Mutation namespaces

Namespaces such as `materials`, `lab` and `learning` group commands. They are not the final operation. For example, the reference's `lab.measurements.measurementRecord` means select `lab`, then `measurements`, then `measurementRecord(input: ...)` inside a mutation. The catalog recursively lists every callable leaf, including these nested measurement commands.

Returned object fields must be selected explicitly. `!` means non-null; `[T]` means list. Read nested input/result fields in the [type catalog](graphql-types.md). `JSON` is a flexible scalar with service validation; private library/agent/learning aliases use the corresponding [REST JSON contracts](rest-overview.md). It does not mean every JSON object is accepted.

## Error forms

Mutation results commonly include `errors` and `clientMutationId` alongside their domain result. A domain error escaping a resolver appears in top-level GraphQL errors with `extensions.code`, `fieldPath`, `retryable` and `safeDetails`. GraphQL parse/type/selection errors are separate framework errors. The [REST error table](rest-overview.md) lists the domain codes and recovery categories, but GraphQL errors do not necessarily use those HTTP statuses.

An engine/profile unavailable error is a real blocked state. Neither a successful schema query nor successful synthetic test establishes external-provider quality, scientific validity, a promoted model, a laboratory result or an approved export.

## Maintaining the contract

Backend Strawberry definitions own GraphQL. Run `make schema-export` after changing them, regenerate Relay with `pnpm relay`, then regenerate the Help reference. Do not edit the committed SDL, Relay output or generated Help pages by hand. JSON contract mirrors have their own canonical source/sync workflow; see the developer guide.
