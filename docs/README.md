# Chemistry Studio documentation

Use **Help & documentation** after signing in, or open `/help` in the running
Studio. The same manuals are readable here when the backend is unavailable.
The bundled help uses a curated set of repository Markdown files and works
without a paid model or an external documentation service.

## Choose a starting point

| You want to | Start here |
|---|---|
| Use the Studio for the first time | [Getting started](usage/getting-started.md) |
| Learn chemistry terms with everyday analogies | [Chemistry basics](usage/chemistry-basics.md), [guided first exercise](usage/guided-first-research.md), and [glossary](usage/chemistry-glossary.md) |
| Edit notebooks, recipes, formulae, and citations | [Notebooks and editing](usage/notebooks-and-editing.md) |
| Organize research and scientific records | [Projects and tasks](usage/projects-and-tasks.md) |
| Change the app or backend | [Local development](development/local-development.md) and [architecture](development/architecture.md) |
| Install, administer, back up, or recover | [Operations manuals](operations/README.md) |
| Look up interfaces and environment settings | [Reference index](reference/README.md) |

## Read current behavior correctly

Core research records and manual workflows work without a model. Optional
engines need their own dependencies and inputs. A saved calculation, training
run, software test, or completed pilot is evidence of execution; it does not
establish scientific accuracy or laboratory success. Review the result's
provenance, method, source rights, and validation status.

The current deployment is local to one trusted machine and workspace.
[Installation](operations/installation.md) describes the supported loopback
configuration. Team/LAN hosting and production distribution require separate
implementation and verification.

## Documentation ownership

Current manuals live in `docs/usage`, `docs/development`, `docs/operations`, and
`docs/reference`. The help manifest explicitly registers the pages included in
the app. Editing Markdown does not edit private notebooks or research records.
See [testing and documentation](development/testing-and-docs.md) for regeneration
and checks: `make docs-generate`, `make docs-check`, and `pnpm docs:check`.

`docs/chemistry-studio` is the original handoff specification;
`docs/design` contains design specifications; `docs/execution` records historical
implementation and release evidence; `docs/research` records research pilots.
Those documents are useful source material, but are not current usage manuals
and are not automatically bundled into Help. Files ending in `-verification.md`,
`local-ui-verification.md`, and `pilot-gate.md` under operations are verification
records or generated reports, rather than instructions to operate today's app.
