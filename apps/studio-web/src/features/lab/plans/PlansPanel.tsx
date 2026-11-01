import { useRef, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../../components/atoms/Badge";
import { Button } from "../../../components/atoms/Button";
import { TextField } from "../../../components/atoms/TextField";
import { EmptyState } from "../../../components/states/states";
import { ChemistryArt } from "../../../components/layout/ChemistryArt";
import { Link } from "react-router";
import { rawUuid } from "../../../relay/network";
import {
  CandidateRevisionPicker,
  ContractRevisionPicker,
  type Picked,
} from "../../registry/pickers";
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
import "../lab-workflow.css";

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

function PlanCard({
  plan,
  onChanged,
  candidateLabel,
  contractLabel,
}: {
  plan: PlanNode;
  onChanged: () => void;
  candidateLabel: string;
  contractLabel: string;
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
      <dl className="cs-lab-plan-summary">
        <div><dt>Test method</dt><dd>{String(payload.method || "Not specified")}</dd></div>
        <div><dt>Candidate</dt><dd>{candidateLabel}</dd></div>
        <div><dt>Success criteria</dt><dd>{contractLabel}</dd></div>
      </dl>
      <details className="cs-technical"><summary>Plan record details</summary><dl>
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
      </dl></details>
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

/** Structured plan form (§14.1, PAR-07): bound revisions are picked by
 * name — candidate revision, contract revision, optional process
 * revision — never a uuid typed by hand. */
export function PlanCreateForm({
  taskId,
  onCreated,
}: {
  taskId: string;
  onCreated: () => void;
}) {
  const [commit, pending] =
    useMutation<labPlansPlanCreateMutation>(PlanCreateMutation);
  const submitting = useRef(false);
  const [title, setTitle] = useState("");
  const [candidate, setCandidate] = useState<Picked | null>(null);
  const [contract, setContract] = useState<Picked | null>(null);
  const [method, setMethod] = useState("");
  const [batches, setBatches] = useState("1");
  const [acceptanceCriteria, setAcceptanceCriteria] = useState("");
  const [hazardNotes, setHazardNotes] = useState("");
  const [resourceNeeds, setResourceNeeds] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = () => {
    if (pending || submitting.current || !method.trim()) return;
    submitting.current = true;
    setError(null);
    const batchCount = Math.max(1, Number.parseInt(batches, 10) || 1);
    const payload = {
      ...(candidate ? { candidateRevisionId: candidate.uuid } : {}),
      ...(contract ? { contractRevisionId: contract.uuid } : {}),
      method,
      samplePlan: Array.from({ length: batchCount }, (_, i) => ({
        batch: String.fromCharCode(65 + i),
        aliquots: 2,
      })),
      ...(acceptanceCriteria ? { acceptanceCriteria } : {}),
      ...(hazardNotes ? { hazardNotes } : {}),
      ...(resourceNeeds ? { resourceNeeds } : {}),
    };
    commit({
      variables: { input: { taskId, title: title.trim() || `${Array.from(method.trim()).slice(0, 289).join("")} experiment`, payload } },
      onCompleted: (res) => {
        submitting.current = false;
        const errs = res.lab?.planCreate.errors;
        if (errs && errs.length > 0) {
          setError(errs.map((e) => `${e.code}: ${e.message}`).join("; "));
        } else {
          setTitle("");
          setMethod("");
          setAcceptanceCriteria("");
          setHazardNotes("");
          setResourceNeeds("");
          onCreated();
        }
      },
      onError: (e) => { submitting.current = false; setError(e.message); },
    });
  };

  return (
    <section aria-label="new experiment plan">
      <header className="cs-lab-step-heading"><div><p className="cs-eyebrow">Plan an experiment</p><h3>How will you test this candidate?</h3><p>Choose what you are testing, then describe the method. The plan stays a draft until a person reviews it.</p></div><ChemistryArt kind="experiment" /></header>
      <div className="cs-plan-bindings">
        <div className="cs-lab-binding">
          {candidate && <div className="cs-lab-binding__summary"><span>Candidate to test</span><strong>{candidate.label}</strong><Button variant="ghost" onClick={() => setCandidate(null)}>Change candidate</Button></div>}
          <div hidden={candidate !== null}>
        <CandidateRevisionPicker
          taskId={taskId}
          label="Candidate to test"
          selectedId={candidate?.uuid ?? null}
          onClear={() => setCandidate(null)}
          onPick={setCandidate}
          autoSelectSingle
        />
          </div>
        </div>
        <div className="cs-lab-binding">
          {contract && <div className="cs-lab-binding__summary"><span>Agreed success criteria</span><strong>{contract.label}</strong><Button variant="ghost" onClick={() => setContract(null)}>Change success criteria</Button></div>}
          <div hidden={contract !== null}>
        <ContractRevisionPicker
          taskId={taskId}
          label="Agreed success criteria"
          selectedId={contract?.uuid ?? null}
          onClear={() => setContract(null)}
          onPick={setContract}
          autoSelectSingle
        />
          </div>
        </div>
      </div>
      {(!candidate || !contract) && <p className="cs-field__hint">{!candidate && !contract ? "No candidate or success criteria selected." : !candidate ? "No candidate selected." : "No success criteria selected."} You can save a draft now, <Link to={`/tasks/${encodeURIComponent(taskId)}/candidates`}>review candidates</Link> or <Link to={`/tasks/${encodeURIComponent(taskId)}/overview`}>define the success criteria</Link>. Unresolved review blockers must be addressed before approval.</p>}
      <TextField
        label="Test method"
        hint="Describe the test a qualified operator will carry out."
        value={method}
        onChange={(e) => setMethod(e.target.value)}
      />
      <details className="cs-lab-plan-options"><summary>Name, samples and notes</summary>
      <TextField label="plan title (optional)" hint="Leave blank to name this plan after its method." value={title} onChange={(e) => setTitle(e.target.value)} />
      <TextField
        label="batch count"
        inputMode="numeric"
        value={batches}
        onChange={(e) => setBatches(e.target.value)}
      />
      <TextField
        label="acceptance criteria (optional)"
        value={acceptanceCriteria}
        onChange={(e) => setAcceptanceCriteria(e.target.value)}
      />
      <TextField
        label="hazard notes (optional)"
        value={hazardNotes}
        onChange={(e) => setHazardNotes(e.target.value)}
      />
      <TextField
        label="resource needs (optional)"
        value={resourceNeeds}
        onChange={(e) => setResourceNeeds(e.target.value)}
      />
      </details>
      {error && (
        <p role="alert" className="cs-field__error">
          {error}
        </p>
      )}
      <Button
        type="button"
        disabled={pending || !method.trim()}
        onClick={create}
      >
        Save draft plan
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
  const candidates = (data.taskCandidateRevisions?.edges ?? []).map((edge) => edge.node);
  const contracts = (data.taskContractRevisions?.edges ?? []).map((edge) => edge.node);

  return (
    <section aria-label="experiment plans">
      <h2>Experiment plans</h2>
      {plans.length === 0 ? (
        <EmptyState title="no plans yet — create one below." />
      ) : (
        <ul aria-label="plans">
          {plans.map((p) => (
            <PlanCard key={p.id} plan={p} onChanged={bump}
              candidateLabel={(() => { const match = candidates.find((candidate) => rawUuid(candidate.id) === String((p.payload as Payload | null)?.candidateRevisionId)); return match ? `${match.hypothesis || match.entityKind} · revision ${match.revision}` : "No candidate selected"; })()}
              contractLabel={(() => { const match = contracts.find((contract) => rawUuid(contract.id) === String((p.payload as Payload | null)?.contractRevisionId)); return match ? `Agreed criteria · revision ${match.revision}` : "No success criteria selected"; })()} />
          ))}
        </ul>
      )}
      <PlanCreateForm taskId={taskId} onCreated={bump} />
    </section>
  );
}
