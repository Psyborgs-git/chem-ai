import { useState } from "react";
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

import type { tasksTaskCreateMutation } from "../../__generated__/tasksTaskCreateMutation.graphql";

const MODES = [
  { value: "improve", label: "improve an existing formulation" },
  { value: "match_reference", label: "match a reference product" },
  { value: "discover", label: "discover something new" },
] as const;

/** Task creation (§11.1). Mode-required fields are collected
 * honestly: leaving them blank creates a *draft* with the missing
 * inputs recorded as unresolved — never fabricated. */
export function TaskCreateForm({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const [commit] = useMutation<tasksTaskCreateMutation>(TaskCreateMutation);
  const [title, setTitle] = useState("");
  const [mode, setMode] = useState<(typeof MODES)[number]["value"]>("improve");
  const [objective, setObjective] = useState("");
  const [targetKind, setTargetKind] = useState("unknown");
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
    setErrors([]);
    commit({
      variables: {
        input: {
          projectId,
          title,
          mode,
          objective: objective || undefined,
          targetKind: mode === "discover" ? targetKind : undefined,
          modeInputs,
        },
      },
      onCompleted: (resp) => {
        const errs = resp.taskCreate.errors;
        if (errs.length > 0) {
          setErrors(errs);
          return;
        }
        if (resp.taskCreate.task) {
          navigate(`/tasks/${encodeURIComponent(resp.taskCreate.task.id)}`);
        }
      },
      onError: (e) =>
        setErrors([{ code: "NETWORK", message: `not saved: ${e.message}` }]),
    });
  };

  return (
    <form
      aria-label="create task"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <TextField
        label="task title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        required
      />

      <div className="cs-field">
        <label htmlFor="mode" className="cs-field__label">
          research mode
        </label>
        <select
          id="mode"
          className="cs-select"
          value={mode}
          onChange={(e) => setMode(e.target.value as typeof mode)}
        >
          {MODES.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      {mode === "improve" && (
        <fieldset>
          <legend>baseline</legend>
          <FormulationRevisionPicker
            label="baseline formulation revision"
            hint="search by family name — leaving it blank keeps the input unresolved"
            statusFilter="accepted"
            onPick={(p) => setBaselineRevisionId(p.uuid)}
          />
          <TextField
            label="variation scope"
            hint="what may change (e.g. solvent system, pigment loading)"
            value={variationScope}
            onChange={(e) => setVariationScope(e.target.value)}
          />
        </fieldset>
      )}

      {mode === "match_reference" && (
        <fieldset>
          <legend>reference</legend>
          <ReferenceProductPicker
            label="reference product"
            hint="search by product name or supplier — blank stays unresolved"
            onPick={(p) => setReferenceProductId(p.uuid)}
          />
          <div className="cs-field">
            <label htmlFor="match-scope" className="cs-field__label">
              match scope
            </label>
            <select
              id="match-scope"
              className="cs-select"
              value={matchScope}
              onChange={(e) => setMatchScope(e.target.value)}
            >
              <option value="functional">functional</option>
              <option value="analytical">analytical</option>
              <option value="functional_and_analytical">
                functional and analytical
              </option>
            </select>
          </div>
        </fieldset>
      )}

      {mode === "discover" && (
        <fieldset>
          <legend>target</legend>
          <div className="cs-field">
            <label htmlFor="target-kind" className="cs-field__label">
              target kind
            </label>
            <select
              id="target-kind"
              className="cs-select"
              value={targetKind}
              onChange={(e) => setTargetKind(e.target.value)}
            >
              <option value="unknown">unknown</option>
              <option value="formulation">formulation</option>
              <option value="material">material</option>
              <option value="molecule">molecule</option>
            </select>
          </div>
          <TextField
            label="objective"
            hint="what the search should achieve; blank stays unresolved"
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
          />
        </fieldset>
      )}

      {mode !== "discover" && (
        <TextField
          label="objective (optional)"
          value={objective}
          onChange={(e) => setObjective(e.target.value)}
        />
      )}

      {errors.map((e) => (
        <InlineFinding key={`${e.code}:${e.message}`} severity="error" message={e.message} />
      ))}

      <Button variant="primary" type="submit">
        Create task (saves a draft)
      </Button>
    </form>
  );
}
