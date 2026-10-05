import { Suspense } from "react";
import { useLazyLoadQuery } from "react-relay";

import { Badge } from "../../../components/atoms/Badge";
import { EmptyState, LoadingState } from "../../../components/states/states";
import { TaskReportQuery } from "./operations";

import type { tasksReportQuery } from "../../../__generated__/tasksReportQuery.graphql";

type Json = Record<string, unknown>;
type Finding = { kind?: string; text?: string; action?: string };

const VERDICT_TONE: Record<
  string,
  "success" | "danger" | "warning" | "neutral" | "info"
> = {
  met: "success",
  pass: "success",
  misses: "danger",
  fail: "danger",
  supported_success: "success",
  supported_failure: "danger",
  inconclusive: "warning",
  not_evaluated: "warning",
  accepted: "success",
  accepted_for_research: "success",
  rejected: "danger",
  superseded: "warning",
  proposed: "info",
  submitted: "info",
};

function ReportBody({ taskId }: { taskId: string }) {
  const data = useLazyLoadQuery<tasksReportQuery>(
    TaskReportQuery,
    { taskId },
    { fetchPolicy: "network-only" },
  );
  const r = (data.taskReport ?? {}) as Json;
  const task = (r.task ?? {}) as Json;
  const contract = (r.contract ?? null) as Json | null;
  const evaluation = (r.evaluation ?? {}) as Json;
  const hypotheses = (r.hypotheses ?? []) as Json[];
  const measurements = (r.measurements ?? {}) as Json;
  const measurementRows = (measurements.rows ?? []) as Json[];
  const byStatus = (measurements.byStatus ?? {}) as Json;
  const contradictions = (r.contradictions ?? []) as Json[];
  const unknowns = (r.unknowns ?? []) as string[];
  const reviewScope = (r.reviewScope ?? {}) as Json;
  const limitations = (r.limitations ?? []) as string[];
  const metrics = (evaluation.metrics ?? []) as Json[];
  const gates = (evaluation.gates ?? []) as Json[];

  return (
    <div data-field="task-report">
      <p>
        <Badge tone="info">mode: {String(task.mode ?? "?")}</Badge>{" "}
        <Badge tone="neutral">{String(task.workflowState ?? "?")}</Badge>{" "}
        {task.closureDecision != null && (
          <Badge tone={VERDICT_TONE[String(task.closureDecision)] ?? "neutral"}>
            {String(task.closureDecision)}
          </Badge>
        )}{" "}
        <Badge tone="neutral">cycle {String(task.evaluationCycle ?? "?")}</Badge>
      </p>

      {contract != null && (
        <p data-field="report-contract">
          contract revision {String(contract.revision)} (
          {String(contract.status)}) — {String(contract.metricCount)} metric(s),{" "}
          {String(contract.gateCount)} hard gate(s)
        </p>
      )}

      <p data-field="report-suggestion">
        evaluator suggestion:{" "}
        <Badge
          tone={
            VERDICT_TONE[String(evaluation.suggestedDecision)] ?? "neutral"
          }
        >
          {String(evaluation.suggestedDecision ?? "?")}
        </Badge>
      </p>

      {metrics.length > 0 && (
        <table data-field="report-metrics">
          <caption>metrics vs contract</caption>
          <thead>
            <tr>
              <th>metric</th>
              <th>verdict</th>
              <th>compared against</th>
              <th>evidence</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((m, i) => {
              const mf = (m.findings ?? []) as Finding[];
              return (
                <tr key={i} data-verdict={String(m.verdict)}>
                  <td>
                    {String(m.label ?? m.metricId ?? "?")}
                    {m.required === false ? " (optional)" : ""}
                    {mf.length > 0 && (
                      <ul>
                        {mf.map((f, j) => (
                          <li key={j} data-finding-kind={f.kind}>
                            {f.text}
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                  <td data-field="report-metric-verdict">
                    <Badge
                      tone={VERDICT_TONE[String(m.verdict)] ?? "neutral"}
                    >
                      {String(m.verdict ?? "?")}
                    </Badge>
                  </td>
                  <td>{String(m.comparedAgainst ?? "—")}</td>
                  <td>{(m.evidenceIds as string[] | undefined)?.length ?? 0}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {gates.length > 0 && (
        <ul data-field="report-gates" aria-label="hard gates">
          {gates.map((g, i) => (
            <li key={i} data-verdict={String(g.verdict)}>
              {String(g.text ?? g.id ?? "?")} —{" "}
              <Badge tone={VERDICT_TONE[String(g.verdict)] ?? "neutral"}>
                {String(g.verdict ?? "?")}
              </Badge>
            </li>
          ))}
        </ul>
      )}

      <section aria-label="hypotheses" data-field="report-hypotheses">
        <h4>hypotheses ({hypotheses.length})</h4>
        {hypotheses.length === 0 ? (
          <EmptyState title="no candidate revisions yet" />
        ) : (
          <ul>
            {hypotheses.map((h) => (
              <li key={String(h.id)} data-status={String(h.status)}>
                rev {String(h.revision)} — {String(h.hypothesis ?? "—")}{" "}
                <Badge tone={VERDICT_TONE[String(h.status)] ?? "neutral"}>
                  {String(h.status)}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="measurements" data-field="report-measurements">
        <h4>
          measurements ({measurementRows.length}) —{" "}
          {String(measurements.acceptedCount ?? 0)} accepted,{" "}
          {String(measurements.attributedCount ?? 0)} metric-attributed
        </h4>
        {measurementRows.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>method</th>
                <th>metric</th>
                <th>status</th>
                <th>repeat</th>
              </tr>
            </thead>
            <tbody>
              {measurementRows.map((m) => (
                <tr key={String(m.id)} data-status={String(m.status)}>
                  <td>{String(m.method)}</td>
                  <td>{m.metric != null ? String(m.metric) : "unattributed"}</td>
                  <td>
                    <Badge tone={VERDICT_TONE[String(m.status)] ?? "neutral"}>
                      {String(m.status)}
                    </Badge>
                    {m.applicable === false && (
                      <>
                        {" "}
                        <Badge tone="warning">not applicable</Badge>
                      </>
                    )}
                  </td>
                  <td>{String(m.repeatType)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {Object.keys(byStatus).length > 0 && (
          <p className="cs-hint">by status: {JSON.stringify(byStatus)}</p>
        )}
      </section>

      {contradictions.length > 0 && (
        <section aria-label="contradictions" data-field="report-contradictions">
          <h4>contradictions ({contradictions.length})</h4>
          <p className="cs-hint">
            contradicting claims stay visible — nothing is hidden or demoted.
          </p>
          {contradictions.map((c) => (
            <div key={String(c.linkId)} data-field="contradiction">
              {(c.claims as Json[]).map((claim) => (
                <blockquote key={String(claim.id)}>
                  <Badge tone={VERDICT_TONE[String(claim.status)] ?? "neutral"}>
                    {String(claim.status)}
                  </Badge>{" "}
                  {JSON.stringify(claim.statement)}
                </blockquote>
              ))}
            </div>
          ))}
        </section>
      )}

      <section aria-label="unknowns" data-field="report-unknowns">
        <h4>unknowns ({unknowns.length})</h4>
        {unknowns.length > 0 && (
          <ul>
            {unknowns.map((u, i) => (
              <li key={i}>{u}</li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="review scope" data-field="report-review-scope">
        <h4>review scope</h4>
        <dl>
          <dt>decisions recorded</dt>
          <dd>{String(reviewScope.decisionCount ?? 0)}</dd>
          <dt>closure recorded</dt>
          <dd>{reviewScope.closureRecorded === true ? "yes" : "no"}</dd>
          <dt>human-reviewed measurements</dt>
          <dd>{String(reviewScope.humanReviewedMeasurements ?? 0)}</dd>
          <dt>pending review</dt>
          <dd>{String(reviewScope.pendingReviewMeasurements ?? 0)}</dd>
        </dl>
      </section>

      <section aria-label="limitations" data-field="report-limitations">
        <h4>limitations</h4>
        <ul>
          {limitations.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}

/** Task report (§25, CS-0504): hypotheses, measurements,
 * contradictions, unknowns, review scope and evaluator output — a
 * review aid, never a scientific-validation claim. */
export function TaskReportPanel({ taskId }: { taskId: string }) {
  return (
    <Suspense fallback={<LoadingState label="compiling report…" />}>
      <ReportBody taskId={taskId} />
    </Suspense>
  );
}
