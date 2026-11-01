# Complete interface reference

Generated from repository sources and reviewed contract notes. Use these pages alongside the user, developer and operator guides. This reference contains no live workspace data.

Coverage: **92 REST method/path definitions**, **64 GraphQL queries**, **105 callable mutations**, **252 additional GraphQL type declarations**, **43 configuration names**.

The Strawberry-generated `/graphql` transport is documented separately. SPA/static assets are not data API operations. The desktop runtime probe is conditional.

| Reference | Contents |
| --- | --- |
| [commands](commands.md) | Development and operations command reference |
| [configuration](configuration.md) | Environment and build configuration reference |
| [contracts-agent](contracts-agent.md) | Private agent API — JSON contract details |
| [contracts-artifacts](contracts-artifacts.md) | Artifact transfer API — JSON contract details |
| [contracts-auth](contracts-auth.md) | Session and owner setup API — JSON contract details |
| [contracts-background](contracts-background.md) | Background service API — JSON contract details |
| [contracts-events](contracts-events.md) | Event stream API — JSON contract details |
| [contracts-learning](contracts-learning.md) | Local learning and worker API — JSON contract details |
| [contracts-library](contracts-library.md) | Private library API — JSON contract details |
| [contracts-simulations](contracts-simulations.md) | Polymer simulation API — JSON contract details |
| [contracts-system](contracts-system.md) | Health, readiness and desktop API — JSON contract details |
| [contracts-workflows](contracts-workflows.md) | Research workflow API — JSON contract details |
| [graphql-contracts](graphql-contracts.md) | GraphQL command state and validation contracts |
| [graphql-mutation](graphql-mutation.md) | GraphQL mutation reference |
| [graphql-overview](graphql-overview.md) | GraphQL transport and conventions |
| [graphql-query](graphql-query.md) | GraphQL query reference |
| [graphql-types](graphql-types.md) | GraphQL type catalog |
| [rest-agent](rest-agent.md) | Private agent API |
| [rest-artifacts](rest-artifacts.md) | Artifact transfer API |
| [rest-auth](rest-auth.md) | Session and owner setup API |
| [rest-background](rest-background.md) | Background service API |
| [rest-events](rest-events.md) | Event stream API |
| [rest-learning](rest-learning.md) | Local learning and worker API |
| [rest-library](rest-library.md) | Private library API |
| [rest-overview](rest-overview.md) | REST transport, authentication and errors |
| [rest-simulations](rest-simulations.md) | Polymer simulation API |
| [rest-system](rest-system.md) | Health, readiness and desktop API |
| [rest-workflows](rest-workflows.md) | Research workflow API |

## Keeping this reference current

```bash
make docs-generate
make docs-check
```

Edit the implementation or schema first, then update reviewed notes in `docs/reference-source/metadata.json` and the mandatory reviewed examples in `docs/reference-source/rest-examples.json`, then regenerate. The check rejects missing/stale metadata, unresolved router registrations, missing contract symbols and generated drift. GraphQL SDL must separately pass `infra/ci/export_schema.py --check`. Generated files in this directory should not be edited by hand.
