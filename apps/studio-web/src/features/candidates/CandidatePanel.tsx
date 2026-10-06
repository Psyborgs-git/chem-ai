import { Suspense, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../components/atoms/Badge";
import { Button } from "../../components/atoms/Button";
import { TextField } from "../../components/atoms/TextField";
import { EmptyState, LoadingState } from "../../components/states/states";
import { CandidateCreateMutation, TaskCandidatesQuery } from "./operations";

import type { candidatesCreateMutation } from "../../__generated__/candidatesCreateMutation.graphql";
import type { candidatesTaskCandidatesQuery } from "../../__generated__/candidatesTaskCandidatesQuery.graphql";

type CandidateNode = NonNullable<
  candidatesTaskCandidatesQuery["response"]["taskCandidateRevisions"]["edges"][number]["node"]
>;

/** Canonical revision identity: the Relay GlobalID is the canonical
 * ID (§8.2); show it plus the revision number so old/new revisions
 * are visibly distinct records (AT-0206-3). */
function CandidateRevisionRow({
  cand,
  onDiff,
}: {
  cand: CandidateNode;
  onDiff: (c: CandidateNode) => void;
}) {
  return (
    <li className="cs-candidate" data-canonical-id={cand.id}>
      <code className="cs-candidate__id">{cand.id}</code>
      <span className="cs-candidate__rev">rev {cand.revision}</span>
      <Badge tone={cand.status === "accepted_for_research" ? "success" : "neutral"}>
        {cand.status}
      </Badge>
      <Badge tone="info">eligibility: {cand.eligibility}</Badge>
      <span className="cs-candidate__kind">{cand.entityKind}</span>
      {cand.parentRevisionId && (
        <span className="cs-candidate__parent">
          child of <code>{cand.parentRevisionId}</code>
        </span>
      )}
      <button type="button" onClick={() => onDiff(cand)}>
        view content
      </button>
    </li>
  );
}

/** Revision content + lineage view: old and new revisions render
 * side-by-side under their own canonical IDs. */
function nodeId(gid: string): string {
  try {
    return atob(gid).split(":").pop() ?? gid;
  } catch {
    return gid;
  }
}

function RevisionDiff({ cand, all }: { cand: CandidateNode; all: CandidateNode[] }) {
  const parent = cand.parentRevisionId
    ? all.find((c) => nodeId(c.id) === cand.parentRevisionId)
    : undefined;
  return (
    <div className="cs-diff" role="group" aria-label="revision comparison">
      <div>
        <h4>this revision</h4>
        <p>
          <code>{cand.id}</code> — rev {cand.revision} ({cand.status})
        </p>
        <pre aria-label="content">{JSON.stringify(cand.payload, null, 2)}</pre>
      </div>
      {parent && (
        <div>
          <h4>parent revision</h4>
          <p>
            <code>{parent.id}</code> — rev {parent.revision} ({parent.status})
          </p>
          <pre aria-label="parent content">{JSON.stringify(parent.payload, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

function CandidateList({
  taskId,
  fetchKey,
}: {
  taskId: string;
  fetchKey: number;
}) {
  // fetchKey + network-only forces a real refetch on propose — a
  // remount alone replays the cached query result (CS-1201).
  const data = useLazyLoadQuery<candidatesTaskCandidatesQuery>(
    TaskCandidatesQuery,
    { taskId },
    { fetchKey, fetchPolicy: "network-only" },
  );
  const [diff, setDiff] = useState<CandidateNode | null>(null);
  const all = data.taskCandidateRevisions.edges.map((e) => e.node);
  // history view sorts by revision so the lineage reads in order
  const sorted = [...all].sort((a, b) => a.revision - b.revision);
  if (sorted.length === 0) {
    return <EmptyState title="No candidates proposed yet." />;
  }
  return (
    <div>
      <ul className="cs-candidate-list" aria-label="candidate revisions">
        {sorted.map((c) => (
          <CandidateRevisionRow key={c.id} cand={c} onDiff={setDiff} />
        ))}
      </ul>
      {diff && <RevisionDiff cand={diff} all={all} />}
    </div>
  );
}

function ProposeForm({
  taskId,
  onProposed,
}: {
  taskId: string;
  onProposed: () => void;
}) {
  const [commit] = useMutation<candidatesCreateMutation>(CandidateCreateMutation);
  const [hypothesis, setHypothesis] = useState("");
  const [kind, setKind] = useState("formulation");
  const [feedback, setFeedback] = useState<string | null>(null);

  return (
    <form
      aria-label="propose candidate"
      onSubmit={(e) => {
        e.preventDefault();
        setFeedback(null);
        commit({
          variables: {
            input: {
              taskId,
              entityKind: kind,
              hypothesis: hypothesis || undefined,
            },
          },
          onCompleted: (resp) => {
            const errs = resp.candidates.create.errors;
            setFeedback(
              errs.length ? `not proposed: ${errs[0].message}` : "proposed as draft",
            );
            if (!errs.length) onProposed();
          },
          onError: (e) => setFeedback(`not proposed: ${e.message}`),
        });
      }}
    >
      <TextField
        label="hypothesis"
        value={hypothesis}
        onChange={(e) => setHypothesis(e.target.value)}
      />
      <div className="cs-field">
        <label htmlFor="entity-kind" className="cs-field__label">
          entity kind
        </label>
        <select
          id="entity-kind"
          className="cs-select"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="formulation">formulation</option>
          <option value="material">material</option>
          <option value="molecule">molecule</option>
        </select>
      </div>
      <Button type="submit">Propose candidate (creates a draft revision)</Button>
      {feedback && <p role="status">{feedback}</p>}
    </form>
  );
}

export function CandidatePanel({ taskId }: { taskId: string }) {
  const [fetchKey, setFetchKey] = useState(0);
  return (
    <div>
      <ProposeForm
        taskId={taskId}
        onProposed={() => setFetchKey((k) => k + 1)}
      />
      <Suspense fallback={<LoadingState label="loading candidates…" />}>
        <CandidateList taskId={taskId} fetchKey={fetchKey} />
      </Suspense>
    </div>
  );
}
