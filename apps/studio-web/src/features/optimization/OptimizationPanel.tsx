import { useRef, useState } from "react";
import { useFragment, useMutation } from "react-relay";

import { Badge } from "../../components/atoms/Badge";
import { Button } from "../../components/atoms/Button";
import { TextField } from "../../components/atoms/TextField";
import { EmptyState } from "../../components/states/states";
import { CampaignCommandMutation, CreateCampaignMutation, OptimizationFragment } from "./operations";
import type { OptimizationPanel_task$key } from "../../__generated__/OptimizationPanel_task.graphql";
import type { optimizationCreateCampaignMutation } from "../../__generated__/optimizationCreateCampaignMutation.graphql";
import type { optimizationCampaignCommandMutation, OptimizationOperation } from "../../__generated__/optimizationCampaignCommandMutation.graphql";

export type CampaignManifest = {
  scientificStatus: string;
  capabilityStatus: string;
  definition: { seed: number; target: { name: string; unit: string; method: string } };
  state: {
    engine_version: string;
    adapter_version: string;
    request_index: number;
    experiments: ReadonlyArray<{
      id: string;
      parameters: Record<string, string>;
      status: string;
      outcome: string | null;
      reason: string | null;
      measurement_id: string | null;
    }>;
    history: ReadonlyArray<{ status: string; recommender: string; acquisition: string | null; rejected: Record<string, number> }>;
  };
};

export function CampaignSummary({ manifest }: { manifest: CampaignManifest }) {
  const { state } = manifest;
  const last = state.history.at(-1);
  return <>
    <p><Badge tone="neutral">{manifest.capabilityStatus}</Badge>{" "}<Badge tone="warning">{manifest.scientificStatus}</Badge></p>
    <p>BayBE {state.engine_version} · {state.adapter_version} · seed {manifest.definition.seed} · request {state.request_index}</p>
    {last && <p role="status">{last.status} · {last.recommender}{last.acquisition ? ` · ${last.acquisition}` : " · no acquisition or uncertainty reported"} · rejected {JSON.stringify(last.rejected)}</p>}
    <p>Target: {manifest.definition.target.name} ({manifest.definition.target.unit}), method {manifest.definition.target.method}</p>
  </>;
}

export function OptimizationPanel({ taskRef }: { taskRef: OptimizationPanel_task$key }) {
  const task = useFragment(OptimizationFragment, taskRef);
  const [definition, setDefinition] = useState("");
  const [batch, setBatch] = useState("1");
  const [message, setMessage] = useState("");
  const [measurement, setMeasurement] = useState("");
  const [snapshot, setSnapshot] = useState("");
  const [reason, setReason] = useState("");
  const [create, creating] = useMutation<optimizationCreateCampaignMutation>(CreateCampaignMutation);
  const [command, updating] = useMutation<optimizationCampaignCommandMutation>(CampaignCommandMutation);
  const busy = creating || updating;
  const creation = useRef({ payload: "", key: "" });
  const request = useRef({ payload: "", key: "" });

  function retryKey(ref: { current: { payload: string; key: string } }, payload: unknown) {
    const serialized = JSON.stringify(payload);
    if (ref.current.payload !== serialized) {
      ref.current = { payload: serialized, key: crypto.randomUUID() };
    }
    return ref.current.key;
  }

  function submitDefinition() {
    let parsed: unknown;
    try {
      parsed = JSON.parse(definition);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
    } catch { setMessage("Provide a campaign definition JSON object. No parameters or results are invented."); return; }
    setMessage("");
    create({ variables: { input: { taskId: task.id, definition: parsed, idempotencyKey: retryKey(creation, parsed) } },
      onCompleted: (data) => setMessage(data.optimization.create.errors.map(e => `${e.code}: ${e.message}`).join("; ") || "Campaign definition frozen. Suggestions are not experiment approvals."),
      onError: () => setMessage("Request outcome unknown. Retry unchanged inputs with the same key, or reload to inspect the saved campaign."),
    });
  }

  function act(campaignId: string, revision: number, operation: OptimizationOperation, experimentId?: string) {
    const size = Number(batch);
    if (!Number.isInteger(size) || size < 1 || size > 16) { setMessage("Batch size must be 1–16."); return; }
    if (operation === "observed" && (!measurement || !snapshot)) { setMessage("A reviewed measurement and frozen snapshot Relay ID are required; pending values are not zero."); return; }
    if ((operation === "cancelled" || operation === "failed") && !reason.trim()) { setMessage("Record a cancellation/failure reason."); return; }
    setMessage("");
    const input = { campaignId, expectedRevision: revision, operation, batchSize: size,
      experimentId: experimentId ?? null,
      measurementId: operation === "observed" ? measurement : null,
      snapshotId: operation === "observed" ? snapshot : null,
      reason: operation === "cancelled" || operation === "failed" ? reason : null,
    };
    command({ variables: { input: { ...input, idempotencyKey: retryKey(request, input) } }, onCompleted: (data) => setMessage(data.optimization.command.errors.map(e => `${e.code}: ${e.message}`).join("; ") || "Campaign state persisted. No lab action or approval was issued."),
    onError: () => setMessage("Request outcome unknown. Retry unchanged inputs with the same key, or reload to inspect the saved campaign."), });
  }

  return <div>
    <p>Local experiment planning only. Scientific reviewer + model-manager permissions are required to freeze a definition. Recommendations require the optimization profile and network-denied worker.</p>
    <p>No lab execution, experiment approval, superiority claim, or artificial zero outcomes. Unsupported hybrid, cardinality, and batch-wide constraints are rejected.</p>
    <label>Campaign definition JSON<textarea aria-label="Campaign definition JSON" rows={10} value={definition} onChange={e => setDefinition(e.target.value)} /></label>
    <Button onClick={submitDefinition} disabled={busy || !definition.trim()}>Freeze campaign definition</Button>
    <TextField label="Recommendation batch (1–16)" inputMode="numeric" value={batch} onChange={e => setBatch(e.target.value)} />
    <TextField label="Reviewed measurement Relay ID" value={measurement} onChange={e => setMeasurement(e.target.value)} />
    <TextField label="Frozen property dataset Relay ID" value={snapshot} onChange={e => setSnapshot(e.target.value)} />
    <TextField label="Cancellation/failure reason" value={reason} maxLength={1000} onChange={e => setReason(e.target.value)} />
    <p>Observation identity must already be recorded in the reviewed measurement’s actual optimization conditions (campaignId, experimentId, parameters, context). Corrections or changed contracts require a new campaign.</p>
    {message && <p role="status">{message}</p>}
    {task.optimizationCampaigns.length === 0 && <EmptyState title="No frozen campaigns. Define the approved parameter space, target/method, constraints, context and seed." />}
    {task.optimizationCampaigns.map(c => {
      const manifest = c.manifest as CampaignManifest;
      return <section key={c.id} aria-label={`campaign ${c.id}`}>
        <h4>Campaign {c.id} · revision {c.revision}</h4>
        <CampaignSummary manifest={manifest} />
        <Button disabled={busy} onClick={() => act(c.id, c.revision, "recommend")}>Request suggestions</Button>
        <details><summary>Frozen definition</summary><pre>{JSON.stringify(manifest.definition, null, 2)}</pre></details>
        <div
          className="cs-table-wrap"
          role="region"
          aria-label="reserved experiment identities"
          tabIndex={0}
        >
          <table className="cs-table"><caption>Reserved experiment identities (cancelled/failed remain reserved)</caption>
            <thead><tr><th scope="col" className="cs-table__identity">Identity / parameters</th><th scope="col">State</th><th scope="col">Observation</th><th scope="col">Lifecycle</th></tr></thead>
            <tbody>{manifest.state.experiments.map(e => <tr key={e.id}>
              <td className="cs-table__identity">{e.id}<pre>{JSON.stringify(e.parameters)}</pre></td><td>{e.status}{e.reason && <p>{e.reason}</p>}</td>
              <td>{e.outcome === null ? "No observation" : `${e.outcome} ${manifest.definition.target.unit}`}<p>{e.measurement_id ?? ""}</p></td>
              <td>{e.status === "pending" && <>
                <Button disabled={busy} onClick={() => act(c.id, c.revision, "observed", e.id)}>Link reviewed observation</Button>
                <Button disabled={busy} onClick={() => act(c.id, c.revision, "cancelled", e.id)}>Cancel suggestion</Button>
                <Button disabled={busy} onClick={() => act(c.id, c.revision, "failed", e.id)}>Record failure</Button>
              </>}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </section>;
    })}
  </div>;
}
