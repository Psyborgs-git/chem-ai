import { Suspense, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../components/atoms/Badge";
import { Button } from "../../components/atoms/Button";
import { TextField } from "../../components/atoms/TextField";
import { EmptyState, LoadingState } from "../../components/states/states";
import {
  QuestionRaiseMutation,
  SessionEndMutation,
  SessionStartMutation,
  TaskSessionsQuery,
} from "./operations";
import { SessionStream } from "./SessionStream";

import type { researchQuestionRaiseMutation } from "../../__generated__/researchQuestionRaiseMutation.graphql";
import type { researchSessionEndMutation } from "../../__generated__/researchSessionEndMutation.graphql";
import type { researchSessionStartMutation } from "../../__generated__/researchSessionStartMutation.graphql";
import type { researchTaskSessionsQuery } from "../../__generated__/researchTaskSessionsQuery.graphql";

type ManifestItem = {
  kind?: string;
  refId?: string;
  text?: string;
  tokens?: number;
  pinned?: boolean;
};

/** The session's starting context (§10.1): what the compiler kept,
 * what the budget disclosed as omitted, and the pinned constraints
 * that can never be budgeted away. */
function ManifestView({
  manifest,
}: {
  manifest: NonNullable<
    NonNullable<
      researchTaskSessionsQuery["response"]["taskSessions"]["edges"][number]["node"]["startManifest"]
    >
  >;
}) {
  const items = (manifest.items as ManifestItem[]) ?? [];
  const omitted = (manifest.omitted as ManifestItem[]) ?? [];
  const pinned = items.filter((i) => i.pinned);
  return (
    <div className="cs-manifest" aria-label="session context manifest">
      <p>
        <Badge tone="info">{manifest.compilerVersion}</Badge>{" "}
        <span>
          {manifest.tokenEstimate}/{manifest.tokenBudget} tokens
        </span>{" "}
        {manifest.overBudget && <Badge tone="warning">over budget — constraints preserved</Badge>}
      </p>
      {pinned.length > 0 && (
        <ul aria-label="pinned constraints and warnings">
          {pinned.map((i, n) => (
            <li key={n} data-kind={i.kind}>
              <strong>{i.kind}</strong>: {i.text}
            </li>
          ))}
        </ul>
      )}
      <ul aria-label="selected context">
        {items
          .filter((i) => !i.pinned)
          .map((i, n) => (
            <li key={n} data-kind={i.kind} data-ref-id={i.refId ?? undefined}>
              <strong>{i.kind}</strong>: {i.text}
            </li>
          ))}
      </ul>
      {omitted.length > 0 && (
        <div role="note" aria-label="omitted context">
          <strong>omitted by budget (disclosed):</strong>
          <ul>
            {omitted.map((i, n) => (
              <li key={n} data-kind={i.kind}>
                {i.kind} <code>{i.refId}</code>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Sessions({ taskId }: { taskId: string }) {
  const [fetchKey, setFetchKey] = useState(0);
  const data = useLazyLoadQuery<researchTaskSessionsQuery>(
    TaskSessionsQuery,
    { taskId },
    { fetchKey, fetchPolicy: "network-only" },
  );
  const [startSession, starting] = useMutation<researchSessionStartMutation>(
    SessionStartMutation,
  );
  const [endSession, ending] = useMutation<researchSessionEndMutation>(SessionEndMutation);
  const [raiseQuestion, raising] = useMutation<researchQuestionRaiseMutation>(
    QuestionRaiseMutation,
  );
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");

  const sessions = data.taskSessions.edges.map((e) => e.node);
  const questions = data.taskQuestions;
  const summaries = data.taskSummaries;
  const active = sessions.find((s) => s.status === "active");

  return (
    <div>
      <p>
        {!active ? (
          <Button
            disabled={starting}
            onClick={() =>
              startSession({
                variables: { input: { taskId } },
                onCompleted: (r) => {
                  const errs = r.research.sessionStart.errors;
                  setError(errs.length ? errs.map((e) => e.message).join("; ") : null);
                  if (!errs.length) setFetchKey((k) => k + 1);
                },
                onError: (e) => setError(e.message),
              })
            }
          >
            start research session
          </Button>
        ) : (
          <Button
            disabled={ending}
            onClick={() =>
              endSession({
                variables: { input: { sessionId: active.id } },
                onCompleted: (r) => {
                  const errs = r.research.sessionEnd.errors;
                  setError(errs.length ? errs.map((e) => e.message).join("; ") : null);
                  if (!errs.length) setFetchKey((k) => k + 1);
                },
                onError: (e) => setError(e.message),
              })
            }
          >
            end active session
          </Button>
        )}
      </p>
      {error && (
        <p role="alert" className="cs-error">
          {error}
        </p>
      )}

      <h4>sessions</h4>
      {sessions.length === 0 ? (
        <EmptyState title="No sessions yet — starting one compiles the task context." />
      ) : (
        <ul>
          {sessions.map((s) => (
            <li key={s.id}>
              <code>{s.id}</code>{" "}
              <Badge tone={s.status === "active" ? "success" : "neutral"}>{s.status}</Badge>
              {s.endSnapshot != null && <small> snapshot recorded at end</small>}
              {s.startManifest && <ManifestView manifest={s.startManifest} />}
              <details>
                <summary>stream</summary>
                <SessionStream sessionId={s.id} />
              </details>
            </li>
          ))}
        </ul>
      )}

      <h4>open questions</h4>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!question.trim()) return;
          raiseQuestion({
            variables: { input: { taskId, question } },
            onCompleted: (r) => {
              const errs = r.research.questionRaise.errors;
              setError(errs.length ? errs.map((e) => e.message).join("; ") : null);
              if (!errs.length) {
                setQuestion("");
                setFetchKey((k) => k + 1);
              }
            },
            onError: (e) => setError(e.message),
          });
        }}
      >
        <TextField
          label="raise a question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <Button type="submit" disabled={raising}>
          raise
        </Button>
      </form>
      {questions.length === 0 ? (
        <EmptyState title="No questions recorded." />
      ) : (
        <ul>
          {questions.map((q) => (
            <li key={q.id}>
              {q.blocking && <Badge tone="warning">blocking</Badge>}{" "}
              <Badge tone={q.status === "open" ? "info" : "neutral"}>{q.status}</Badge>{" "}
              {q.question}
              {q.resolution && <small> — {q.resolution}</small>}
            </li>
          ))}
        </ul>
      )}

      <h4>summaries</h4>
      {summaries.length === 0 ? (
        <EmptyState title="No summaries — derived aids are written after review." />
      ) : (
        <ul>
          {summaries.map((s) => (
            <li key={s.id}>
              <Badge tone={s.stale ? "warning" : "success"}>
                {s.stale ? "stale" : "current"}
              </Badge>{" "}
              <Badge tone="neutral">derived · {s.generator}</Badge> {s.body}
              {s.stale && (
                <small>
                  {" "}
                  — written against a superseded contract; structured state is
                  authoritative.
                </small>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Research memory surface (§10.1): sessions resume from compiled
 * context, open questions and derived summaries stay distinct from
 * canonical state. */
export function ResearchPanel({ taskId }: { taskId: string }) {
  return (
    <Suspense fallback={<LoadingState label="loading research memory…" />}>
      <Sessions taskId={taskId} />
    </Suspense>
  );
}
