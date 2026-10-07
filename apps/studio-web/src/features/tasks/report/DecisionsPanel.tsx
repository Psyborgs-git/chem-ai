import { Suspense } from "react";
import { useLazyLoadQuery } from "react-relay";

import { Badge } from "../../../components/atoms/Badge";
import { EmptyState, LoadingState } from "../../../components/states/states";
import { TaskDecisionsQuery } from "./operations";

import type { tasksDecisionsQuery } from "../../../__generated__/tasksDecisionsQuery.graphql";

import {
  provenanceSummary,
  type ProvenanceBlock,
} from "../provenance";

type Json = Record<string, unknown>;

const KIND_TONE: Record<string, "success" | "danger" | "warning" | "neutral" | "info"> = {
  closure: "success",
  reopen: "warning",
  review_return: "info",
  state_change: "neutral",
};

function DecisionsBody({ taskId }: { taskId: string }) {
  const data = useLazyLoadQuery<tasksDecisionsQuery>(
    TaskDecisionsQuery,
    { taskId },
    { fetchPolicy: "network-only" },
  );
  const edges = data.taskDecisions.edges;
  if (edges.length === 0) {
    return <EmptyState title="no decisions recorded yet" />;
  }
  return (
    <ol data-field="decision-log">
      {edges.map(({ node }) => {
        const payload = (node.payload ?? {}) as Json;
        const packet = (payload.packet ?? null) as Json | null;
        return (
          <li key={node.id} data-field="decision" data-kind={node.kind}>
            <p>
              <Badge tone={KIND_TONE[node.kind] ?? "neutral"}>{node.kind}</Badge>{" "}
              {node.decidedBy != null && (
                <>
                  by {node.decidedBy.displayName} ({node.decidedBy.kind}){" "}
                </>
              )}
              <span className="cs-hint">{node.createdAt}</span>
            </p>
            <dl>
              {payload.closureDecision != null && (
                <>
                  <dt>closure decision</dt>
                  <dd data-field="decision-closure">
                    {String(payload.closureDecision)}
                  </dd>
                </>
              )}
              {payload.contractRevisionId != null && (
                <>
                  <dt>bound contract revision</dt>
                  <dd data-field="decision-contract">
                    <code>{String(payload.contractRevisionId)}</code>
                  </dd>
                </>
              )}
              {payload.evaluationCycle != null && (
                <>
                  <dt>evaluation cycle</dt>
                  <dd>{String(payload.evaluationCycle)}</dd>
                </>
              )}
              {payload.reason != null && (
                <>
                  <dt>reason</dt>
                  <dd>{String(payload.reason)}</dd>
                </>
              )}
            </dl>
            {packet != null && (
              <details data-field="decision-packet">
                <summary>signed closure packet</summary>
                <dl>
                  {packet.candidateRevisionId != null && (
                    <>
                      <dt>candidate revision</dt>
                      <dd>
                        <code>{String(packet.candidateRevisionId)}</code>
                      </dd>
                    </>
                  )}
                  <dt>evidence ids</dt>
                  <dd data-field="packet-evidence">
                    {JSON.stringify(packet.evidenceIds ?? [])}
                  </dd>
                  <dt>status</dt>
                  <dd>
                    fixture-only: {String(packet.fixtureOnly)}; scientific
                    validation: {String(packet.scientificValidation)}
                  </dd>
                  {packet.provenance != null && (
                    <>
                      <dt>provenance</dt>
                      <dd data-field="packet-provenance">
                        {
                          provenanceSummary(
                            packet.provenance as ProvenanceBlock,
                            packet.fixtureOnly !== false,
                          ).text
                        }
                      </dd>
                    </>
                  )}
                </dl>
              </details>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** Immutable decision log (§7.1): closures keep the packet they were
 * signed under — a later contract revision never rewrites them. */
export function DecisionsPanel({ taskId }: { taskId: string }) {
  return (
    <Suspense fallback={<LoadingState label="loading decisions…" />}>
      <DecisionsBody taskId={taskId} />
    </Suspense>
  );
}
