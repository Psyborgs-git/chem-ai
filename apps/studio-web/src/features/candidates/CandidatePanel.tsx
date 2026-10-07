import { Suspense, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";
import { Link } from "react-router";

import { Badge } from "../../components/atoms/Badge";
import { Button } from "../../components/atoms/Button";
import { TextField } from "../../components/atoms/TextField";
import { InlineFinding } from "../../components/molecules/InlineFinding";
import { EmptyState, LoadingState } from "../../components/states/states";
import {
  FormulationRevisionPicker,
  MaterialIdentityPicker,
} from "../registry/pickers";
import { RevisionDiff } from "../registry/RevisionDiff";
import {
  CandidateCreateMutation,
  CandidateReviewMutation,
  CandidateSubmitMutation,
  TaskCandidatesQuery,
} from "./operations";

import type { candidatesCreateMutation } from "../../__generated__/candidatesCreateMutation.graphql";
import type { candidatesReviewMutation } from "../../__generated__/candidatesReviewMutation.graphql";
import type { candidatesSubmitMutation } from "../../__generated__/candidatesSubmitMutation.graphql";
import type { candidatesTaskCandidatesQuery } from "../../__generated__/candidatesTaskCandidatesQuery.graphql";

type CandidateNode = NonNullable<
  candidatesTaskCandidatesQuery["response"]["taskCandidateRevisions"]["edges"][number]["node"]
>;

type Errs = readonly { code: string; message: string }[];

function DifferencesList({ payload }: { payload: unknown }) {
  const p =
    payload && typeof payload === "object" && !Array.isArray(payload)
      ? (payload as Record<string, unknown>)
      : null;
  const diffs = Array.isArray(p?.proposedDifferences)
    ? (p.proposedDifferences as unknown[])
    : [];
  if (diffs.length === 0) return null;
  return (
    <ul aria-label="proposed differences" className="cs-candidate__differences">
      {diffs.map((d, i) => (
        <li key={i}>{typeof d === "string" ? d : JSON.stringify(d)}</li>
      ))}
    </ul>
  );
}

/** A formulation-bound candidate: its entityRevisionId resolves to a
 * FormulationRevision whose stored parentRevisionId is the baseline —
 * render the real ingredient/process diff (§PAR-07). */
function CandidateDiff({ cand }: { cand: CandidateNode }) {
  const entity = cand.entityRevisionId;
  if (!entity) {
    return <EmptyState title="candidate is not bound to an entity revision" />;
  }
  return <RevisionDiff baselineUuid={null} candidateUuid={entity} />;
}

function nodeId(gid: string): string {
  try {
    return atob(gid).split(":").pop() ?? gid;
  } catch {
    return gid;
  }
}

/** Revision content + lineage view: this revision's payload rendered
 * under its own canonical id beside its parent candidate revision.
 * Raw payload render is intentional — this is the revision-history
 * inspector (AT-0206-3); the structured ingredient diff lives on the
 * entity-bound path above. */
function RevisionContent({
  cand,
  parent,
}: {
  cand: CandidateNode;
  parent: CandidateNode | undefined;
}) {
  return (
    <div className="cs-diff" role="group" aria-label="revision comparison">
      <div>
        <h4>this revision</h4>
        <p>
          <code>{cand.id}</code> — rev {cand.revision} ({cand.status})
        </p>
        <pre aria-label="content">
          {JSON.stringify(cand.payload, null, 2)}
        </pre>
      </div>
      {parent && (
        <div>
          <h4>parent revision</h4>
          <p>
            <code>{parent.id}</code> — rev {parent.revision} ({parent.status})
          </p>
          <pre aria-label="parent content">
            {JSON.stringify(parent.payload, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function CandidateActions({
  cand,
  onChanged,
}: {
  cand: CandidateNode;
  onChanged: () => void;
}) {
  const [submit, submitting] =
    useMutation<candidatesSubmitMutation>(CandidateSubmitMutation);
  const [review, reviewing] =
    useMutation<candidatesReviewMutation>(CandidateReviewMutation);
  const [errors, setErrors] = useState<Errs>([]);
  const pending = submitting || reviewing;
  const showErrs = (errs: Errs | null | undefined) => {
    if (errs && errs.length > 0) {
      setErrors(errs);
      return true;
    }
    return false;
  };
  return (
    <div className="cs-candidate__actions">
      {cand.status === "draft" && (
        <Button
          type="button"
          disabled={pending}
          onClick={() => {
            setErrors([]);
            submit({
              variables: { input: { candidateId: cand.id } },
              onCompleted: (res) => {
                if (!showErrs(res.candidates.submit.errors)) onChanged();
              },
              onError: (e) =>
                setErrors([{ code: "NETWORK", message: e.message }]),
            });
          }}
        >
          submit for review
        </Button>
      )}
      {cand.status === "submitted" && (
        <div>
          <Button
            type="button"
            disabled={pending}
            onClick={() => {
              setErrors([]);
              review({
                variables: {
                  input: {
                    candidateId: cand.id,
                    accept: true,
                  },
                },
                onCompleted: (res) => {
                  if (!showErrs(res.candidates.review.errors)) onChanged();
                },
                onError: (e) =>
                  setErrors([{ code: "NETWORK", message: e.message }]),
              });
            }}
          >
            accept for research
          </Button>{" "}
          <Button
            type="button"
            variant="danger"
            disabled={pending}
            onClick={() => {
              setErrors([]);
              review({
                variables: {
                  input: {
                    candidateId: cand.id,
                    accept: false,
                  },
                },
                onCompleted: (res) => {
                  if (!showErrs(res.candidates.review.errors)) onChanged();
                },
                onError: (e) =>
                  setErrors([{ code: "NETWORK", message: e.message }]),
              });
            }}
          >
            reject
          </Button>
        </div>
      )}
      {cand.status === "accepted_for_research" && (
        <p className="cs-candidate__next">
          accepted — link this exact revision into a manual experiment plan in{" "}
          <Link to="/lab">Lab</Link>
        </p>
      )}
      {errors.map((e) => (
        <InlineFinding
          key={`${e.code}:${e.message}`}
          severity="error"
          message={e.message}
        />
      ))}
    </div>
  );
}

function CandidateRow({
  cand,
  parent,
  onChanged,
}: {
  cand: CandidateNode;
  parent: CandidateNode | undefined;
  onChanged: () => void;
}) {
  const [diffOpen, setDiffOpen] = useState(false);
  const [contentOpen, setContentOpen] = useState(false);
  return (
    <li className="cs-candidate" data-canonical-id={cand.id}>
      <p>
        <code className="cs-candidate__id">{cand.id}</code>{" "}
        <span className="cs-candidate__rev">rev {cand.revision}</span>{" "}
        <Badge
          tone={cand.status === "accepted_for_research" ? "success" : "neutral"}
        >
          {cand.status}
        </Badge>{" "}
        <Badge tone="info">eligibility: {cand.eligibility}</Badge>{" "}
        <span className="cs-candidate__kind">{cand.entityKind}</span>
        {cand.parentRevisionId && (
          <span className="cs-candidate__parent">
            {" "}
            child of <code>{cand.parentRevisionId.slice(0, 8)}…</code>
          </span>
        )}
      </p>
      {cand.hypothesis && <p>hypothesis: {cand.hypothesis}</p>}
      <DifferencesList payload={cand.payload} />
      {cand.entityKind === "formulation" && (
        <button
          type="button"
          onClick={() => setDiffOpen((o) => !o)}
          aria-expanded={diffOpen}
        >
          {diffOpen ? "hide ingredient diff" : "view diff vs baseline"}
        </button>
      )}{" "}
      <button
        type="button"
        onClick={() => setContentOpen((o) => !o)}
        aria-expanded={contentOpen}
      >
        {contentOpen ? "hide content" : "view content"}
      </button>
      {diffOpen && (
        <Suspense fallback={<LoadingState label="loading diff…" />}>
          <CandidateDiff cand={cand} />
        </Suspense>
      )}
      {contentOpen && <RevisionContent cand={cand} parent={parent} />}
      <CandidateActions cand={cand} onChanged={onChanged} />
    </li>
  );
}

function CandidateList({
  taskId,
  fetchKey,
  onChanged,
}: {
  taskId: string;
  fetchKey: number;
  onChanged: () => void;
}) {
  // fetchKey + network-only forces a real refetch on propose — a
  // remount alone replays the cached query result (CS-1201).
  const data = useLazyLoadQuery<candidatesTaskCandidatesQuery>(
    TaskCandidatesQuery,
    { taskId },
    { fetchKey, fetchPolicy: "network-only" },
  );
  const all = data.taskCandidateRevisions.edges.map((e) => e.node);
  const sorted = [...all].sort((a, b) => a.revision - b.revision);
  if (sorted.length === 0) {
    return <EmptyState title="No candidates proposed yet." />;
  }
  return (
    <ul className="cs-candidate-list" aria-label="candidate revisions">
      {sorted.map((c) => (
        <CandidateRow
          key={c.id}
          cand={c}
          parent={
            c.parentRevisionId
              ? all.find((x) => nodeId(x.id) === c.parentRevisionId)
              : undefined
          }
          onChanged={onChanged}
        />
      ))}
    </ul>
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
  const [entityRevisionId, setEntityRevisionId] = useState("");
  const [entityLabel, setEntityLabel] = useState<string | null>(null);
  const [difference, setDifference] = useState("");
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
              entityRevisionId: entityRevisionId || undefined,
              proposedDifferences: difference
                ? [difference]
                : undefined,
            },
          },
          onCompleted: (resp) => {
            const errs = resp.candidates.create.errors;
            setFeedback(
              errs.length ? `not proposed: ${errs[0].message}` : "proposed as draft",
            );
            if (!errs.length) {
              setEntityRevisionId("");
              setEntityLabel(null);
              setDifference("");
              onProposed();
            }
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
      <TextField
        label="proposed difference (optional)"
        hint="one line of what the candidate changes vs its baseline"
        value={difference}
        onChange={(e) => setDifference(e.target.value)}
      />
      <div className="cs-field">
        <label htmlFor="entity-kind" className="cs-field__label">
          entity kind
        </label>
        <select
          id="entity-kind"
          className="cs-select"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
            setEntityRevisionId("");
            setEntityLabel(null);
          }}
        >
          <option value="formulation">formulation</option>
          <option value="material">material</option>
          <option value="molecule">molecule</option>
        </select>
      </div>
      {kind === "formulation" ? (
        <FormulationRevisionPicker
          label="entity revision"
          hint="search by family name — binds the exact formulation revision"
          onPick={(p) => {
            setEntityRevisionId(p.uuid);
            setEntityLabel(p.label);
          }}
        />
      ) : (
        <MaterialIdentityPicker
          label={`${kind} identity`}
          hint="bind a registered material identity by name or identifier"
          onPick={(p) => {
            setEntityRevisionId(p.uuid);
            setEntityLabel(p.label);
          }}
        />
      )}
      {entityLabel && entityRevisionId && (
        <p className="cs-field__hint" data-field="bound-entity">
          bound to: {entityLabel}
        </p>
      )}
      <Button type="submit">Propose candidate (creates a draft revision)</Button>
      {feedback && <p role="status">{feedback}</p>}
    </form>
  );
}

export function CandidatePanel({ taskId }: { taskId: string }) {
  const [fetchKey, setFetchKey] = useState(0);
  const bump = () => setFetchKey((k) => k + 1);
  return (
    <div>
      <ProposeForm taskId={taskId} onProposed={bump} />
      <Suspense fallback={<LoadingState label="loading candidates…" />}>
        <CandidateList taskId={taskId} fetchKey={fetchKey} onChanged={bump} />
      </Suspense>
    </div>
  );
}
