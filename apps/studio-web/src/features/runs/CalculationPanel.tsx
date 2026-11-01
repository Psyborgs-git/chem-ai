import { Suspense, useRef, useState, type FormEvent } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";
import { Link } from "react-router";

import { Badge } from "../../components/atoms/Badge";
import { Button } from "../../components/atoms/Button";
import { TextField } from "../../components/atoms/TextField";
import { InlineFinding } from "../../components/molecules/InlineFinding";
import { LoadingState } from "../../components/states/states";
import { CalculationCapabilityQuery, DescribeStructureMutation } from "./operations";
import { RunResult, type RunView } from "./RunResult";
import { RunsPanel } from "./RunsPanel";

import type { runsCalculationCapabilityQuery } from "../../__generated__/runsCalculationCapabilityQuery.graphql";
import type { runsDescribeStructureMutation } from "../../__generated__/runsDescribeStructureMutation.graphql";
import "./calculations.css";

type Capability = { status: string; detail: string };

/** The key survives an uncertain network result. Retrying the same
 * input retrieves the original run rather than launching it twice. */
export function CalculationForm({
  taskId,
  capability,
  readOnlyReason,
  onRun,
}: {
  taskId: string;
  capability: Capability;
  readOnlyReason?: string;
  onRun?: (run: RunView) => void;
}) {
  const [smiles, setSmiles] = useState("");
  const [commit, mutationPending] = useMutation<runsDescribeStructureMutation>(DescribeStructureMutation);
  const [pending, setPending] = useState(false);
  const pendingRef = useRef(false);
  const requestKey = useRef<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<RunView | null>(null);
  const busy = pending || mutationPending;
  const available = capability.status === "available";

  function changeInput(value: string) {
    setSmiles(value);
    setError(null);
    requestKey.current = null;
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pendingRef.current || mutationPending || !available || readOnlyReason) return;
    if (!smiles.trim()) {
      setError("Enter a molecular structure in SMILES format.");
      return;
    }
    if (smiles.trim().length > 8192) {
      setError("Use a SMILES input of 8,192 characters or fewer.");
      return;
    }
    pendingRef.current = true;
    setPending(true);
    setError(null);
    setRun(null);
    requestKey.current ??= crypto.randomUUID();
    commit({
      variables: { input: { taskId, smiles: smiles.trim(), idempotencyKey: requestKey.current } },
      onCompleted: (response) => {
        pendingRef.current = false;
        setPending(false);
        const result = response.runs.describeStructure;
        if (result.run) {
          setRun(result.run);
          onRun?.(result.run);
          // A known server response resolves uncertainty; the next
          // deliberate submission is a separate calculation.
          requestKey.current = null;
        }
        if (result.errors.length) {
          setError(result.errors.map((finding) => `${finding.code}: ${finding.message}`).join("; "));
          requestKey.current = null;
        } else if (!result.run) {
          setError("The server did not confirm a saved run. Retry to check the original request.");
        }
      },
      onError: (failure) => {
        pendingRef.current = false;
        setPending(false);
        setError(`The calculation response could not be confirmed. Retry checks the same request. ${failure.message}`);
      },
    });
  }

  return (
    <div>
      <div className="cs-calculation-layout">
        <form className="cs-calculation-form" onSubmit={submit} aria-label="Molecular calculation" aria-busy={busy}>
          <h3>Describe a molecule</h3>
          <p className="cs-field__hint">Calculate structural properties locally with RDKit. Enter a SMILES structure to begin.</p>
          <TextField label="SMILES structure" name="smiles" value={smiles} onChange={(event) => changeInput(event.target.value)} placeholder="For example: CCO" hint="SMILES is a text representation of a molecular structure." maxLength={8192} autoComplete="off" spellCheck={false} disabled={busy || !!readOnlyReason} required />
          {readOnlyReason && <InlineFinding severity="warning" message={readOnlyReason} />}
          {!available && <InlineFinding severity="warning" message={`RDKit is ${capability.status}. ${capability.detail}`} />}
          {error && <InlineFinding severity="error" message={error} />}
          <div className="cs-calculation-actions">
            <Button type="submit" variant="primary" disabled={busy || !available || !!readOnlyReason || !smiles.trim()}>{busy ? "Calculating locally…" : "Calculate properties"}</Button>
            <Button type="button" variant="ghost" disabled={busy || !!readOnlyReason} onClick={() => changeInput("CCO")}>Use ethanol example</Button>
          </div>
          {busy && <p role="status" aria-live="polite">RDKit is calculating the molecular descriptors. The result will be saved to this task.</p>}
        </form>
        <aside className="cs-calculation-help" aria-label="About local calculations">
          <Badge tone={available ? "success" : "warning"}>RDKit · {capability.status}</Badge>
          <h3>Small input. Traceable results.</h3>
          <p>Get molecular formula, molecular weight, hydrogen-bond counts, polarity, and other descriptors from the supplied structure.</p>
          <p>Each run keeps its input, engine version, method, and completion time so you can revisit the result.</p>
          <p className="cs-field__hint">{capability.detail}</p>
        </aside>
      </div>
      {run && <section className="cs-calculation-latest" aria-label="Latest calculation"><div className="cs-calculation-header"><h3>Latest calculation</h3><Link className="cs-btn cs-btn--secondary" to={`/runs/${encodeURIComponent(run.id)}`}>Open saved result</Link></div><RunResult run={run} /></section>}
    </div>
  );
}

function CalculationInner({ taskId, workflowState }: { taskId: string; workflowState: string }) {
  const [capabilityRefresh, setCapabilityRefresh] = useState(0);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const data = useLazyLoadQuery<runsCalculationCapabilityQuery>(CalculationCapabilityQuery, {}, { fetchKey: capabilityRefresh, fetchPolicy: "network-only" });
  const readOnlyReason = ["closed", "cancelled"].includes(workflowState)
    ? "This task is closed to new calculations. Existing results remain available below."
    : undefined;
  return (
    <>
      <div className="cs-calculation-header"><div><h3>Local molecular calculations</h3><p className="cs-field__hint">Explore a structure and retain the computed result with your research task.</p></div><Button variant="ghost" onClick={() => setCapabilityRefresh((value) => value + 1)}>Refresh engine status</Button></div>
      <CalculationForm taskId={taskId} capability={data.engineCapabilities.rdkit} readOnlyReason={readOnlyReason} onRun={() => setHistoryRefresh((value) => value + 1)} />
      <section className="cs-calculation-history" aria-labelledby="calculation-history-heading"><h3 id="calculation-history-heading">Run history</h3><Suspense fallback={<LoadingState label="Loading run history…" />}><RunsPanel taskId={taskId} refreshKey={historyRefresh} /></Suspense></section>
    </>
  );
}

export function CalculationPanel({ taskId, workflowState }: { taskId: string; workflowState: string }) {
  return <Suspense fallback={<LoadingState label="Checking local calculation engine…" />}><CalculationInner key={taskId} taskId={taskId} workflowState={workflowState} /></Suspense>;
}
