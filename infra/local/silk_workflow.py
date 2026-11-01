"""Create/continue the approved silk research campaign through Studio services.

Run with the API environment. Provider credentials remain in the app secret store.
This operator entry point queues the same durable agent run as the UI.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import select

from studio.auth.context import load_context
from studio.config.settings import get_settings
from studio.domain.agent_workspace.service import AgentWorkspaceService
from studio.domain.agent_workspace.workflows import WorkflowService
from studio.persistence.engine import make_engine, make_session_factory
from studio.persistence.models import InferenceProvider, Principal

DATA_REVISION = "cbab9483395a32dd968fbeb047808031fb0f3a13"
HF = f"https://huggingface.co/datasets/yhayashi1986/PolyOmics/resolve/{DATA_REVISION}/"
BOOTSTRAP = f"""Carry out the first stage of our approved Mulberry-silk alternatives experiment.
Use your actual tools and save results in THIS workflow's notebook. Public sources only.
Our goal is synthetic polymers/yarns approaching mulberry silk's feel, drape and lustre,
with separate practical-development and novel-chemistry candidate lanes. Never claim a
bulk property predictor or short MD trajectory establishes fabric equivalence.

1. Inspect learning_catalog. Register catalogId qwen3-4b-instruct-mlx and await its
downloadJobId with await_training_job until completion. This is the 4-bit Qwen3 4B
Instruct2507 checkpoint; preserve its pinned revision and license.
2. Fetch and retain {HF}README.md and {HF}biodegradable_candidate_polyester.csv.
The author dataset card https://huggingface.co/datasets/yhayashi1986/PolyOmics declares
CC-BY-4.0. Cite that evidence; for these two dataset files set citation.license to
cc-by-4.0 and citation.rights to {{"training":"allowed","extraction":"allowed","export":"allowed"}}.
3. Discover/fetch at least three accessible primary or open-access scientific resources
on Bombyx mori textile properties, synthetic textile polyester filaments, cross-section,
friction, drape or lustre. Useful starting resources are DOI10.2115/fiber.41.5_T211,
https://www.nature.com/articles/s43246-024-00488-2 and
https://www.mdpi.com/1996-1944/12/24/4086. Respect actual availability; do not invent full text.
4. Import the retained CSV twice with import_retained_dataset, one property density
(unit g/cm^3), one refractive_index (unit1). Each uses mapping
{{"psmiles":"smiles_1","target":"density OR refractive_index","polymerId":"UUID"}},
metadataColumns [UUID,temp,press,qm_method,forcefield,check_eq,Mn,Mw,tacticity],
filters {{"check_eq":"True"}},
conditions {{"temperatureK":300,"pressureAtm":1,"phase":"amorphous"}},
method "PolyOmics RadonPy GAFF2_mod amorphous MD, 300 K, 1 atm". These are externally
computed values from original retained bytes, never measured textile properties.
Freeze both datasets, inspect accepted/rejected counts and train/development/final groups.
5. Use read_dataset for each property dataset and read_resource for the dataset card.
Then call prepare_polymer_research_dataset with both datasetIds. It compiles roughly
400 auditable source-record extraction and actually executed app-tool teaching tasks.
Their origin remains synthetic. Freeze the resulting assistant dataset.
6. Save a cited reference-profile note with known textile mechanisms, measured versus
computed distinctions, missing benchmarks, and our next steps. Do not queue training yet.
Finish with a SHORT inventory of actual source/dataset/base-model IDs and any failures.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--provider", default="OPENAI sub")
    parser.add_argument("--workflow")
    parser.add_argument("--message-file", type=Path)
    args = parser.parse_args()
    settings = get_settings()
    factory = make_session_factory(make_engine(settings.database_url))
    with factory() as db:
        owner = db.scalar(
            select(Principal).where(Principal.login == args.owner, Principal.kind == "user")
        )
        if owner is None:
            raise SystemExit("Owner not found")
        ctx = load_context(db, owner.workspace_id, owner.id)
        agents = AgentWorkspaceService(db, ctx)
        workflows = WorkflowService(db, ctx)
        if args.workflow:
            workflow = workflows.get(args.workflow)
        else:
            provider = db.scalar(
                select(InferenceProvider).where(
                    InferenceProvider.workspace_id == owner.workspace_id,
                    InferenceProvider.name == args.provider,
                    InferenceProvider.enabled.is_(True),
                )
            )
            if provider is None:
                raise SystemExit("Configured provider not found")
            selected = next(item for item in agents.providers() if item["id"] == str(provider.id))
            model = next(item for item in selected["models"] if item["modelId"] == provider.model)
            if any(
                model.get(key) is None
                for key in ("inputPricePerMillionUsd", "outputPricePerMillionUsd")
            ):
                raise SystemExit("Configure this model's token prices in the app before a paid run")
            workflow = workflows.get(
                workflows.create(
                    {
                        "name": "Mulberry-silk alternatives",
                        "providerId": str(provider.id),
                        "trainingSeconds": 14400,
                        "simulationSeconds": 14400,
                        "paidCostUsd": 20,
                        "goal": "Synthetic polymer and yarn alternatives to mulberry silk; "
                        "prioritize feel, drape and lustre, compare practical and novel chemistry.",
                    },
                    settings,
                )["id"]
            )
        message = args.message_file.read_text() if args.message_file else BOOTSTRAP
        run = agents.create_run(
            workflow.thread_id, {"workflowId": str(workflow.id), "message": message}
        )
        result = {
            "workflowId": str(workflow.id),
            "threadId": str(workflow.thread_id),
            "notebookId": str(workflow.notebook_id),
            "runId": run["id"],
        }
        db.commit()
        path = Path(".runtime/silk-workflow-state.json")
        fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(result, handle, indent=2)
        print(json.dumps(result))


if __name__ == "__main__":
    main()
