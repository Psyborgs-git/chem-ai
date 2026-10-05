import { useState } from "react";
import { useMutation } from "react-relay";

import { Button } from "../../components/atoms/Button";
import { MetricTargetEditor } from "../../components/molecules/MetricTargetEditor";
import { SaveStatus } from "../../components/states/states";
import { ContractDraftMutation } from "./operations";
import { useSaveState } from "./useSaveState";

import type { tasksContractDraftMutation } from "../../__generated__/tasksContractDraftMutation.graphql";

type Metric = { name: string; operator: "<=" | ">=" | "target"; value: string; unit: string };

const UNITS = ["Pa_s", "MPa", "degC", "percent", "mass_fraction"] as const;

/** Success-contract editor (§11.1): edits build a draft payload;
 * save goes through the mutation and reports honestly — a failed
 * save shows 'unsaved', never a durable-save claim (§22.4). */
export function ContractEditor({
  taskId,
  workflowState,
}: {
  taskId: string;
  workflowState: string;
}) {
  const readOnly = workflowState === "closed" || workflowState === "cancelled";
  const [metrics, setMetrics] = useState<Metric[]>([
    { name: "viscosity", operator: ">=", value: "", unit: "Pa_s" },
  ]);
  const [commit] = useMutation<tasksContractDraftMutation>(ContractDraftMutation);
  const save = useSaveState();

  const update = (i: number, v: { value?: string; unit?: string }) => {
    save.markDirty();
    setMetrics((ms) => ms.map((m, j) => (j === i ? { ...m, ...v } : m)));
  };

  const saveDraft = () =>
    save.attemptSave(
      () =>
        new Promise<boolean>((resolve) => {
          commit({
            variables: {
              input: {
                taskId,
                payload: {
                  requiredMetrics: metrics.map((m) => ({
                    name: m.name,
                    operator: m.operator,
                    target: {
                      value: m.value,
                      unit: m.unit,
                    },
                  })),
                },
              },
            },
            onCompleted: (resp) =>
              resolve(resp.contractDraftCreate.errors.length === 0),
            onError: () => resolve(false),
          });
        }),
    );

  return (
    <div aria-label="success contract editor">
      {readOnly ? (
        <SaveStatus state="read_only_revision" />
      ) : (
        <SaveStatus state={save.state} />
      )}
      {metrics.map((m, i) => (
        <MetricTargetEditor
          key={`${m.name}-${i}`}
          metric={m.name}
          operator={m.operator}
          value={m.value}
          unit={m.unit}
          units={UNITS}
          onChange={(v) => update(i, v)}
        />
      ))}
      <Button
        variant="secondary"
        disabled={readOnly}
        onClick={() =>
          setMetrics((ms) => [
            ...ms,
            { name: `metric-${ms.length + 1}`, operator: ">=", value: "", unit: "Pa_s" },
          ])
        }
      >
        add metric
      </Button>
      <Button variant="primary" disabled={readOnly} onClick={() => void saveDraft()}>
        Save contract draft
      </Button>
      {save.lastError && (
        <p role="alert" className="cs-field__error">
          {save.lastError}
        </p>
      )}
    </div>
  );
}
