import { Suspense, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../../components/atoms/Badge";
import { Button } from "../../../components/atoms/Button";
import { TextField } from "../../../components/atoms/TextField";
import { EmptyState, LoadingState } from "../../../components/states/states";
import {
  ActualsRecordMutation,
  BatchAddMutation,
  ContractCheckQuery,
  ExecutionCloseMutation,
  ExecutionHistoricalMutation,
  ExecutionOpenMutation,
  MeasurementAmendMutation,
  MeasurementApplicabilityMutation,
  MeasurementRecordMutation,
  MeasurementReviewMutation,
  ReplicationSummaryQuery,
  SampleAddMutation,
  TaskExecutionsQuery,
} from "./operations";
import { TaskPlansQuery } from "../plans/operations";

import type { labResultsTaskExecutionsQuery } from "../../../__generated__/labResultsTaskExecutionsQuery.graphql";
import type { labResultsReplicationSummaryQuery } from "../../../__generated__/labResultsReplicationSummaryQuery.graphql";
import type { labResultsContractCheckQuery } from "../../../__generated__/labResultsContractCheckQuery.graphql";
import type { labPlansTaskPlansQuery } from "../../../__generated__/labPlansTaskPlansQuery.graphql";
import type { labResultsMeasurementReviewMutation } from "../../../__generated__/labResultsMeasurementReviewMutation.graphql";
import type { labResultsMeasurementApplicabilityMutation } from "../../../__generated__/labResultsMeasurementApplicabilityMutation.graphql";
import type { labResultsMeasurementAmendMutation } from "../../../__generated__/labResultsMeasurementAmendMutation.graphql";
import type { labResultsMeasurementRecordMutation } from "../../../__generated__/labResultsMeasurementRecordMutation.graphql";
import type { labResultsSampleAddMutation } from "../../../__generated__/labResultsSampleAddMutation.graphql";
import type { labResultsBatchAddMutation } from "../../../__generated__/labResultsBatchAddMutation.graphql";
import type { labResultsExecutionCloseMutation } from "../../../__generated__/labResultsExecutionCloseMutation.graphql";
import type { labResultsActualsRecordMutation } from "../../../__generated__/labResultsActualsRecordMutation.graphql";
import type { labResultsExecutionOpenMutation } from "../../../__generated__/labResultsExecutionOpenMutation.graphql";
import type { labResultsExecutionHistoricalMutation } from "../../../__generated__/labResultsExecutionHistoricalMutation.graphql";

type Execution = NonNullable<
  labResultsTaskExecutionsQuery["response"]["taskExecutions"][number]
>;
type Batch = Execution["batches"][number];
type Sample = Batch["samples"][number];
type MeasurementRow = Sample["measurements"][number];
type Errs = readonly { code: string; message: string }[] | null | undefined;
type Json = Record<string, unknown>;

const MANUAL_LABEL =
  "MANUAL EXECUTION — qualified operator required; the system does not start equipment";

const STATUS_TONE: Record<
  string,
  "info" | "success" | "warning" | "danger" | "neutral"
> = {
  open: "info",
  completed: "success",
  aborted: "warning",
  accepted: "success",
  rejected: "danger",
  recorded: "neutral",
};

function showErrs(errs: Errs, setError: (m: string) => void): boolean {
  if (errs && errs.length > 0) {
    setError(errs.map((e) => `${e.code}: ${e.message}`).join("; "));
    return true;
  }
  return false;
}

function ValueLabel({ m }: { m: MeasurementRow }) {
  const v = (m.value ?? {}) as Json;
  const text =
    m.valueType === "numeric"
      ? `${String(v.value ?? "?")} ${String(v.unit ?? "")}`
      : m.valueType === "interval"
        ? `[${String(v.low ?? "?")}–${String(v.high ?? "?")}] ${String(
            v.unit ?? "",
          )}`
        : m.valueType === "missing"
          ? `missing (${String(v.reason ?? "unspecified")})`
          : `${m.valueType}: ${String(v.value ?? v.label ?? "…")}`;
  return <span data-field="measurement-value">{text}</span>;
}

function ReplicationSummary({ executionId }: { executionId: string }) {
  const data = useLazyLoadQuery<labResultsReplicationSummaryQuery>(
    ReplicationSummaryQuery,
    { executionId },
    { fetchPolicy: "network-only" },
  );
  const s = (data.replicationSummary ?? {}) as Json;
  return (
    <dl data-field="replication-summary">
      <dt>independent batches</dt>
      <dd data-field="independent-batches">
        {String(s.independentBatches ?? 0)}
      </dd>
      <dt>observations</dt>
      <dd data-field="observations">{String(s.observations ?? 0)}</dd>
      <dt>repeat-type counts</dt>
      <dd data-field="by-repeat-type">
        {JSON.stringify(s.byRepeatType ?? {})}
      </dd>
      <dt>note</dt>
      <dd>{String(s.note ?? "—")}</dd>
    </dl>
  );
}

function ContractCheck({ measurementId }: { measurementId: string }) {
  const [metricText, setMetricText] = useState(
    JSON.stringify({ name: "viscosity", target: ">= 100 mPa·s" }, null, 2),
  );
  const [result, setResult] = useState<Json | null>(null);
  const [error, setError] = useState<string | null>(null);

  return (
    <details data-field="contract-check">
      <summary>contract comparison</summary>
      <textarea
        aria-label="contract metric (JSON)"
        rows={4}
        value={metricText}
        onChange={(e) => setMetricText(e.target.value)}
        className="cs-input"
      />
      <Button
        type="button"
        onClick={() => {
          setError(null);
          setResult(null);
          try {
            JSON.parse(metricText);
          } catch {
            setError("metric is not valid JSON");
            return;
          }
          setResult({ __pending: metricText });
        }}
      >
        compare
      </Button>
      {error && (
        <p role="alert" className="cs-field__error">
          {error}
        </p>
      )}
      {result?.__pending != null && (
        <Suspense fallback={<LoadingState label="comparing…" />}>
          <ContractCheckResult
            measurementId={measurementId}
            metric={JSON.parse(String(result.__pending))}
          />
        </Suspense>
      )}
    </details>
  );
}

function ContractCheckResult({
  measurementId,
  metric,
}: {
  measurementId: string;
  metric: Json;
}) {
  const data = useLazyLoadQuery<labResultsContractCheckQuery>(
    ContractCheckQuery,
    { measurementId, metric },
    { fetchPolicy: "network-only" },
  );
  const r = (data.measurementContractCheck ?? {}) as Json;
  const findings = (r.findings ?? []) as { kind?: string; text?: string; action?: string }[];
  return (
    <div data-field="contract-verdict" data-verdict={String(r.verdict ?? "")}>
      <p>
        <Badge
          tone={
            r.verdict === "met"
              ? "success"
              : r.verdict === "not_met"
                ? "danger"
                : "warning"
          }
        >
          {String(r.verdict ?? "?")}
        </Badge>
      </p>
      {findings.length > 0 && (
        <ul aria-label="comparison findings">
          {findings.map((f, i) => (
            <li key={i} data-finding-kind={f.kind}>
              {f.text}
              {f.action ? ` — action: ${f.action}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function MeasurementItem({
  m,
  onChanged,
}: {
  m: MeasurementRow;
  onChanged: () => void;
}) {
  const [review, reviewing] =
    useMutation<labResultsMeasurementReviewMutation>(
      MeasurementReviewMutation,
    );
  const [apply, applying] =
    useMutation<labResultsMeasurementApplicabilityMutation>(
      MeasurementApplicabilityMutation,
    );
  const [amend, amending] =
    useMutation<labResultsMeasurementAmendMutation>(MeasurementAmendMutation);
  const [note, setNote] = useState("");
  const [amendOpen, setAmendOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [newValue, setNewValue] = useState(JSON.stringify(m.value ?? {}, null, 2));
  const [error, setError] = useState<string | null>(null);
  const pending = reviewing || applying || amending;

  return (
    <li data-measurement-id={m.id} data-status={m.status}>
      <p>
        <strong>{m.method}</strong>{" "}
        <Badge tone={STATUS_TONE[m.status] ?? "neutral"}>{m.status}</Badge>{" "}
        <Badge tone="info">{m.repeatType}</Badge>{" "}
        {m.metric ? (
          <Badge tone="info">metric: {m.metric}</Badge>
        ) : (
          <Badge tone="neutral">unattributed</Badge>
        )}{" "}
        {!m.applicable && <Badge tone="warning">not contract-applicable</Badge>}{" "}
        {m.supersededBy && <Badge tone="danger">superseded</Badge>}
      </p>
      <dl>
        <dt>value</dt>
        <dd>
          <ValueLabel m={m} />
        </dd>
        {m.reviewNote && (
          <>
            <dt>review note</dt>
            <dd>{m.reviewNote}</dd>
          </>
        )}
        {m.applicabilityNote && (
          <>
            <dt>applicability note</dt>
            <dd>{m.applicabilityNote}</dd>
          </>
        )}
      </dl>
      {((m.amendments ?? []) as Json[]).length > 0 && (
        <ul aria-label="amendments" data-field="amendments">
          {((m.amendments ?? []) as Json[]).map((a, i) => (
            <li key={i} data-field="amendment">
              amendment: {String(a.reason ?? "")} — corrected to{" "}
              {JSON.stringify(a.value ?? {})}
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p role="alert" className="cs-field__error">
          {error}
        </p>
      )}
      <div>
        <TextField
          label="review note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <Button
          type="button"
          disabled={pending}
          onClick={() =>
            review({
              variables: {
                input: { measurementId: m.id, decision: "accepted", note: note || undefined },
              },
              onCompleted: (r) => {
                if (!showErrs(r.lab?.measurements?.measurementReview.errors, setError))
                  onChanged();
              },
              onError: (e) => setError(e.message),
            })
          }
        >
          accept
        </Button>{" "}
        <Button
          type="button"
          disabled={pending}
          onClick={() =>
            review({
              variables: {
                input: { measurementId: m.id, decision: "rejected", note: note || undefined },
              },
              onCompleted: (r) => {
                if (!showErrs(r.lab?.measurements?.measurementReview.errors, setError))
                  onChanged();
              },
              onError: (e) => setError(e.message),
            })
          }
        >
          reject
        </Button>{" "}
        <Button
          type="button"
          disabled={pending}
          onClick={() =>
            apply({
              variables: {
                input: {
                  measurementId: m.id,
                  applicable: !m.applicable,
                  note: note || undefined,
                },
              },
              onCompleted: (r) => {
                if (
                  !showErrs(
                    r.lab?.measurements?.measurementApplicability.errors,
                    setError,
                  )
                )
                  onChanged();
              },
              onError: (e) => setError(e.message),
            })
          }
        >
          {m.applicable ? "mark not applicable" : "mark applicable"}
        </Button>{" "}
        <Button type="button" onClick={() => setAmendOpen((o) => !o)}>
          amend
        </Button>
      </div>
      {amendOpen && (
        <section aria-label="amend measurement" data-field="amend-form">
          <p className="cs-hint">
            corrections are amendments — the original reading stays immutable
            and is marked superseded; a reason is required.
          </p>
          <TextField
            label="amendment reason (required)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <textarea
            aria-label="amended value (JSON)"
            rows={4}
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            className="cs-input"
          />
          <Button
            type="button"
            disabled={pending || !reason.trim()}
            onClick={() => {
              let value: unknown;
              try {
                value = JSON.parse(newValue);
              } catch {
                setError("amended value is not valid JSON");
                return;
              }
              amend({
                variables: {
                  input: {
                    measurementId: m.id,
                    reason,
                    value,
                  },
                },
                onCompleted: (r) => {
                  if (
                    !showErrs(r.lab?.measurements?.measurementAmend.errors, setError)
                  ) {
                    setAmendOpen(false);
                    onChanged();
                  }
                },
                onError: (e) => setError(e.message),
              });
            }}
          >
            submit amendment
          </Button>
        </section>
      )}
      <ContractCheck measurementId={m.id} />
    </li>
  );
}

function MeasurementForm({
  sampleId,
  onChanged,
}: {
  sampleId: string;
  onChanged: () => void;
}) {
  const [commit, pending] =
    useMutation<labResultsMeasurementRecordMutation>(
      MeasurementRecordMutation,
    );
  const [method, setMethod] = useState("");
  const [metric, setMetric] = useState("");
  const [repeatType, setRepeatType] = useState("same_sample");
  const [valueText, setValueText] = useState(
    JSON.stringify({ kind: "numeric", value: "102.4", unit: "mPa·s" }, null, 2),
  );
  const [error, setError] = useState<string | null>(null);

  return (
    <details data-field="measurement-form">
      <summary>record measurement</summary>
      <TextField
        label="method"
        value={method}
        onChange={(e) => setMethod(e.target.value)}
      />
      <TextField
        label="contract metric id (optional — unattributed readings cannot satisfy a metric)"
        value={metric}
        onChange={(e) => setMetric(e.target.value)}
      />
      <div className="cs-field">
        <label className="cs-field__label" htmlFor={`repeat-${sampleId}`}>
          repeat type
        </label>
        <select
          id={`repeat-${sampleId}`}
          className="cs-input"
          value={repeatType}
          onChange={(e) => setRepeatType(e.target.value)}
        >
          <option value="same_sample">same sample (repeat reading)</option>
          <option value="independent_batch">independent batch</option>
          <option value="independent_operator">independent operator</option>
          <option value="timepoint">timepoint</option>
        </select>
      </div>
      <textarea
        aria-label="measurement value (JSON)"
        rows={5}
        value={valueText}
        onChange={(e) => setValueText(e.target.value)}
        className="cs-input"
      />
      {error && (
        <p role="alert" className="cs-field__error">
          {error}
        </p>
      )}
      <Button
        type="button"
        disabled={pending || !method.trim()}
        onClick={() => {
          setError(null);
          let value: unknown;
          try {
            value = JSON.parse(valueText);
          } catch {
            setError("value is not valid JSON");
            return;
          }
          commit({
            variables: {
              input: {
                sampleId,
                method,
                repeatType,
                value,
                metric: metric.trim() || undefined,
              },
            },
            onCompleted: (r) => {
              if (
                !showErrs(
                  r.lab?.measurements?.measurementRecord.errors,
                  setError,
                )
              )
                onChanged();
            },
            onError: (e) => setError(e.message),
          });
        }}
      >
        record
      </Button>
    </details>
  );
}

function BatchCard({ batch, onChanged }: { batch: Batch; onChanged: () => void }) {
  const [addSample, adding] =
    useMutation<labResultsSampleAddMutation>(SampleAddMutation);
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState("aliquot");
  const [error, setError] = useState<string | null>(null);

  return (
    <li data-batch-id={batch.id}>
      <p>
        <strong>batch {batch.label}</strong>{" "}
        <Badge tone="info">independent preparation</Badge>
      </p>
      <ul aria-label="samples">
        {batch.samples.map((s) => (
          <li key={s.id} data-sample-id={s.id}>
            <p>
              sample {s.label} <Badge tone="neutral">{s.kind}</Badge>
            </p>
            {s.measurements.length > 0 && (
              <ul aria-label="measurements">
                {s.measurements.map((m) => (
                  <MeasurementItem key={m.id} m={m} onChanged={onChanged} />
                ))}
              </ul>
            )}
            <MeasurementForm sampleId={s.id} onChanged={onChanged} />
          </li>
        ))}
      </ul>
      <div className="cs-inline-form">
        <TextField
          label="new sample label"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <select
          aria-label="sample kind"
          className="cs-input"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="aliquot">aliquot</option>
          <option value="timepoint">timepoint</option>
          <option value="whole">whole</option>
        </select>
        <Button
          type="button"
          disabled={adding || !label.trim()}
          onClick={() =>
            addSample({
              variables: { input: { batchId: batch.id, label, kind } },
              onCompleted: (r) => {
                if (!showErrs(r.lab?.measurements?.sampleAdd.errors, setError)) {
                  setLabel("");
                  onChanged();
                }
              },
              onError: (e) => setError(e.message),
            })
          }
        >
          add sample
        </Button>
      </div>
      {error && (
        <p role="alert" className="cs-field__error">
          {error}
        </p>
      )}
    </li>
  );
}

function ExecutionCard({
  execution,
  onChanged,
}: {
  execution: Execution;
  onChanged: () => void;
}) {
  const [close, closing] =
    useMutation<labResultsExecutionCloseMutation>(ExecutionCloseMutation);
  const [record, recording] =
    useMutation<labResultsActualsRecordMutation>(ActualsRecordMutation);
  const [addBatch, addingBatch] =
    useMutation<labResultsBatchAddMutation>(BatchAddMutation);
  const [batchLabel, setBatchLabel] = useState("");
  const [actualsText, setActualsText] = useState(
    JSON.stringify({ materials: [], process: "as planned" }, null, 2),
  );
  const [deviationsText, setDeviationsText] = useState("[]");
  const [observations, setObservations] = useState("");
  const [error, setError] = useState<string | null>(null);
  const deviations = (execution.deviations ?? []) as unknown[];

  return (
    <li
      className="cs-execution"
      data-execution-id={execution.id}
      data-status={execution.status}
      data-historical={execution.historical}
    >
      <p>
        <strong>execution {execution.id.slice(0, 8)}…</strong>{" "}
        <Badge tone={STATUS_TONE[execution.status] ?? "neutral"}>
          {execution.status}
        </Badge>{" "}
        <Badge tone="warning">{MANUAL_LABEL}</Badge>{" "}
        {execution.historical && (
          <Badge tone="info">historical import — not retrospectively approved</Badge>
        )}
      </p>
      <dl>
        <dt>plan</dt>
        <dd>
          <code>{execution.planId ?? "— (historical record)"}</code>
        </dd>
      </dl>
      {deviations.length > 0 && (
        <p data-field="deviations">
          <Badge tone="warning">deviations recorded</Badge>{" "}
          {deviations.length} deviation(s) — contract applicability may differ
          from scientific usefulness.
        </p>
      )}
      <Suspense fallback={<LoadingState label="replication…" />}>
        <ReplicationSummary executionId={execution.id} />
      </Suspense>
      {execution.status === "in_progress" && (
        <details data-field="actuals-form">
          <summary>record actuals / deviations</summary>
          <textarea
            aria-label="actual materials and process (JSON)"
            rows={5}
            value={actualsText}
            onChange={(e) => setActualsText(e.target.value)}
            className="cs-input"
          />
          <textarea
            aria-label="deviations (JSON list)"
            rows={3}
            value={deviationsText}
            onChange={(e) => setDeviationsText(e.target.value)}
            className="cs-input"
          />
          <TextField
            label="observations"
            value={observations}
            onChange={(e) => setObservations(e.target.value)}
          />
          <Button
            type="button"
            disabled={recording}
            onClick={() => {
              setError(null);
              let actual: unknown;
              let deviations: unknown;
              try {
                actual = JSON.parse(actualsText);
                deviations = JSON.parse(deviationsText);
              } catch {
                setError("actuals/deviations are not valid JSON");
                return;
              }
              record({
                variables: {
                  input: {
                    executionId: execution.id,
                    actual,
                    deviations,
                    observations: observations || undefined,
                  },
                },
                onCompleted: (r) => {
                  if (
                    !showErrs(r.lab?.measurements?.actualsRecord.errors, setError)
                  )
                    onChanged();
                },
                onError: (e) => setError(e.message),
              });
            }}
          >
            record actuals
          </Button>
        </details>
      )}
      {error && (
        <p role="alert" className="cs-field__error">
          {error}
        </p>
      )}
      {execution.batches.length > 0 && (
        <ul aria-label="batches">
          {execution.batches.map((b) => (
            <BatchCard key={b.id} batch={b} onChanged={onChanged} />
          ))}
        </ul>
      )}
      {execution.status === "in_progress" && (
        <div className="cs-inline-form">
          <TextField
            label="new batch label"
            value={batchLabel}
            onChange={(e) => setBatchLabel(e.target.value)}
          />
          <Button
            type="button"
            disabled={addingBatch || !batchLabel.trim()}
            onClick={() =>
              addBatch({
                variables: {
                  input: { executionId: execution.id, label: batchLabel },
                },
                onCompleted: (r) => {
                  if (!showErrs(r.lab?.measurements?.batchAdd.errors, setError)) {
                    setBatchLabel("");
                    onChanged();
                  }
                },
                onError: (e) => setError(e.message),
              })
            }
          >
            add batch
          </Button>{" "}
          <Button
            type="button"
            disabled={closing}
            onClick={() =>
              close({
                variables: {
                  input: { executionId: execution.id, status: "completed" },
                },
                onCompleted: (r) => {
                  if (
                    !showErrs(r.lab?.measurements?.executionClose.errors, setError)
                  )
                    onChanged();
                },
                onError: (e) => setError(e.message),
              })
            }
          >
            close execution
          </Button>
        </div>
      )}
    </li>
  );
}

function OpenExecutionControls({
  taskId,
  onChanged,
}: {
  taskId: string;
  onChanged: () => void;
}) {
  const data = useLazyLoadQuery<labPlansTaskPlansQuery>(
    TaskPlansQuery,
    { taskId },
    { fetchPolicy: "network-only" },
  );
  const [open, opening] =
    useMutation<labResultsExecutionOpenMutation>(ExecutionOpenMutation);
  const [importHistorical, importing] =
    useMutation<labResultsExecutionHistoricalMutation>(
      ExecutionHistoricalMutation,
    );
  const [histText, setHistText] = useState(
    JSON.stringify({ source: "lab notebook p.41", notes: "" }, null, 2),
  );
  const [error, setError] = useState<string | null>(null);
  const approved = data.taskPlans.edges
    .map((e) => e.node)
    .filter((n) => n != null && n.status === "approved");

  return (
    <section aria-label="start executions">
      {approved.length > 0 && (
        <ul aria-label="approved plans ready to execute">
          {approved.map((p) => (
            <li key={p!.id}>
              {p!.title}{" "}
              <Button
                type="button"
                disabled={opening}
                onClick={() =>
                  open({
                    variables: { input: { planId: p!.id } },
                    onCompleted: (r) => {
                      if (
                        !showErrs(
                          r.lab?.measurements?.executionOpen.errors,
                          setError,
                        )
                      )
                        onChanged();
                    },
                    onError: (e) => setError(e.message),
                  })
                }
              >
                open manual execution
              </Button>
            </li>
          ))}
        </ul>
      )}
      <details data-field="historical-import">
        <summary>import historical record (never retrospectively approved)</summary>
        <textarea
          aria-label="historical record payload (JSON)"
          rows={5}
          value={histText}
          onChange={(e) => setHistText(e.target.value)}
          className="cs-input"
        />
        <Button
          type="button"
          disabled={importing}
          onClick={() => {
            setError(null);
            let payload: unknown;
            try {
              payload = JSON.parse(histText);
            } catch {
              setError("payload is not valid JSON");
              return;
            }
            importHistorical({
              variables: { input: { taskId, payload } },
              onCompleted: (r) => {
                if (
                  !showErrs(
                    r.lab?.measurements?.executionHistoricalImport.errors,
                    setError,
                  )
                )
                  onChanged();
              },
              onError: (e) => setError(e.message),
            });
          }}
        >
          import historical record
        </Button>
      </details>
      {error && (
        <p role="alert" className="cs-field__error">
          {error}
        </p>
      )}
    </section>
  );
}

/** Executions, batches, samples and measurement review for a task
 * (§6.3, §14.2, CS-0502). Three readings of one aliquot are replicate
 * readings — never independent batches. Corrections are amendments;
 * the original stays immutable and shows superseded. Historical imports
 * are marked and carry no fabricated approval. */
export function ResultsPanel({ taskId }: { taskId: string }) {
  const [fetchKey, setFetchKey] = useState(0);
  const data = useLazyLoadQuery<labResultsTaskExecutionsQuery>(
    TaskExecutionsQuery,
    { taskId },
    { fetchKey, fetchPolicy: "network-only" },
  );
  const bump = () => setFetchKey((k) => k + 1);
  const executions = data.taskExecutions.filter((e) => e != null);

  return (
    <section aria-label="executions and results">
      <h2>executions &amp; results</h2>
      <Suspense fallback={<LoadingState label="loading approved plans…" />}>
        <OpenExecutionControls taskId={taskId} onChanged={bump} />
      </Suspense>
      {executions.length === 0 ? (
        <EmptyState title="no executions yet — approve a plan or import a historical record." />
      ) : (
        <ul aria-label="executions">
          {executions.map((e) => (
            <ExecutionCard key={e.id} execution={e} onChanged={bump} />
          ))}
        </ul>
      )}
    </section>
  );
}
