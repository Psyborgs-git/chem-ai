import { useRef, useState } from "react";
import { useMutation } from "react-relay";
import { useNavigate } from "react-router";

import { Button } from "../../components/atoms/Button";
import { TextField } from "../../components/atoms/TextField";
import { InlineFinding } from "../../components/molecules/InlineFinding";
import {
  FormulationRevisionPicker,
  ReferenceProductPicker,
} from "../registry/pickers";
import { TaskCreateMutation } from "./operations";
import { ChemistryArt } from "../../components/layout/ChemistryArt";

import type { tasksTaskCreateMutation } from "../../__generated__/tasksTaskCreateMutation.graphql";

const MODES = [
  { value: "discover", label: "Explore", description: "Investigate a new molecule, material or formulation.", art: "molecule" },
  { value: "improve", label: "Improve", description: "Build on a formulation you already know.", art: "improve" },
  { value: "match_reference", label: "Match", description: "Compare against a reference product.", art: "match" },
] as const;

/** Task creation (§11.1). Mode-required fields are collected
 * honestly: leaving them blank creates a *draft* with the missing
 * inputs recorded as unresolved — never fabricated. */
export function TaskCreateForm({ projectId }: { projectId?: string }) {
  const navigate = useNavigate();
  const [commit, pending] = useMutation<tasksTaskCreateMutation>(TaskCreateMutation);
  const submitting = useRef(false);
  const [title, setTitle] = useState("");
  const [mode, setMode] = useState<(typeof MODES)[number]["value"]>("discover");
  const [objective, setObjective] = useState("");
  const [targetKind, setTargetKind] = useState("molecule");
  // mode inputs
  const [baselineRevisionId, setBaselineRevisionId] = useState("");
  const [variationScope, setVariationScope] = useState("");
  const [referenceProductId, setReferenceProductId] = useState("");
  const [matchScope, setMatchScope] = useState("functional");
  const [errors, setErrors] = useState<
    readonly { code: string; message: string }[]
  >([]);

  const modeInputs = (() => {
    if (mode === "improve") {
      return {
        ...(baselineRevisionId ? { baselineRevisionId } : {}),
        ...(variationScope ? { variationScope } : {}),
      };
    }
    if (mode === "match_reference") {
      return {
        ...(referenceProductId ? { referenceProductId } : {}),
        matchScope,
      };
    }
    return {};
  })();

  const submit = () => {
    if (submitting.current || pending || !title.trim()) return;
    submitting.current = true;
    setErrors([]);
    commit({
      variables: {
        input: {
          projectId,
          title,
          mode,
          objective: objective.trim() ? objective : title.trim(),
          targetKind: mode === "discover" ? targetKind : undefined,
          modeInputs,
        },
      },
      onCompleted: (resp) => {
        submitting.current = false;
        const errs = resp.taskCreate.errors;
        if (errs.length > 0) {
          setErrors(errs);
          return;
        }
        if (resp.taskCreate.task) {
          navigate(`/tasks/${encodeURIComponent(resp.taskCreate.task.id)}`);
        }
      },
      onError: (e) => {
        submitting.current = false;
        setErrors([{ code: "NETWORK", message: `not saved: ${e.message}` }]);
      },
    });
  };

  return (
    <form aria-label="create task" aria-busy={pending} className="cs-task-create cs-intent-form" onSubmit={(event) => { event.preventDefault(); submit(); }}>
      <TextField label="task title" hint="What would you like to investigate? This becomes your starting research goal." value={title} onChange={(event) => setTitle(event.target.value)} required autoFocus disabled={pending} />
      <fieldset className="cs-intent-picker" disabled={pending}><legend>How would you like to begin?</legend><div className="cs-intent-options">
        {MODES.map((item) => <label key={item.value} className={`cs-intent-choice${mode === item.value ? " is-selected" : ""}`}>
          <input type="radio" name="research-mode" aria-label={item.label} value={item.value} checked={mode === item.value} onChange={() => setMode(item.value)} />
          <ChemistryArt kind={item.art} className="cs-intent-art" /><strong>{item.label}</strong><span>{item.description}</span>
        </label>)}
      </div></fieldset>
      {mode === "discover" && <label className="cs-field"><span className="cs-field__label">What are you exploring?</span><select className="cs-select" value={targetKind} onChange={(event) => setTargetKind(event.target.value)} disabled={pending}>
        <option value="molecule">A molecule</option><option value="material">A material</option><option value="formulation">A formulation</option><option value="unknown">Not sure yet</option>
      </select></label>}
      {mode === "improve" && <fieldset className="cs-create-context"><legend>Start from an existing formulation</legend>
        <FormulationRevisionPicker label="baseline formulation revision" hint="Choose a reviewed baseline, or leave this unresolved in your draft." statusFilter="accepted" selectedId={baselineRevisionId} onClear={() => setBaselineRevisionId("")} onPick={(picked) => setBaselineRevisionId(picked.uuid)} />
        <TextField label="variation scope" hint="What may change, such as the solvent system or ingredient loading?" value={variationScope} onChange={(event) => setVariationScope(event.target.value)} disabled={pending} />
      </fieldset>}
      {mode === "match_reference" && <fieldset className="cs-create-context"><legend>Choose the reference</legend>
        <ReferenceProductPicker label="reference product" hint="Search by product or supplier. Missing information stays unresolved." selectedId={referenceProductId} onClear={() => setReferenceProductId("")} onPick={(picked) => setReferenceProductId(picked.uuid)} />
        <p className="cs-field__hint">Starts with a performance comparison. Change the comparison scope in Details.</p>
      </fieldset>}
      <details className="cs-create-details"><summary>Details <span>Optional</span></summary>
        <TextField label="Research goal (optional)" hint="Use a more detailed goal, or keep the task title as your starting point." value={objective} onChange={(event) => setObjective(event.target.value)} disabled={pending} />
        {mode === "match_reference" && <label className="cs-field"><span className="cs-field__label">What should match?</span><select className="cs-select" value={matchScope} onChange={(event) => setMatchScope(event.target.value)} disabled={pending}><option value="functional">Performance</option><option value="analytical">Analytical profile</option><option value="functional_and_analytical">Performance and analytical profile</option></select></label>}
      </details>
      {errors.map((error) => <InlineFinding key={`${error.code}:${error.message}`} severity="error" message={error.message} />)}
      <div className="cs-create-footer"><p>Your task starts as a draft. Success criteria and review decisions stay in your control.</p><Button variant="primary" type="submit" disabled={pending || !title.trim()}>{pending ? "Creating task…" : "Create task"}</Button></div>
    </form>
  );
}
