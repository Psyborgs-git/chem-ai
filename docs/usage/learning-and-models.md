# Learning, datasets and models

**Local learning** manages owner-private datasets, models and durable jobs. Its four tabs are **Runs**, **Datasets**, **Models** and **New run**. The separate **Model registry** manages the older reviewed workspace model-release workflow; private model activation and reviewed registry promotion are different actions.

Before training, read the [base-model and LoRA explanation](chemistry-basics.md#understand-learning-before-training) and the [learning glossary](chemistry-glossary.md#models-and-learning). The [first research exercise](guided-first-research.md) needs no training and creates no experimental training labels.

## Check runtime readiness

Open **Local learning → Runtimes**. Each backend reports **Ready** or **Setup needed** with actual missing dependencies/hardware. Refresh after an administrator installs a runtime. Choosing a model or queueing a job does not install Python packages, weights, a GPU driver or a licensed prior.

MLX uses Apple Silicon and requires Metal access. Transformers can use a compatible local or self-hosted runtime. Chemprop handles molecular property models. REINVENT handles declared molecular learning/optimization tracks. See [Learning workspace operations](../operations/learning-workspace.md) for exact isolated environment and remote-worker setup.

## Import and inspect data

Open **Datasets → Import data**. Choose Molecules, Assistant examples or Preferences, select the file, and provide the displayed column mapping. Supported private import formats are CSV, JSONL, SMI and SDF, with a 20 MiB and 50,000-row limit.

Under **Source and rights**, record data origin and permission truthfully. Options distinguish measured/experimental, extracted, computed and synthetic data. **Needs review** does not grant training rights; choose **I own this data** or **Source permits training** only when that is accurate.

Select **Import and validate**. Inspect accepted/rejected rows, duplicate counts, reports and source context. Structure validation and parser acceptance do not certify an experimental label.

| Track | Required example content |
| --- | --- |
| Assistant fine-tuning | `prompt` and `response`, or complete validated `messages`/`tools` |
| Preference training | `prompt`, `chosen`, `rejected` |
| Agent reinforcement learning | `prompt`, `expected`; exact-match reward |
| Property model | `smiles`, `target`, declared property/unit/method context |
| Molecular transfer | Appropriate molecular structures and a compatible prior |
| Prediction | Molecular structures plus a compatible trained property model |

Assistant tool examples must preserve matched calls/results and the complete conversation. Molecular records can retain repeat-unit SMILES with connection wildcards and source metadata. A structure-only file supplies no invented property label.

## Freeze partitions before training

Choose **Freeze** on a validated dataset. Freezing makes immutable train/development/final partitions using identity, scaffold or document grouping. At least three independent groups are required for held-out partitions. Related examples stay together; duplicate rows do not manufacture independent groups.

Training uses training/development inputs. Final held-out labels are reserved for independent evaluation. If there are too few groups, add genuinely independent data rather than copying rows or weakening grouping.

Notebook-derived datasets use current authorized page revisions and respect training opt-outs. Source-derived computational datasets import retained original bytes, verify checksums and keep property, unit, method, conditions and lineage. Generated labels cannot masquerade as published computed source data. These additional creation paths are available through authorized agent tools and API workflows; see [Learning workspace operations](../operations/learning-workspace.md).

## Download or register a model

Open **Models → Starting models** and select **Download** on a compatible catalog entry. A download is a job with pinned repository revision, checksummed files and license metadata. Wait until the model is ready. A catalog entry is not evidence of a trained model.

Expand **Register a local model** for an existing compatible local safetensors directory. Choose its backend, actual local path and license information, then **Register model**. Registration does not fetch missing weights or make arbitrary model code safe; remote model code is disabled by the training runtime.

**Your models** distinguishes saved assets and trained candidates. Use **Preview** for ready assistant models. Molecular property models run prediction jobs instead of a chat preview.

## Queue a bounded run

1. Select **New run** and choose **Fine-tune an assistant**, **Train a property model**, **Predict properties** or **Compare models**. **More training options** exposes additional supported tracks.
2. Select a compatible **Frozen dataset**.
3. Choose a compatible ready **Base or trained model**. A new Chemprop fit creates its own property model.
4. Set **Maximum steps** or **Maximum epochs** and **Time limit - seconds**. Use a small trial before a longer run.
5. Under **Advanced settings**, inspect execution target/device, batch size, sequence length, adapter rank, seed, checkpoint cadence or track-specific parameters.
6. Select **Check readiness**. Read compatibility, data-rights, held-out, runtime/device and disk findings plus **Resolved parameters**.
7. Select **Queue run** only after checks pass. Changing configuration invalidates the previous check, and creation checks admission again.

For a source-backed property dataset, property/unit/method context is carried into the form and stays tied to that source. A property fit uses one coherent context. Classification needs 0/1 labels and both classes in training. Chemprop's displayed fixed learning-rate schedule is distinct from assistant adapter training parameters.

## Monitor, stop and resume

The default **Runs** tab shows persisted state, recorded progress, elapsed time, loss/validation observations, metrics and downloadable files. Select a run to inspect its detail and error. A loss chart appears only when there are sufficient real observations.

**Stop run** requests process-group cancellation. **Resume** requeues a resumable blocked/failed/cancelled/interrupted/timed-out job. Resolve the reported prerequisite first. Transformers can resume optimizer checkpoints; MLX restarts from adapter weights as a warm start with fresh optimizer state. Neither case guarantees a bit-identical continuation.

The original total wall-time budget and campaign accounting survive attempts. Backend or remote worker loss does not reset a job's allowance. Training and simulation share heavy-work admission so competing expensive jobs do not silently overcommit the device.

Research campaigns appear above runs with linked resources, API cost, specification/ledger and **Open agent**. The saved campaign specification controls its limits; an agent cannot increase them.

## Evaluate and activate deliberately

Choose **Evaluate candidate** on a completed trainable candidate or start **Compare models**. Assistant evaluation compares base and candidate on final held-out prompts without sending either the expected answers. Recorded checks may cover exact match, JSON, citation IDs, numeric values/units and tool calls. Citation-ID membership is not proof of source entailment.

Property evaluation reports held-out MAE/RMSE or classification metrics against a training-only baseline. Structural coverage is an uncalibrated applicability flag, not a calibrated uncertainty interval or experimental performance guarantee.

Use the completed evaluation tied to the exact model under **Review activation**, then choose **Approve as my active model** as the human owner. Explicitly selecting a candidate in a private Agent run previews it without changing the active binding. The agent cannot approve its own activation.

For the reviewed workspace registry, use **More → Model registry** and its release/evaluation/promotion actions. See [Model operations](../operations/model-ops.md). A private candidate's evaluation does not bypass registry compatibility or promotion gates.

## Interpret results within their scope

Keep synthetic, extracted, externally computed, simulated and measured records distinct. Finishing a fine-tune proves that a particular run finished; it does not prove a useful chemistry model. Molecular scoring objectives such as QED, logP or molecular weight do not establish biological activity, chemical safety, fabric hand or material performance.
