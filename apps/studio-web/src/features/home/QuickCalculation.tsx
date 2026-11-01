import { useRef, useState, type FormEvent } from "react";
import { graphql, useLazyLoadQuery, useMutation } from "react-relay";
import { Link } from "react-router";
import { MoleculeLoader } from "../../components/motion/MoleculeLoader";
import { ChemistryArt } from "../../components/layout/ChemistryArt";
import { StudioIcon } from "../../components/layout/StudioLayout";
import { Button } from "../../components/atoms/Button";
import { TextField } from "../../components/atoms/TextField";
import { CalculationCapabilityQuery } from "../runs/operations";
import { RunResult, type RunView } from "../runs/RunResult";
import type { runsCalculationCapabilityQuery } from "../../__generated__/runsCalculationCapabilityQuery.graphql";
import type { homeQuickCalculationMutation } from "../../__generated__/homeQuickCalculationMutation.graphql";
import "../runs/calculations.css";

const QuickMutation = graphql`
  mutation homeQuickCalculationMutation($input: QuickDescribeStructureInput!) {
    runs { quickDescribeStructure(input: $input) {
      run { id taskId kind status queuedAt startedAt finishedAt error inputSummary resultSummary }
      errors { code message fieldPath }
    } }
  }
`;

export function QuickCalculation({ projects = [], onSaved }: { projects?: readonly { id: string; name: string }[]; onSaved?: () => void }) {
  const [refresh, setRefresh] = useState(0);
  const capability = useLazyLoadQuery<runsCalculationCapabilityQuery>(CalculationCapabilityQuery, {}, { fetchPolicy: "store-and-network", fetchKey: refresh }).engineCapabilities.rdkit;
  const [commit, pending] = useMutation<homeQuickCalculationMutation>(QuickMutation);
  const [smiles, setSmiles] = useState("");
  const [project, setProject] = useState("");
  const [run, setRun] = useState<RunView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);
  const requestKey = useRef<string | null>(null);
  const available = capability.status === "available";
  const change = (value: string) => { setSmiles(value); requestKey.current = null; setError(null); setRun(null); };
  function submit(event: FormEvent) {
    event.preventDefault();
    if (busy.current || pending || !available || !smiles.trim()) return;
    busy.current = true;
    requestKey.current ??= crypto.randomUUID();
    setError(null);
    setRun(null);
    commit({ variables: { input: { smiles: smiles.trim(), projectId: project || null, idempotencyKey: requestKey.current } },
      onCompleted: (response) => {
        busy.current = false;
        const result = response.runs.quickDescribeStructure;
        if (result.run) { setRun(result.run); requestKey.current = null; onSaved?.(); }
        if (result.errors.length) { setError(result.errors.map((finding) => finding.message).join(" ")); requestKey.current = null; }
        else if (!result.run) setError("The result could not be confirmed. Calculate again to check the same request.");
      },
      onError: () => { busy.current = false; setError("The connection was interrupted. Your structure is still here. Retry to check the original calculation."); },
    });
  }
  return <section className="cs-quick-calculator" aria-labelledby="quick-calculation-title">
    <div className="cs-quick-calculator__intro"><div><div className="cs-kicker"><span className={`cs-live-dot${available ? "" : " is-unavailable"}`} />{available ? "Local molecular calculator" : "Molecular calculator"}</div><h2 id="quick-calculation-title">Explore a molecule</h2><p>Get its structure and properties. Start with a SMILES string.</p></div><ChemistryArt kind="molecule" /></div>
    <form aria-label="Quick molecular calculation" onSubmit={submit} aria-busy={pending}>
      <TextField id="quick-structure" label="Molecular structure" name="smiles" value={smiles} onChange={(event) => change(event.target.value)} disabled={pending} placeholder="Paste a SMILES structure, e.g. CCO" hint="SMILES is a text representation of a molecule." required maxLength={8192} autoComplete="off" spellCheck={false} />
      <div className="cs-quick-calculator__actions"><Button type="submit" variant="primary" disabled={pending || !available || !smiles.trim()}>{pending ? "Calculating…" : "Calculate properties"}<StudioIcon name="arrow" /></Button><Button variant="ghost" disabled={pending} onClick={() => { change("CCO"); document.getElementById("quick-structure")?.focus(); }}>Try ethanol</Button></div>
      <details className="cs-save-context"><summary>Save to a project <span>Optional</span></summary><label htmlFor="quick-project">Project</label><select className="cs-select" id="quick-project" value={project} disabled={pending} onChange={(event) => { setProject(event.target.value); requestKey.current = null; setRun(null); }}><option value="">Quick calculations — organize automatically</option>{projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></details>
      {!pending && <p className="cs-save-note"><StudioIcon name="projects" />Results are saved automatically {project ? `to ${projects.find((item) => item.id === project)?.name ?? "your project"}` : "in Quick calculations"}.</p>}
      {pending && <div className="cs-calculating" role="status"><MoleculeLoader size={30} /><progress aria-label="Calculation in progress" /><span>Calculating locally and saving your result…</span></div>}
      {error && <div className="cs-action-error" role="alert"><strong>Let's try that again</strong><p>{error}</p></div>}
      {!available && <div className="cs-action-error" role="status"><strong>The local engine is unavailable</strong><p>Calculations will be available when RDKit is ready on this device.</p><Button variant="ghost" onClick={() => setRefresh((value) => value + 1)}>Check again</Button><details><summary>Engine details</summary>{capability.detail}</details></div>}
    </form>
    {run && <section className="cs-quick-result" aria-label="Calculation result"><header><div><span className="cs-kicker">Saved result</span><h3>Your molecule, explained</h3></div><Link to={`/runs/${encodeURIComponent(run.id)}`} className="cs-btn cs-btn--ghost">Open full result <StudioIcon name="arrow" /></Link></header><RunResult run={run} compact /></section>}
  </section>;
}
