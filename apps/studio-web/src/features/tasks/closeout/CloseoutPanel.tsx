import { Suspense, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../../components/atoms/Badge";
import { Button } from "../../../components/atoms/Button";
import { TextField } from "../../../components/atoms/TextField";
import { EmptyState, LoadingState } from "../../../components/states/states";
import {
  TaskCloseMutation,
  TaskEvaluationQuery,
  TaskTransitionMutation,
} from "./operations";

import type { tasksCloseoutEvaluationQuery } from "../../../__generated__/tasksCloseoutEvaluationQuery.graphql";
import type { tasksCloseoutCloseMutation } from "../../../__generated__/tasksCloseoutCloseMutation.graphql";
import type { tasksCloseoutTransitionMutation } from "../../../__generated__/tasksCloseoutTransitionMutation.graphql";

type Json = Record<string, unknown>;
type Finding = { kind?: string; text?: string; action?: string };
type MetricReport = {
  metricId?: string;
  label?: string;
  required?: boolean;
  verdict?: string;
  comparedAgainst?: string;
  evidenceIds?: string[];
  independentBatches?: number;
  findings?: Finding[];
};
type GateReport = {
  id?: string;
  text?: string;
  verdict?: string;
  metricVerdict?: string;
  findings?: Finding[];
};
type CandidateReport = {
  candidateRevisionId?: string;
  candidateRevision?: number;
  entityKind?: string;
  entityRevisionId?: string;
  eligibility?: string;
  metrics?: MetricReport[];
  gates?: GateReport[];
  evidenceIds?: string[];
  suggestedDecision?: string;
  supportedSuccessEligible?: boolean;
};

const VERDICT_TONE: Record<
  string,
  "success" | "danger" | "warning" | "neutral"
> = {
  met: "success",
  pass: "success",
  misses: "danger",
  fail: "danger",
  supported_success: "success",
  supported_failure: "danger",
  inconclusive: "warning",
  not_evaluated: "warning",
  stopped: "neutral",
};

const CLOSURE_DECISIONS = [
  "supported_success",
  "supported_failure",
  "inconclusive",
  "stopped",
] as const;

function FindingsList({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) return null;
  return (
    <ul aria-label="findings">
      {findings.map((f, i) => (
        <li key={i} data-finding-kind={f.kind ?? "unknown"}>
          {f.text}
          {f.action ? ` — action: ${f.action}` : ""}
        </li>
      ))}
    </ul>
  );
}

function MetricsGates({ report }: { report: Json }) {
  const metrics = (report.metrics ?? []) as MetricReport[];
  const gates = (report.gates ?? []) as GateReport[];
  return (
    <>
      {metrics.length > 0 && (
        <div
          className="cs-table-wrap"
          role="region"
          aria-label="contract metrics"
          tabIndex={0}
        >
          <table className="cs-table" data-field="metrics-table">
            <caption>contract metrics</caption>
            <thead>
              <tr>
                <th scope="col" className="cs-table__identity">
                  metric
                </th>
                <th scope="col">verdict</th>
                <th scope="col">compared against</th>
                <th scope="col">evidence</th>
              </tr>
            </thead>
            <tbody>
              {metrics.map((m) => (
                <tr
                  key={m.metricId}
                  data-field="metric-row"
                  data-verdict={m.verdict}
                >
                  <td className="cs-table__identity">
                    {m.label ?? m.metricId}
                    {m.required === false ? " (optional)" : ""}
                    <FindingsList findings={m.findings ?? []} />
                  </td>
                  <td data-field="metric-verdict">
                    <Badge tone={VERDICT_TONE[m.verdict ?? ""] ?? "neutral"}>
                      {m.verdict ?? "?"}
                    </Badge>
                  </td>
                  <td>{m.comparedAgainst ?? "—"}</td>
                  <td>{(m.evidenceIds ?? []).length} reading(s)</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {gates.length > 0 && (
        <div
          className="cs-table-wrap"
          role="region"
          aria-label="hard gates"
          tabIndex={0}
        >
          <table className="cs-table cs-table--fit" data-field="gates-table">
            <caption>hard gates — never compensated by performance</caption>
            <thead>
              <tr>
                <th scope="col" className="cs-table__identity">
                  gate
                </th>
                <th scope="col">verdict</th>
              </tr>
            </thead>
            <tbody>
              {gates.map((g) => (
                <tr key={g.id} data-field="gate-row" data-verdict={g.verdict}>
                  <td className="cs-table__identity">
                    <span className="cs-table__cell">
                      {g.text ?? g.id}
                      <FindingsList findings={g.findings ?? []} />
                    </span>
                  </td>
                  <td data-field="gate-verdict">
                    <Badge tone={VERDICT_TONE[g.verdict ?? ""] ?? "neutral"}>
                      {g.verdict ?? "?"}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function CandidateReports({
  candidates,
  selectedId,
  onSelect,
}: {
  candidates: CandidateReport[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (candidates.length === 0) return null;
  const selected = candidates.find(
    (c) => c.candidateRevisionId === selectedId,
  );
  return (
    <div data-field="candidate-reports">
      {candidates.length > 1 && (
        <p className="cs-hint">
          {candidates.length} accepted candidates — each is reported
          separately and no pooled verdict exists. Select the candidate whose
          report you reviewed.
        </p>
      )}
      <div
        className="cs-table-wrap"
        role="region"
        aria-label="candidates"
        tabIndex={0}
      >
        <table className="cs-table cs-table--fit" data-field="candidates-table">
          <caption>candidates evaluated against this contract</caption>
          <thead>
            <tr>
              <th scope="col" className="cs-table__identity">
                candidate
              </th>
              <th scope="col">kind</th>
              <th scope="col">eligibility</th>
              <th scope="col">suggestion</th>
              <th scope="col">evidence</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c) => (
              <tr
                key={c.candidateRevisionId}
                data-field="candidate-row"
                data-selected={c.candidateRevisionId === selectedId}
              >
                <td className="cs-table__identity">
                  <label>
                    <input
                      type="radio"
                      name="evaluation-candidate"
                      checked={c.candidateRevisionId === selectedId}
                      onChange={() =>
                        c.candidateRevisionId &&
                        onSelect(c.candidateRevisionId)
                      }
                    />{" "}
                    rev {c.candidateRevision ?? "?"} —{" "}
                    {String(c.candidateRevisionId ?? "").slice(0, 8)}…
                  </label>
                </td>
                <td>{c.entityKind ?? "—"}</td>
                <td>{c.eligibility ?? "—"}</td>
                <td data-field="candidate-verdict">
                  <Badge
                    tone={
                      VERDICT_TONE[c.suggestedDecision ?? ""] ?? "neutral"
                    }
                  >
                    {c.suggestedDecision ?? "?"}
                  </Badge>
                </td>
                <td>{(c.evidenceIds ?? []).length} reading(s)</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selected ? (
        <div data-field="selected-candidate-report">
          <h4>
            report for candidate rev {selected.candidateRevision ?? "?"}
          </h4>
          <MetricsGates report={selected as unknown as Json} />
        </div>
      ) : (
        candidates.length > 1 && (
          <p className="cs-hint" data-field="select-candidate-hint">
            select a candidate above to view its per-candidate report.
          </p>
        )
      )}
    </div>
  );
}

function EvaluationReport({
  report,
  reassessment,
  candidates,
  selectedId,
  onSelectCandidate,
}: {
  report: Json;
  reassessment: Json;
  candidates: CandidateReport[];
  selectedId: string | null;
  onSelectCandidate: (id: string) => void;
}) {
  const unknowns = (report.unknowns ?? []) as string[];
  const findings = (report.findings ?? []) as Finding[];
  const stale = (reassessment.staleEvidenceIds ?? []) as {
    id?: string;
    status?: string;
  }[];

  return (
    <div data-field="evaluation-report">
      {reassessment.needsReassessment === true && (
        <div role="alert" data-field="reassessment-banner">
          <Badge tone="danger">reassessment required</Badge> evidence bound
          into the signed closure packet has since been superseded or revoked —
          the packet is unchanged (it is immutable); a new evaluation cycle is
          needed.
          {stale.length > 0 && (
            <ul>
              {stale.map((s) => (
                <li key={s.id}>
                  evidence {String(s.id).slice(0, 8)}… → {s.status}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <p>
        <Badge
          tone={
            VERDICT_TONE[String(report.suggestedDecision)] ?? "neutral"
          }
        >
          suggestion: {String(report.suggestedDecision ?? "?")}
        </Badge>{" "}
        <Badge tone="info">fixture-only — not scientific validation</Badge>{" "}
        <Badge tone="neutral">
          cycle {String(report.evaluationCycle ?? "?")}
        </Badge>
      </p>
      <p className="cs-hint">
        the evaluator only suggests — closure is always a human reviewer
        decision; nothing here auto-approves.
      </p>

      {report.assessable !== true && (
        <EmptyState
          title={String(report.reason ?? "task is not assessable yet")}
        />
      )}
      <FindingsList findings={findings} />

      <CandidateReports
        candidates={candidates}
        selectedId={selectedId}
        onSelect={onSelectCandidate}
      />

      {candidates.length === 0 && <MetricsGates report={report} />}

      {unknowns.length > 0 && (
        <div data-field="unknowns">
          <strong>open unknowns:</strong>
          <ul>
            {unknowns.map((u, i) => (
              <li key={i}>{u}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function CloseForm({
  taskId,
  eligible,
  candidates,
  selectedId,
  onSelectCandidate,
  onClosed,
}: {
  taskId: string;
  eligible: boolean;
  candidates: CandidateReport[];
  selectedId: string | null;
  onSelectCandidate: (id: string) => void;
  onClosed: () => void;
}) {
  const [close, closing] =
    useMutation<tasksCloseoutCloseMutation>(TaskCloseMutation);
  const [decision, setDecision] = useState<string>("inconclusive");
  const [note, setNote] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const needsCandidate = candidates.length > 1 && selectedId === null;

  return (
    <section aria-label="close task" data-field="close-form">
      <h4>human closure decision</h4>
      {candidates.length > 0 && (
        <div className="cs-field">
          <label className="cs-field__label" htmlFor="closure-candidate">
            candidate this closure binds
          </label>
          <select
            id="closure-candidate"
            className="cs-input"
            value={selectedId ?? ""}
            onChange={(e) => onSelectCandidate(e.target.value)}
          >
            <option value="" disabled>
              select the candidate whose report you reviewed
            </option>
            {candidates.map((c) => (
              <option
                key={c.candidateRevisionId}
                value={c.candidateRevisionId}
              >
                rev {c.candidateRevision ?? "?"} —{" "}
                {String(c.candidateRevisionId ?? "").slice(0, 8)}… (
                {c.entityKind ?? "entity"})
              </option>
            ))}
          </select>
          {needsCandidate && (
            <p className="cs-hint" data-field="candidate-required-hint">
              this task has multiple accepted candidates — the closure packet
              must bind the exact candidate whose report you reviewed.
            </p>
          )}
        </div>
      )}
      <div className="cs-field">
        <label className="cs-field__label" htmlFor="closure-decision">
          closure decision
        </label>
        <select
          id="closure-decision"
          className="cs-input"
          value={decision}
          onChange={(e) => setDecision(e.target.value)}
        >
          {CLOSURE_DECISIONS.map((d) => (
            <option
              key={d}
              value={d}
              disabled={d === "supported_success" && !eligible}
            >
              {d}
              {d === "supported_success" && !eligible
                ? " (evidence gate unmet)"
                : ""}
            </option>
          ))}
        </select>
      </div>
      <TextField
        label="reviewer rationale (optional)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <label className="cs-inline-form">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />{" "}
        I confirm this closure as the human reviewer
      </label>
      {error && (
        <p role="alert" className="cs-field__error">
          {error}
        </p>
      )}
      <Button
        type="button"
        disabled={closing || !confirmed || needsCandidate}
        onClick={() =>
          close({
            variables: {
              input: {
                taskId,
                closureDecision: decision,
                candidateRevisionId: selectedId
                  ? btoa(`CandidateRevision:${selectedId}`)
                  : undefined,
                packet: note.trim() ? { reviewerNote: note } : undefined,
              },
            },
            onCompleted: (r) => {
              const errs = r.taskClose.errors;
              if (errs && errs.length > 0) {
                setError(errs.map((e) => `${e.code}: ${e.message}`).join("; "));
                return;
              }
              onClosed();
            },
            onError: (e) => setError(e.message),
          })
        }
      >
        close task
      </Button>
    </section>
  );
}

function CloseoutBody({
  taskId,
  workflowState,
}: {
  taskId: string;
  workflowState: string;
}) {
  const [fetchKey, setFetchKey] = useState(0);
  const data = useLazyLoadQuery<tasksCloseoutEvaluationQuery>(
    TaskEvaluationQuery,
    { taskId },
    { fetchPolicy: "network-only", fetchKey },
  );
  const report = (data.taskEvaluation ?? {}) as Json;
  const reassessment = (data.taskReassessmentStatus ?? {}) as Json;
  const candidates = (report.candidates ?? []) as CandidateReport[];
  const [selectedCandidateId, setSelectedCandidateId] = useState<
    string | null
  >(candidates.length === 1 ? (candidates[0].candidateRevisionId ?? null) : null);
  const selectedCandidate = candidates.find(
    (c) => c.candidateRevisionId === selectedCandidateId,
  );
  const eligible =
    candidates.length > 1
      ? selectedCandidate?.supportedSuccessEligible === true
      : report.supportedSuccessEligible === true;
  const [transition, transitioning] =
    useMutation<tasksCloseoutTransitionMutation>(TaskTransitionMutation);
  const [error, setError] = useState<string | null>(null);

  return (
    <div>
      <EvaluationReport
        report={report}
        reassessment={reassessment}
        candidates={candidates}
        selectedId={selectedCandidateId}
        onSelectCandidate={setSelectedCandidateId}
      />
      {error && (
        <p role="alert" className="cs-field__error">
          {error}
        </p>
      )}
      {workflowState === "awaiting_review" && (
        <CloseForm
          taskId={taskId}
          eligible={eligible}
          candidates={candidates}
          selectedId={selectedCandidateId}
          onSelectCandidate={setSelectedCandidateId}
          onClosed={() => setFetchKey((k) => k + 1)}
        />
      )}
      {workflowState !== "awaiting_review" && workflowState !== "closed" && (
        <p data-field="close-hint">
          the task must be in <code>awaiting_review</code> before a reviewer
          can close it.{" "}
          <Button
            type="button"
            disabled={transitioning}
            onClick={() =>
              transition({
                variables: {
                  input: { taskId, toState: "awaiting_review" },
                },
                onCompleted: (r) => {
                  const errs = r.taskTransition.errors;
                  if (errs && errs.length > 0) {
                    setError(
                      errs.map((e) => `${e.code}: ${e.message}`).join("; "),
                    );
                  }
                },
                onError: (e) => setError(e.message),
              })
            }
          >
            send to review
          </Button>
        </p>
      )}
      {workflowState === "closed" && (
        <p data-field="closed-note">
          task is closed — the signed packet is immutable; reopening starts a
          new evaluation cycle.
        </p>
      )}
    </div>
  );
}

/** Task closeout (§12.3): per-metric evaluation report, hard-gate
 * verdicts, and the human-only closure action. The evaluator suggests;
 * the reviewer decides. */
export function CloseoutPanel({
  taskId,
  workflowState,
}: {
  taskId: string;
  workflowState: string;
}) {
  return (
    <Suspense fallback={<LoadingState label="evaluating…" />}>
      <CloseoutBody taskId={taskId} workflowState={workflowState} />
    </Suspense>
  );
}
