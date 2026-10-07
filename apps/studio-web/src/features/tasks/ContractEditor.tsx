import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../components/atoms/Badge";
import { Button } from "../../components/atoms/Button";
import { Checkbox } from "../../components/atoms/Checkbox";
import { TextField } from "../../components/atoms/TextField";
import { UnitSelect } from "../../components/atoms/UnitSelect";
import { LoadingState, SaveStatus } from "../../components/states/states";

import {
  AGGREGATIONS,
  CONTRACT_OPERATORS,
  CONTRACT_UNITS,
  EVIDENCE_CLASSES,
  emptyForm,
  emptyMetric,
  formFromPayload,
  payloadFromForm,
  pendingForm,
} from "./contractForm";
import type { ContractForm, MetricForm } from "./contractForm";
import {
  ContractDraftMutation,
  ContractFreezeMutation,
  ContractRevisionsQuery,
} from "./operations";
import { useSaveState } from "./useSaveState";

import type { tasksContractDraftMutation } from "../../__generated__/tasksContractDraftMutation.graphql";
import type { tasksContractFreezeMutation } from "../../__generated__/tasksContractFreezeMutation.graphql";
import type { tasksContractRevisionsQuery } from "../../__generated__/tasksContractRevisionsQuery.graphql";

type RevisionNode = {
  id: string;
  revision: number;
  status: string;
  contentHash: string;
  createdAt: string;
  payload: unknown;
};

const isDraft = (r: RevisionNode) => r.status === "draft";
const metricCount = (p: unknown): number => {
  if (typeof p !== "object" || p === null) return 0;
  const rec = p as Record<string, unknown>;
  const m = Array.isArray(rec.metrics) ? rec.metrics : rec.requiredMetrics;
  return Array.isArray(m) ? m.length : 0;
};

/** Success-contract editor (§11.1): hydrates the current draft or the
 * frozen contract, edits the canonical `metrics`/`hard_constraints`/
 * `unknowns` payload, and saves through the mutation. A failed save
 * reports 'unsaved' and keeps the input — never a durable-save claim
 * (§22.4). Unsaved edits survive section switches via a per-task form
 * store, and the browser warns before unload while dirty. */
export function ContractEditor({
  taskId,
  workflowState,
}: {
  taskId: string;
  workflowState: string;
}) {
  return (
    <Suspense fallback={<LoadingState label="loading contract…" />}>
      <ContractEditorInner taskId={taskId} workflowState={workflowState} />
    </Suspense>
  );
}

function ContractEditorInner({
  taskId,
  workflowState,
}: {
  taskId: string;
  workflowState: string;
}) {
  const [fetchKey, setFetchKey] = useState(0);
  // fetchKey + network-only forces a real refetch after save/freeze —
  // a remount alone replays the cached query result (CS-1201).
  const data = useLazyLoadQuery<tasksContractRevisionsQuery>(
    ContractRevisionsQuery,
    { taskId },
    { fetchKey, fetchPolicy: "network-only" },
  );

  const revisions = useMemo(
    () =>
      data.taskContractRevisions.edges
        .map((e) => e.node as RevisionNode)
        .sort((a, b) => b.revision - a.revision),
    [data],
  );
  const latest = revisions[0] ?? null;
  const latestDraft = revisions.find(isDraft) ?? null;
  const current = revisions.find((r) => r.status === "frozen") ?? null;
  const locked =
    workflowState === "closed" || workflowState === "cancelled";

  const [viewingId, setViewingId] = useState<string | null>(null);
  const [form, setForm] = useState<ContractForm | null>(null);
  const [hydratedFrom, setHydratedFrom] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  // true once the user actually edits — a freshly hydrated form is not
  // 'unsaved input' and must not arm the pending-store or unload warning
  const touched = useRef(false);
  const save = useSaveState();
  const [commitDraft, saving] =
    useMutation<tasksContractDraftMutation>(ContractDraftMutation);
  const [commitFreeze, freezing] =
    useMutation<tasksContractFreezeMutation>(ContractFreezeMutation);
  const pending = saving || freezing;

  // hydrate when the head revision changes: unsaved edits for this
  // task win over the server state; otherwise the latest draft is
  // editable, a frozen contract opens read-only, and nothing starts
  // blank-fabricated. Re-renders that carry the same head revision
  // (e.g. the mutation's own node write) must not clobber edits.
  const headId = latestDraft?.id ?? latest?.id ?? null;
  useEffect(() => {
    const pendingState = pendingForm.get(taskId);
    if (pendingState) {
      setForm(pendingState);
      setHydratedFrom("unsaved");
      touched.current = true;
      save.markDirty();
      return;
    }
    touched.current = false;
    if (latestDraft) {
      setForm(formFromPayload(latestDraft.payload));
      setHydratedFrom(latestDraft.id);
      // the stored draft IS persisted — 'saved' is the honest state
      // (and the freeze gate works on the stored revision)
      save.markSaved();
    } else if (latest) {
      setForm(formFromPayload(latest.payload));
      setHydratedFrom(latest.id);
      save.markSaved();
    } else {
      setForm(emptyForm());
      setHydratedFrom(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId, headId]);

  // keep the unsaved store in step while dirty so unmounts (section
  // switches, route changes) never drop input silently (§22.4)
  useEffect(() => {
    if (save.state === "unsaved" && form && touched.current)
      pendingForm.set(taskId, form);
    if (save.state === "saved") {
      pendingForm.clear(taskId);
      touched.current = false;
    }
  }, [taskId, form, save.state]);

  if (!form) return <LoadingState label="loading contract…" />;

  const viewing =
    viewingId !== null ? revisions.find((r) => r.id === viewingId) : null;
  const viewingHistorical = viewing != null;
  const editingReadonly = locked || viewingHistorical;

  const update = (fn: (f: ContractForm) => ContractForm) => {
    touched.current = true;
    save.markDirty();
    setForm((f) => (f ? fn(f) : f));
  };
  const updateMetric = (key: string, patch: Partial<MetricForm>) =>
    update((f) => ({
      ...f,
      metrics: f.metrics.map((m) =>
        m.key === key ? { ...m, ...patch } : m,
      ),
    }));

  const describeErrors = (errs: readonly { code: string; message: string }[]) =>
    errs.map((e) => `${e.code}: ${e.message}`).join("; ");

  const saveDraft = () =>
    save.attemptSave(
      () =>
        new Promise<boolean>((resolve) => {
          commitDraft({
            variables: {
              input: { taskId, payload: payloadFromForm(form) },
            },
            onCompleted: (resp) => {
              const errs = resp.contractDraftCreate.errors;
              if (errs.length === 0) {
                // clear the unsaved-store synchronously — a refetch
                // that lands before the 'saved' effect must not
                // restore the just-saved form as 'unsaved edits'
                pendingForm.clear(taskId);
                touched.current = false;
                setHydratedFrom(resp.contractDraftCreate.contractRevision?.id ?? null);
                setFetchKey((k) => k + 1);
                resolve(true);
              } else if (
                errs.some((e) => e.code.includes("CONFLICT"))
              ) {
                save.markConflict(describeErrors(errs));
                resolve(false);
              } else {
                // validation errors stay visible with their field
                // paths; input is retained for correction (§22.4)
                setServerError(describeErrors(errs));
                resolve(false);
              }
            },
            onError: () => resolve(false),
          });
        }),
    );

  const freeze = () => {
    const target = latestDraft;
    if (!target) return;
    commitFreeze({
      variables: { input: { revisionId: target.id } },
      onCompleted: (resp) => {
        const errs = resp.contractFreeze.errors;
        if (errs.length === 0) {
          pendingForm.clear(taskId);
          save.markSaved();
          setFetchKey((k) => k + 1);
        } else if (errs.some((e) => e.code.includes("CONFLICT"))) {
          save.markConflict(describeErrors(errs));
        } else {
          // a refused freeze keeps the draft editable — the typed
          // error explains what the gate still needs
          save.markDirty();
          setServerError(describeErrors(errs));
        }
      },
      onError: (e) => {
        save.markDirty();
        setServerError(`freeze failed — not persisted (${e.message})`);
      },
    });
  };

  return (
    <div aria-label="success contract editor" className="cs-contract">
      <header className="cs-contract__head">
        <RevisionIdentity latest={latest} current={current} draft={latestDraft} />
        {form.legacy && (
          <p role="note" className="cs-field__hint">
            this draft was written by an older editor — saving converts it to the
            canonical contract schema; the stored revision is never rewritten.
          </p>
        )}
        {editingReadonly ? (
          <SaveStatus state="read_only_revision" />
        ) : (
          <SaveStatus state={save.state} />
        )}
      </header>

      {viewingHistorical && (
        <p role="note">
          viewing revision {viewing.revision} ({viewing.status}) —{" "}
          <Button
            variant="secondary"
            onClick={() => setViewingId(null)}
          >
            back to current
          </Button>
        </p>
      )}

      {editingReadonly ? (
        <ReadOnlyForm form={viewingHistorical ? formFromPayload(viewing.payload) : form} />
      ) : (
        <EditForm
          form={form}
          updateMetric={updateMetric}
          update={update}
          disabled={pending}
        />
      )}

      <div className="cs-contract__actions">
        {!editingReadonly && (
          <>
            <Button
              variant="primary"
              disabled={pending}
              onClick={() => void saveDraft()}
            >
              save draft
            </Button>
            <Button
              variant="secondary"
              disabled={pending || !latestDraft || save.state === "unsaved"}
              title={
                !latestDraft
                  ? "save a draft first"
                  : save.state === "unsaved"
                    ? "unsaved changes — save before freezing"
                    : "freeze the saved draft for evaluation"
              }
              onClick={freeze}
            >
              freeze contract
            </Button>
            {current && (
              <Button
                variant="secondary"
                onClick={() => setViewingId(current.id)}
              >
                view frozen revision {current.revision}
              </Button>
            )}
          </>
        )}
        {hydratedFrom === "unsaved" && (
          <Badge tone="warning">restored unsaved edits</Badge>
        )}
      </div>
      {save.lastError && (
        <p role="alert" className="cs-field__error">
          {save.lastError}
        </p>
      )}
      {serverError && (
        <p role="alert" className="cs-field__error">
          {serverError}
        </p>
      )}

      <RevisionHistory
        revisions={revisions}
        onView={(id) => setViewingId(id)}
      />
    </div>
  );
}

function RevisionIdentity({
  latest,
  current,
  draft,
}: {
  latest: RevisionNode | null;
  current: RevisionNode | null;
  draft: RevisionNode | null;
}) {
  if (!latest) {
    return <p>no contract yet — draft the success criteria below.</p>;
  }
  return (
    <p className="cs-contract__identity">
      {draft ? (
        <>
          draft revision {draft.revision}{" "}
          <Badge tone="info">draft</Badge>{" "}
        </>
      ) : (
        <>
          revision {latest.revision}{" "}
          <Badge tone={latest.status === "frozen" ? "success" : "neutral"}>
            {latest.status}
          </Badge>{" "}
        </>
      )}
      {current && (
        <>
          · current frozen: rev {current.revision}{" "}
        </>
      )}
      <span title={latest.contentHash}>
        · hash {latest.contentHash.slice(0, 12)}
      </span>
    </p>
  );
}

function EditForm({
  form,
  updateMetric,
  update,
  disabled,
}: {
  form: ContractForm;
  updateMetric: (key: string, patch: Partial<MetricForm>) => void;
  update: (fn: (f: ContractForm) => ContractForm) => void;
  disabled: boolean;
}) {
  const [newUnknown, setNewUnknown] = useState("");

  return (
    <div className="cs-contract__form">
      <fieldset>
        <legend className="cs-field__label">metrics</legend>
        {form.metrics.length === 0 && (
          <p className="cs-field__hint">
            no metrics declared — a draft may stay empty, but nothing can
            freeze until at least one evaluable metric exists.
          </p>
        )}
        {form.metrics.map((m) => (
          <div key={m.key} className="cs-contract__metric" role="group" aria-label="contract metric">
            <div className="cs-quantity__row">
              <TextField
                label="metric label"
                value={m.label}
                disabled={disabled}
                onChange={(e) => updateMetric(m.key, { label: e.target.value })}
              />
              <TextField
                label="metric id"
                value={m.id}
                hint="e.g. metric.viscosity"
                disabled={disabled}
                onChange={(e) => updateMetric(m.key, { id: e.target.value })}
              />
              <Checkbox
                label="required"
                checked={m.required}
                disabled={disabled}
                onChange={(e) =>
                  updateMetric(m.key, { required: e.target.checked })
                }
              />
            </div>
            <div className="cs-quantity__row">
              <div className="cs-field">
                <label className="cs-field__label" htmlFor={`${m.key}-op`}>
                  operator
                </label>
                <select
                  id={`${m.key}-op`}
                  className="cs-select"
                  value={m.operator}
                  disabled={disabled}
                  onChange={(e) =>
                    updateMetric(m.key, { operator: e.target.value })
                  }
                >
                  {CONTRACT_OPERATORS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <TextField
                label="target value(s)"
                value={m.targetValues}
                hint="one value — or low, high for 'between'"
                disabled={disabled}
                onChange={(e) =>
                  updateMetric(m.key, { targetValues: e.target.value })
                }
              />
              <UnitSelect
                label="unit"
                units={CONTRACT_UNITS}
                value={m.unit}
                disabled={disabled}
                onValueChange={(u) => updateMetric(m.key, { unit: u })}
              />
            </div>
            <div className="cs-quantity__row">
              <TextField
                label="method revision"
                value={m.methodRevisionId}
                hint="uuid of the measurement method revision, if bound"
                disabled={disabled}
                onChange={(e) =>
                  updateMetric(m.key, { methodRevisionId: e.target.value })
                }
              />
              <TextField
                label="conditions"
                value={m.conditions}
                disabled={disabled}
                onChange={(e) =>
                  updateMetric(m.key, { conditions: e.target.value })
                }
              />
              <div className="cs-field">
                <label className="cs-field__label" htmlFor={`${m.key}-agg`}>
                  aggregation
                </label>
                <select
                  id={`${m.key}-agg`}
                  className="cs-select"
                  value={m.aggregation}
                  disabled={disabled}
                  onChange={(e) =>
                    updateMetric(m.key, { aggregation: e.target.value })
                  }
                >
                  {AGGREGATIONS.map((a) => (
                    <option key={a.value} value={a.value}>
                      {a.label}
                    </option>
                  ))}
                </select>
              </div>
              <TextField
                label="independent batches (min)"
                value={m.minIndependentBatches}
                inputMode="numeric"
                disabled={disabled}
                onChange={(e) =>
                  updateMetric(m.key, {
                    minIndependentBatches: e.target.value,
                  })
                }
              />
            </div>
            <fieldset>
              <legend className="cs-field__label">required evidence</legend>
              <div className="cs-quantity__row">
                {EVIDENCE_CLASSES.map((c) => (
                  <Checkbox
                    key={c}
                    label={c}
                    checked={m.requiredEvidence.includes(c)}
                    disabled={disabled}
                    onChange={(e) =>
                      updateMetric(m.key, {
                        requiredEvidence: e.target.checked
                          ? [...m.requiredEvidence, c]
                          : m.requiredEvidence.filter((x) => x !== c),
                      })
                    }
                  />
                ))}
              </div>
            </fieldset>
            <Button
              variant="secondary"
              disabled={disabled}
              onClick={() =>
                update((f) => ({
                  ...f,
                  metrics: f.metrics.filter((x) => x.key !== m.key),
                }))
              }
            >
              remove metric
            </Button>
          </div>
        ))}
        <Button
          variant="secondary"
          disabled={disabled}
          onClick={() =>
            update((f) => ({ ...f, metrics: [...f.metrics, emptyMetric()] }))
          }
        >
          add metric
        </Button>
      </fieldset>

      <fieldset>
        <legend className="cs-field__label">hard constraints</legend>
        {form.constraints.map((c) => (
          <div key={c.key} className="cs-quantity__row">
            <TextField
              label="constraint id"
              value={c.id}
              disabled={disabled}
              onChange={(e) =>
                update((f) => ({
                  ...f,
                  constraints: f.constraints.map((x) =>
                    x.key === c.key ? { ...x, id: e.target.value } : x,
                  ),
                }))
              }
            />
            <TextField
              label="constraint"
              value={c.text}
              disabled={disabled}
              onChange={(e) =>
                update((f) => ({
                  ...f,
                  constraints: f.constraints.map((x) =>
                    x.key === c.key ? { ...x, text: e.target.value } : x,
                  ),
                }))
              }
            />
            <Button
              variant="secondary"
              disabled={disabled}
              onClick={() =>
                update((f) => ({
                  ...f,
                  constraints: f.constraints.filter((x) => x.key !== c.key),
                }))
              }
            >
              remove constraint
            </Button>
          </div>
        ))}
        <Button
          variant="secondary"
          disabled={disabled}
          onClick={() =>
            update((f) => ({
              ...f,
              constraints: [
                ...f.constraints,
                { key: `c${f.constraints.length}-${Date.now()}`, id: "", text: "" },
              ],
            }))
          }
        >
          add constraint
        </Button>
      </fieldset>

      <fieldset>
        <legend className="cs-field__label">declared unknowns</legend>
        <ul className="cs-unknowns" aria-label="declared unknowns">
          {form.unknowns.map((u) => (
            <li key={u}>
              {u}{" "}
              <Button
                variant="secondary"
                disabled={disabled}
                onClick={() =>
                  update((f) => ({
                    ...f,
                    unknowns: f.unknowns.filter((x) => x !== u),
                  }))
                }
              >
                resolve
              </Button>
            </li>
          ))}
        </ul>
        <div className="cs-quantity__row">
          <TextField
            label="new unknown"
            value={newUnknown}
            disabled={disabled}
            onChange={(e) => setNewUnknown(e.target.value)}
          />
          <Button
            variant="secondary"
            disabled={disabled || !newUnknown.trim()}
            onClick={() => {
              update((f) => ({ ...f, unknowns: [...f.unknowns, newUnknown.trim()] }));
              setNewUnknown("");
            }}
          >
            add unknown
          </Button>
        </div>
      </fieldset>
    </div>
  );
}

function ReadOnlyForm({ form }: { form: ContractForm }) {
  return (
    <div className="cs-contract__readonly">
      {form.metrics.length === 0 && (
        <p className="cs-field__hint">no evaluable metrics recorded.</p>
      )}
      {form.metrics.map((m) => (
        <div key={m.key} className="cs-contract__metric" role="group" aria-label="contract metric">
          <p>
            <strong>{m.label || m.id}</strong>{" "}
            <Badge tone="neutral">{m.id || "no id"}</Badge>{" "}
            {m.required ? <Badge tone="info">required</Badge> : null}
          </p>
          <p>
            {m.operator} {m.targetValues} {m.unit}
            {m.minIndependentBatches
              ? ` · ≥${m.minIndependentBatches} independent batches`
              : ""}
            {m.aggregation ? ` · aggregation: ${m.aggregation}` : ""}
          </p>
          <p className="cs-field__hint">
            method: {m.methodRevisionId || "unbound"} · conditions:{" "}
            {m.conditions || "none declared"} · evidence:{" "}
            {m.requiredEvidence.join(", ") || "none declared"} · value kind:{" "}
            {m.valueKind}
          </p>
        </div>
      ))}
      {form.constraints.length > 0 && (
        <ul aria-label="hard constraints">
          {form.constraints.map((c) => (
            <li key={c.key}>
              {c.id ? `${c.id}: ` : ""}
              {c.text}
            </li>
          ))}
        </ul>
      )}
      {form.unknowns.length > 0 && (
        <ul aria-label="declared unknowns">
          {form.unknowns.map((u) => (
            <li key={u}>{u}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RevisionHistory({
  revisions,
  onView,
}: {
  revisions: RevisionNode[];
  onView: (id: string) => void;
}) {
  if (revisions.length === 0) return null;
  return (
    <details className="cs-contract__history">
      <summary>revision history ({revisions.length})</summary>
      <table className="cs-table">
        <thead>
          <tr>
            <th>revision</th>
            <th>status</th>
            <th>metrics</th>
            <th>hash</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {revisions.map((r) => (
            <tr key={r.id}>
              <td>{r.revision}</td>
              <td>
                <Badge
                  tone={r.status === "frozen" ? "success" : r.status === "draft" ? "info" : "neutral"}
                >
                  {r.status}
                </Badge>
              </td>
              <td>{metricCount(r.payload)}</td>
              <td>
                <span title={r.contentHash}>{r.contentHash.slice(0, 12)}</span>
              </td>
              <td>
                <Button variant="secondary" onClick={() => onView(r.id)}>
                  view
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
