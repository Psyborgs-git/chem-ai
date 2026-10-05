import { useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../../components/atoms/Badge";
import { Button } from "../../../components/atoms/Button";
import { TextField } from "../../../components/atoms/TextField";
import { EmptyState } from "../../../components/states/states";
import {
  PacketExportMutation,
  PlanCreateMutation,
  PlanReviewMutation,
  PlanSubmitMutation,
  TaskPlansQuery,
} from "./operations";

import type { labPlansPacketExportMutation } from "../../../__generated__/labPlansPacketExportMutation.graphql";
import type { labPlansPlanCreateMutation } from "../../../__generated__/labPlansPlanCreateMutation.graphql";
import type { labPlansPlanReviewMutation } from "../../../__generated__/labPlansPlanReviewMutation.graphql";
import type { labPlansPlanSubmitMutation } from "../../../__generated__/labPlansPlanSubmitMutation.graphql";
import type { labPlansTaskPlansQuery } from "../../../__generated__/labPlansTaskPlansQuery.graphql";

type PlanNode = NonNullable<
  labPlansTaskPlansQuery["response"]["taskPlans"]["edges"][number]["node"]
>;
type Blocker = { kind?: string; text?: string };
type Payload = Record<string, unknown>;
type Errs = readonly { code: string; message: string }[];

const STATUS_TONE: Record<
  string,
  "info" | "success" | "warning" | "danger" | "neutral"
> = {
  draft: "neutral",
  submitted: "warning",
  approved: "success",
  rejected: "danger",
};

const MANUAL_LABEL =
  "MANUAL EXECUTION — qualified operator required; the system does not start equipment";

const PAYLOAD_TEMPLATE = JSON.stringify(
  {
    candidateRevisionId: "",
    contractRevisionId: "",
    processRevisionId: "",
    method: "",
    samplePlan: [{ batch: "A", aliquots: 2 }],
    acceptanceCriteria: "",
    hazardNotes: "",
    resourceNeeds: "",
  },
  null,
  2,
);

function PlanCard({
  plan,
  onChanged,
}: {
  plan: PlanNode;
  onChanged: () => void;
}) {
  const [submit, submitting] =
    useMutation<labPlansPlanSubmitMutation>(PlanSubmitMutation);
  const [review, reviewing] =
    useMutation<labPlansPlanReviewMutation>(PlanReviewMutation);
  const [exportPacket, exporting] =
    useMutation<labPlansPacketExportMutation>(PacketExportMutation);
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState<string | null>(null);

  const payload = (plan.payload ?? {}) as Payload;
  const blockers = (plan.blockers ?? []) as Blocker[];
  const packet = plan.packet as Payload | null;
  const pending = submitting || reviewing || exporting;
  const showErrs = (errs: Errs | null | undefined) => {
    if (errs && errs.length > 0) {
      setError(errs.map((e) => `${e.code}: ${e.message}`).join("; "));
      return true;
    }
    return false;
  };
  const doSubmit = () => {
    setError(null);
    submit({
      variables: { input: { planId: plan.id } },
      onCompleted: (res) => {
        if (!showErrs(res.lab?.planSubmit.errors)) onChanged();
      },
      onError: (e) => setError(e.message),
    });
  };
  const doReview = (decision: "approved" | "rejected") => {
    setError(null);
    review({
      variables: {
        input: {
          planId: plan.id,
          decision,
          rationale: rationale || undefined,
        },
      },
      onCompleted: (res) => {
        if (!showErrs(res.lab?.planReview.errors)) onChanged();
      },
      onError: (e) => setError(e.message),
    });
  };
  const doExport = () => {
    setError(null);
    exportPacket({
      variables: { input: { planId: plan.id } },
      onCompleted: (res) => {
        if (!showErrs(res.lab?.packetExport.errors)) onChanged();
      },
      onError: (e) => setError(e.message),
    });
  };

  return (
    <li className="cs-plan" data-plan-id={plan.id} data-status={plan.status}>
      <p>
        <strong>{plan.title}</strong>{" "}
        <Badge tone={STATUS_TONE[plan.status] ?? "neutral"}>{plan.status}</Badge>
      </p>
      <dl>
        <dt>content digest</dt>
        <dd>
          <code>{plan.contentDigest.slice(0, 16)}…</code>
        </dd>
        <dt>candidate revision</dt>
        <dd data-field="candidate-revision">
          <code>{String(payload.candidateRevisionId ?? "—")}</code>
        </dd>
        <dt>contract revision</dt>
        <dd data-field="contract-revision">
          <code>{String(payload.contractRevisionId ?? "—")}</code>
        </dd>
        <dt>process revision</dt>
        <dd data-field="process-revision">
          <code>{String(payload.processRevisionId ?? "—")}</code>
        </dd>
        <dt>method</dt>
        <dd data-field="method">{String(payload.method ?? "—")}</dd>
      </dl>
      {blockers.length > 0 && (
        <ul aria-label="blockers" className="cs-plan__blockers">
          {blockers.map((b, i) => (
            <li key={i} data-blocker-kind={b.kind}>
              <Badge tone="danger">blocker</Badge> {b.text}
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p role="alert" className="cs-plan__error">
          {error}
        </p>
      )}
      {plan.status === "draft" && (
        <Button type="button" disabled={pending} onClick={doSubmit}>
          submit for review
        </Button>
      )}
      {plan.status === "submitted" && (
        <div>
          <TextField
            label="review rationale"
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
          />
          <Button
            type="button"
            disabled={pending}
            onClick={() => doReview("approved")}
          >
            approve
          </Button>{" "}
          <Button
            type="button"
            disabled={pending}
            onClick={() => doReview("rejected")}
          >
            reject
          </Button>
        </div>
      )}
      {plan.status === "approved" && (
        <Button type="button" disabled={pending} onClick={doExport}>
          export manual packet
        </Button>
      )}
      {packet != null && (
        <section aria-label="execution packet" className="cs-packet">
          <p>
            <Badge tone="warning">{MANUAL_LABEL}</Badge>
          </p>
          <dl>
            <dt>approval</dt>
            <dd data-field="packet-approval">
              <code>
                {String((packet.approval as Payload | undefined)?.id ?? "—")}
              </code>
            </dd>
            <dt>execution mode</dt>
            <dd data-field="packet-mode">
              {String(packet.executionMode ?? "—")}
            </dd>
          </dl>
          <details>
            <summary>packet contents</summary>
            <pre data-field="packet-json">{JSON.stringify(packet, null, 2)}</pre>
          </details>
        </section>
      )}
    </li>
  );
}

function PlanCreateForm({
  taskId,
  onCreated,
}: {
  taskId: string;
  onCreated: () => void;
}) {
  const [commit, pending] =
    useMutation<labPlansPlanCreateMutation>(PlanCreateMutation);
  const [title, setTitle] = useState("");
  const [payloadText, setPayloadText] = useState(PAYLOAD_TEMPLATE);
  const [error, setError] = useState<string | null>(null);

  const create = () => {
    setError(null);
    let payload: unknown;
    try {
      payload = JSON.parse(payloadText);
    } catch {
      setError("payload is not valid JSON");
      return;
    }
    commit({
      variables: { input: { taskId, title, payload } },
      onCompleted: (res) => {
        const errs = res.lab?.planCreate.errors;
        if (errs && errs.length > 0) {
          setError(errs.map((e) => `${e.code}: ${e.message}`).join("; "));
        } else {
          setTitle("");
          onCreated();
        }
      },
      onError: (e) => setError(e.message),
    });
  };

  return (
    <section aria-label="new experiment plan">
      <h3>new experiment plan</h3>
      <TextField
        label="plan title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <div className="cs-field">
        <label className="cs-field__label" htmlFor="plan-payload">
          plan payload (JSON — bound revision ids, method, sample plan,
          acceptance criteria, hazard notes, resource needs)
        </label>
        <textarea
          id="plan-payload"
          rows={10}
          value={payloadText}
          onChange={(e) => setPayloadText(e.target.value)}
          className="cs-input"
        />
      </div>
      {error && (
        <p role="alert" className="cs-field__error">
          {error}
        </p>
      )}
      <Button
        type="button"
        disabled={pending || !title.trim()}
        onClick={create}
      >
        create plan
      </Button>
    </section>
  );
}

/** Experiment plans for a task (§14.1, CS-0501): draft → review →
 * approval-bound manual packet. Editing an approved plan makes the
 * release approval stale — packet export re-verifies the digest
 * server-side. No equipment execution exists or is implied. */
export function PlansPanel({ taskId }: { taskId: string }) {
  const [fetchKey, setFetchKey] = useState(0);
  const data = useLazyLoadQuery<labPlansTaskPlansQuery>(
    TaskPlansQuery,
    { taskId },
    { fetchKey, fetchPolicy: "network-only" },
  );
  const bump = () => setFetchKey((k) => k + 1);
  const plans = data.taskPlans.edges.map((e) => e.node).filter((n) => n != null);

  return (
    <section aria-label="experiment plans">
      <h2>experiment plans</h2>
      {plans.length === 0 ? (
        <EmptyState title="no plans yet — create one below." />
      ) : (
        <ul aria-label="plans">
          {plans.map((p) => (
            <PlanCard key={p.id} plan={p} onChanged={bump} />
          ))}
        </ul>
      )}
      <PlanCreateForm taskId={taskId} onCreated={bump} />
    </section>
  );
}
