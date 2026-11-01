# Agentic research verification

Validation recorded on 2026-11-01 for the agent sidebar, private library,
provider models, and learning workspace.

## Automated checks

- A broad backend run passed **682 tests** before the final Responses protocol
  extension.
- The final full web run passed **148 tests**, including notebook refresh,
  draft conflict recovery, folder selection and conversation-switching checks.
- The latest focused browser run passed **4 end-to-end tests**.
  `test-results/.last-run.json` records `passed` with no failed tests.

These runs overlap and describe different checkpoints of the work. Their counts
should not be added together as a single final suite.

## Live provider and local learning

The configured provider completed a native function call and tool-result round
trip through Responses using its existing stored credential. The credential was
preserved, and no private notebook content was sent. Local evidence:
`.runtime/evidence/live-provider-function-check.json`.

The Apple Silicon MLX smoke performed **two real LoRA optimizer steps** on the
Qwen3 0.6B 4-bit model using synthetic chemistry examples. Adapter weights changed
between checkpoints; the final checkpoint reloaded for inference and emitted a
structured tool call. The one-example held-out comparison completed, with zero
exact matches for both base and candidate. This establishes execution and
reload, rather than improved model quality. Local evidence:
`.runtime/evidence/learning-mlx-smoke.json`.

Chemprop completed **one epoch each of regression and binary classification**
on 30 SMILES with computed fixture labels: 24 training, three development and
three final rows. Held-out metrics were recorded, and the saved regression model
reloaded to produce 30 predictions with matching model lineage. These small
computed fixtures establish software operation, not performance on a user's
chemistry or scientific validation. Local evidence:
`.runtime/evidence/learning-chemprop-smoke.json`.

## Native application

The macOS app bundle built successfully, with the reported build size of
**9.51 MiB**. Native smoke checks passed for a Finder-like startup environment,
bundled startup IPC, private log permissions, owned-backend shutdown, reuse of an
existing backend, and preservation of unrelated development services. Local
evidence: `.runtime/evidence/native/native-smoke.json`.

A clean native launch reached the migrated, signed-in workspace, and the agent
sidebar displayed the existing configured provider. The readiness probe confirmed
both the database and bundled frontend were available. macOS initially paused
startup for Documents-folder access. Local evidence:
`.runtime/evidence/workspace-native-current.json`. See
[desktop-macos.md](desktop-macos.md) for the permission and launch workflow.

## Remaining execution coverage

Transformers SFT/DPO/GRPO, REINVENT transfer learning and molecular RL, and a
physical self-hosted GPU/CUDA worker have implemented execution paths but were
not exercised against those runtimes or hardware in this verification. Chemprop
was tested on CPU; selected CUDA/MPS availability and dispatch behavior were
checked through adapter tests. Missing runtimes and unavailable devices remain
explicit capability states.
