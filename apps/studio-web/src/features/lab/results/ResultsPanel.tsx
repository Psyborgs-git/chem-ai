import { Suspense, useId, useRef, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../../components/atoms/Badge";
import { Button } from "../../../components/atoms/Button";
import { TextField } from "../../../components/atoms/TextField";
import { EmptyState, LoadingState } from "../../../components/states/states";
import { ChemistryArt } from "../../../components/layout/ChemistryArt";
import { rawUuid } from "../../../relay/network";
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
import { ActualsCaptureForm, ContractMetricForm, HistoricalRecordForm } from "./LabCaptureForms";

import type { labResultsTaskExecutionsQuery } from "../../../__generated__/labResultsTaskExecutionsQuery.graphql";
import type { labResultsReplicationSummaryQuery } from "../../../__generated__/labResultsReplicationSummaryQuery.graphql";
import type { labResultsContractCheckQuery } from "../../../__generated__/labResultsContractCheckQuery.graphql";
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
import "../lab-workflow.css";

type Execution = NonNullable<
  labResultsTaskExecutionsQuery["response"]["taskExecutions"][number]
>;
type Batch = Execution["batches"][number];
type Sample = Batch["samples"][number];
type MeasurementRow = Sample["measurements"][number];
type Errs = readonly { code: string; message: string }[] | null | undefined;
type Json = Record<string, unknown>;
type PlanContext = { id: string; title: string; status: string; payload: unknown };
type ContractContext = { id: string; revision: number; status: string; payload: unknown };
export type MeasurementMetric = { id: string; label: string; unit?: string; target?: string };

function object(value: unknown): Json {
  return value != null && typeof value === "object" && !Array.isArray(value) ? value as Json : {};
}

function metricTarget(metric: Json): string | undefined {
  const unit = typeof metric.unit === "string" && metric.unit ? ` ${metric.unit}` : "";
  const rawValues = metric.target_values ?? metric.targetValues;
  const values = Array.isArray(rawValues)
    ? rawValues.filter((value) => typeof value === "string" || typeof value === "number").map(String)
    : [];
  const operators: Record<string, string> = { gte: "≥", ">=": "≥", gt: ">", ">": ">", lte: "≤", "<=": "≤", lt: "<", "<": "<", eq: "=", "=": "=" };
  if (typeof metric.operator === "string" && values.length) {
    if (operators[metric.operator]) return `${operators[metric.operator]} ${values[0]}${unit}`;
    if (metric.operator === "between" && values.length === 2) return `Between ${values[0]} and ${values[1]}${unit}`;
    if (metric.operator === "categorical_match") return `Matches ${values.join(", ")}`;
  }
  return typeof metric.target === "string" && metric.target.trim() ? metric.target : undefined;
}

function metricChoices(payload: unknown): MeasurementMetric[] {
  const metrics = object(payload).metrics;
  if (!Array.isArray(metrics)) return [];
  return metrics.flatMap((value, index) => {
    const metric = object(value);
    if (typeof metric.id !== "string" || !metric.id) return [];
    const label = typeof metric.label === "string" && metric.label ? metric.label
      : typeof metric.name === "string" && metric.name ? metric.name : `Criterion ${index + 1}`;
    const target = metricTarget(metric);
    return [{ id: metric.id, label, ...(typeof metric.unit === "string" && metric.unit ? { unit: metric.unit } : {}), ...(target ? { target } : {}) }];
  });
}

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

function ReplicationSummary({ executionId, refreshKey }: { executionId: string; refreshKey: number }) {
  const data = useLazyLoadQuery<labResultsReplicationSummaryQuery>(
    ReplicationSummaryQuery,
    { executionId },
    { fetchPolicy: "network-only", fetchKey: refreshKey },
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
  const [metric, setMetric] = useState<Json | null>(null);
  const [comparisonKey, setComparisonKey] = useState(0);
  return (
    <details data-field="contract-check">
      <summary>contract comparison</summary>
      <ContractMetricForm onCompare={(value) => { setMetric(value); setComparisonKey((key) => key + 1); }} />
      {metric && (
        <Suspense fallback={<LoadingState label="comparing…" />}>
          <ContractCheckResult key={comparisonKey} measurementId={measurementId} metric={metric} />
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
        {m.supersededBy && ((m.amendments ?? []) as Json[]).length > 0 && (
          <>
            <dt>effective value</dt>
            <dd data-field="effective-value">
              {JSON.stringify(
                ((m.amendments ?? []) as Json[])[
                  ((m.amendments ?? []) as Json[]).length - 1
                ]?.value ?? {},
              )}{" "}
              <Badge tone="warning">corrected</Badge>
            </dd>
          </>
        )}
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

export function MeasurementForm({
  sampleId,
  sampleLabel,
  defaultMethod = "",
  metrics = [],
  onChanged,
}: {
  sampleId: string;
  sampleLabel?: string;
  defaultMethod?: string;
  metrics?: readonly MeasurementMetric[];
  onChanged: () => void;
}) {
  const [commit, pending] = useMutation<labResultsMeasurementRecordMutation>(MeasurementRecordMutation);
  const id = useId();
  const initialMetric = metrics.length === 1 ? metrics[0] : null;
  const [method, setMethod] = useState(defaultMethod);
  const [metric, setMetric] = useState(initialMetric?.id ?? "");
  const [repeatType, setRepeatType] = useState("same_sample");
  const [kind, setKind] = useState("numeric");
  const [reading, setReading] = useState("");
  const [upper, setUpper] = useState("");
  const [unit, setUnit] = useState(initialMetric?.unit ?? "");
  const unitEdited = useRef(false);
  const [scale, setScale] = useState("");
  const [reason, setReason] = useState("not_measured");
  const [advanced, setAdvanced] = useState(false);
  const [valueText, setValueText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const numeric = ["numeric", "interval", "below_detection", "above_quantification"].includes(kind);
  const decimal = /^[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?$/i;
  const ready = advanced ? Boolean(valueText.trim()) : kind === "missing" || (
    Boolean(reading.trim()) && (!numeric || (decimal.test(reading.trim()) && Boolean(unit.trim()))) &&
    (kind !== "interval" || decimal.test(upper.trim())) &&
    (kind !== "ordinal" || scale.split(",").map((s) => s.trim()).includes(reading.trim()))
  );
  const repeatLabels: Record<string, string> = { same_sample: "Repeat reading of this sample", independent_batch: "Independent preparation", independent_operator: "Independent operator", timepoint: "Timepoint" };
  const knownMetric = metrics.find((choice) => choice.id === metric);

  function chooseMetric(next: string) {
    setMetric(next);
    if (!unitEdited.current) setUnit(metrics.find((choice) => choice.id === next)?.unit ?? "");
  }

  return (
    <details data-field="measurement-form" className="cs-lab-measurement-form">
      <summary>record measurement</summary>
      {sampleLabel && <p className="cs-field__hint">Record a result for <strong>{sampleLabel}</strong>.</p>}
      <div className="cs-field">
        <label className="cs-field__label" htmlFor={`${id}-metric`}>What did you measure?</label>
        <select id={`${id}-metric`} className="cs-select" value={metric} onChange={(event) => chooseMetric(event.target.value)}>
          <option value="">Unattributed reading</option>
          {metrics.map((choice) => <option key={choice.id} value={choice.id}>{choice.label}{choice.unit ? ` (${choice.unit})` : ""}</option>)}
          {metric && !knownMetric && <option value={metric}>Custom criterion (advanced)</option>}
        </select>
        <p className="cs-field__hint">{metrics.length ? "These criteria come from the frozen agreement linked to this experiment." : "No named criteria are linked to this record. You can record an unattributed result."}</p>
        {knownMetric?.target && <p className="cs-field__hint" data-field="measurement-target"><strong>Target:</strong> {knownMetric.target}</p>}
      </div>
      {advanced ? <textarea aria-label="measurement value (JSON)" rows={5} value={valueText} onChange={(e) => setValueText(e.target.value)} className="cs-input" /> : kind === "missing" ? (
        <div className="cs-field"><label className="cs-field__label" htmlFor={`${id}-missing`}>Missing reason</label>
          <select id={`${id}-missing`} className="cs-select" value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="not_measured">Not measured</option><option value="instrument_failure">Instrument failure</option><option value="sample_lost">Sample lost</option><option value="unknown">Unknown</option>
          </select>
        </div>
      ) : <div className="cs-lab-reading-fields">
        <TextField label={kind === "interval" ? "Lower bound" : kind.includes("detection") || kind.includes("quantification") ? "Detection / quantification limit" : numeric ? "Measured value" : "Result label"}
          inputMode={numeric ? "decimal" : "text"} value={reading} onChange={(e) => setReading(e.target.value)} required />
        {kind === "interval" && <TextField label="Upper bound" inputMode="decimal" value={upper} onChange={(e) => setUpper(e.target.value)} required />}
        {numeric && <TextField label="Measurement unit" hint="Confirm the unit used for this reading." value={unit} onChange={(e) => { unitEdited.current = true; setUnit(e.target.value); }} required />}
        {kind === "ordinal" && <TextField label="Ordered scale" hint="Comma-separated labels, from lowest to highest." value={scale} onChange={(e) => setScale(e.target.value)} required />}
      </div>}
      <div className="cs-lab-method-summary"><span><strong>Method:</strong> {method || "Enter the method below"}</span><span>{repeatLabels[repeatType]}</span></div>
      {defaultMethod && <p className="cs-field__hint">Using the method from the approved plan. Change it below if your actual procedure differed.</p>}
      <details data-field="measurement-context" className="cs-lab-secondary" open={!defaultMethod}>
        <summary>Method and repeat details</summary>
        <TextField label="method" hint="Carried from the plan when available; edit it if the actual method differed." value={method} onChange={(e) => setMethod(e.target.value)} />
        <div className="cs-field"><label className="cs-field__label" htmlFor={`${id}-repeat`}>repeat type</label>
          <select id={`${id}-repeat`} className="cs-select" value={repeatType} onChange={(e) => setRepeatType(e.target.value)}>
            <option value="same_sample">same sample (repeat reading)</option><option value="independent_batch">independent batch</option><option value="independent_operator">independent operator</option><option value="timepoint">timepoint</option>
          </select>
        </div>
      </details>
      <details data-field="measurement-options" className="cs-lab-secondary">
        <summary>Other result types and advanced options</summary>
        <div className="cs-field"><label className="cs-field__label" htmlFor={`${id}-kind`}>Result type</label>
          <select id={`${id}-kind`} className="cs-select" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="numeric">Numeric reading</option><option value="interval">Interval</option><option value="below_detection">Below detection limit</option><option value="above_quantification">Above quantification limit</option><option value="categorical">Category</option><option value="ordinal">Ordered category</option><option value="missing">Missing reading</option>
          </select>
        </div>
        <div className="cs-field"><label className="cs-field__label" htmlFor={`${id}-mode`}>Value entry</label>
          <select id={`${id}-mode`} className="cs-select" value={advanced ? "json" : "structured"} onChange={(e) => setAdvanced(e.target.value === "json")}><option value="structured">Measurement fields</option><option value="json">Advanced JSON payload</option></select>
        </div>
        <TextField label="contract metric id (optional — unattributed readings cannot satisfy a metric)" hint="Use the named criterion above for normal entry." value={metric} onChange={(e) => chooseMetric(e.target.value)} />
      </details>
      {error && <p role="alert" className="cs-field__error">{error}</p>}
      <Button type="button" disabled={pending || !method.trim() || !ready} onClick={() => {
        setError(null);
        if (pending || !ready || !method.trim()) return;
        let value: unknown;
        if (advanced) { try { value = JSON.parse(valueText); } catch { setError("value is not valid JSON"); return; } }
        else value = kind === "missing" ? { kind, reason } : kind === "interval" ? { kind, low: reading.trim(), high: upper.trim(), unit: unit.trim() }
          : kind === "below_detection" || kind === "above_quantification" ? { kind, limit: reading.trim(), unit: unit.trim() }
            : kind === "numeric" ? { kind, value: reading.trim(), unit: unit.trim() }
              : { kind, label: reading.trim(), ...(kind === "ordinal" ? { scale: scale.split(",").map((s) => s.trim()) } : {}) };
        commit({ variables: { input: { sampleId, method, repeatType, value, metric: metric.trim() || undefined } },
          onCompleted: (response) => { if (!showErrs(response.lab?.measurements?.measurementRecord.errors, setError)) { setReading(""); setUpper(""); setValueText(""); onChanged(); } },
          onError: (failure) => setError(failure.message),
        });
      }}>record</Button>
    </details>
  );
}

function BatchCard({ batch, onChanged, method, metrics }: {
  batch: Batch; onChanged: () => void; method: string; metrics: readonly MeasurementMetric[];
}) {
  const [addSample, adding] =
    useMutation<labResultsSampleAddMutation>(SampleAddMutation);
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState("aliquot");
  const [error, setError] = useState<string | null>(null);

  return (
    <li className="cs-lab-batch" data-batch-id={batch.id}>
      <p>
        <strong>batch {batch.label}</strong>{" "}
        <Badge tone="info">independent preparation</Badge>
      </p>
      <ul aria-label="samples">
        {batch.samples.map((s) => (
          <li className="cs-lab-sample" key={s.id} data-sample-id={s.id}>
            <p className="cs-lab-breadcrumb">Batch {batch.label}<span aria-hidden="true"> / </span>Sample {s.label}</p>
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
            <MeasurementForm sampleId={s.id} sampleLabel={s.label} defaultMethod={method} metrics={metrics} onChanged={onChanged} />
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
  refreshKey,
  plan,
  contracts,
}: {
  execution: Execution;
  onChanged: () => void;
  refreshKey: number;
  plan: PlanContext | undefined;
  contracts: readonly ContractContext[];
}) {
  const [close, closing] =
    useMutation<labResultsExecutionCloseMutation>(ExecutionCloseMutation);
  const [record, recording] =
    useMutation<labResultsActualsRecordMutation>(ActualsRecordMutation);
  const [addBatch, addingBatch] =
    useMutation<labResultsBatchAddMutation>(BatchAddMutation);
  const [batchLabel, setBatchLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const deviations = (execution.deviations ?? []) as unknown[];
  const planPayload = object(plan?.payload);
  const contract = contracts.find((entry) => rawUuid(entry.id) === planPayload.contractRevisionId && ["frozen", "accepted"].includes(entry.status));
  const metrics = contract ? metricChoices(contract.payload) : [];
  const method = typeof planPayload.method === "string" ? planPayload.method : "";

  return (
    <li
      className="cs-execution"
      data-execution-id={execution.id}
      data-status={execution.status}
      data-historical={execution.historical}
    >
      <p>
        <strong>{plan?.title ?? (execution.historical ? "Imported lab record" : "Manual lab record")}</strong>{" "}
        <Badge tone={STATUS_TONE[execution.status] ?? "neutral"}>
          {execution.status}
        </Badge>{" "}
        <Badge tone="warning">{MANUAL_LABEL}</Badge>{" "}
        {execution.historical && (
          <Badge tone="info">historical import — not retrospectively approved</Badge>
        )}
      </p>
      <details className="cs-technical"><summary>Record identifiers</summary><dl>
        <dt>plan</dt>
        <dd>
          <code>{execution.planId ?? "— (historical record)"}</code>
        </dd>
        <dt>execution</dt><dd><code>{execution.id}</code></dd>
      </dl></details>
      {contract && <p className="cs-field__hint">Results answer the agreed criteria in revision {contract.revision}.</p>}
      {deviations.length > 0 && (
        <p data-field="deviations">
          <Badge tone="warning">deviations recorded</Badge>{" "}
          {deviations.length} deviation(s) — contract applicability may differ
          from scientific usefulness.
        </p>
      )}
      <Suspense fallback={<LoadingState label="replication…" />}>
        <ReplicationSummary executionId={execution.id} refreshKey={refreshKey} />
      </Suspense>
      {execution.status === "in_progress" && (
        <ActualsCaptureForm pending={recording} onSubmit={(capture) => {
          setError(null);
          record({
            variables: { input: { executionId: execution.id, ...capture } },
            onCompleted: (r) => {
              if (!showErrs(r.lab?.measurements?.actualsRecord.errors, setError)) onChanged();
            },
            onError: (e) => setError(e.message),
          });
        }} />
      )}
      {error && (
        <p role="alert" className="cs-field__error">
          {error}
        </p>
      )}
      {execution.batches.length > 0 && (
        <ul aria-label="batches">
          {execution.batches.map((b) => (
            <BatchCard key={b.id} batch={b} method={method} metrics={metrics} onChanged={onChanged} />
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
  plans,
}: {
  taskId: string;
  onChanged: () => void;
  plans: readonly PlanContext[];
}) {
  const [open, opening] =
    useMutation<labResultsExecutionOpenMutation>(ExecutionOpenMutation);
  const [importHistorical, importing] =
    useMutation<labResultsExecutionHistoricalMutation>(
      ExecutionHistoricalMutation,
    );
  const [error, setError] = useState<string | null>(null);
  const approved = plans.filter((plan) => plan.status === "approved");

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
      <HistoricalRecordForm pending={importing} onSubmit={(payload) => {
        setError(null);
        importHistorical({
          variables: { input: { taskId, payload } },
          onCompleted: (r) => {
            if (!showErrs(r.lab?.measurements?.executionHistoricalImport.errors, setError)) onChanged();
          },
          onError: (e) => setError(e.message),
        });
      }} />
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
  const plans = (data.taskPlans?.edges ?? []).map((edge) => edge.node);
  const contracts = (data.taskContractRevisions?.edges ?? []).map((edge) => edge.node);

  return (
    <section aria-label="executions and results">
      <header className="cs-lab-step-heading"><div><p className="cs-eyebrow">Lab notebook</p><h2>Record a lab result</h2><p>Start with an approved plan. Add the batches and samples you actually prepared, then record their readings.</p></div><ChemistryArt kind="sources" /></header>
      <OpenExecutionControls taskId={taskId} plans={plans} onChanged={bump} />
      {executions.length === 0 ? (
        <EmptyState title="no executions yet — approve a plan or import a historical record." />
      ) : (
        <ul aria-label="executions">
          {executions.map((e) => (
            <ExecutionCard key={e.id} execution={e} plan={plans.find((plan) => rawUuid(plan.id) === e.planId || plan.id === e.planId)} contracts={contracts} onChanged={bump} refreshKey={fetchKey} />
          ))}
        </ul>
      )}
    </section>
  );
}
