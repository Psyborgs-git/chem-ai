import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../components/atoms/Badge";
import { Button } from "../../components/atoms/Button";
import { EmptyState } from "../../components/states/states";
import { fetchEventSnapshot } from "../../relay/network";
import { openStream } from "../research/stream";
import { RunRequestCancelMutation, TaskRunsQuery } from "./operations";

import type { runsRequestCancelMutation } from "../../__generated__/runsRequestCancelMutation.graphql";
import type { runsTaskRunsQuery } from "../../__generated__/runsTaskRunsQuery.graphql";

type RunNode = NonNullable<
  runsTaskRunsQuery["response"]["taskRuns"]["edges"][number]["node"]
>;

const TERMINAL = new Set(["succeeded", "failed", "timed_out", "cancelled", "interrupted"]);

/** User-facing run state (§13): a cancel request is NOT a cancel —
 * the badge stays "cancel requested…" until the terminal `cancelled`
 * confirmation arrives (AT-0406-3). A failed run with no result is
 * output-unavailable, not "no output". */
function runStateLabel(run: RunNode): { label: string; tone: "info" | "success" | "warning" | "danger" | "neutral" } {
  switch (run.status) {
    case "requested":
      return { label: "requested", tone: "neutral" };
    case "awaiting_approval":
      return { label: "awaiting approval", tone: "warning" };
    case "queued":
      return { label: "queued", tone: "info" };
    case "running":
      return { label: "running", tone: "info" };
    case "cancel_requested":
      return { label: "cancel requested…", tone: "warning" };
    case "cancelled":
      return { label: "cancelled", tone: "neutral" };
    case "blocked":
      return { label: "blocked", tone: "warning" };
    case "interrupted":
      return { label: "interrupted", tone: "danger" };
    case "timed_out":
      return { label: "timed out", tone: "danger" };
    case "succeeded":
      return { label: "completed", tone: "success" };
    case "failed":
      return run.resultSummary == null
        ? { label: "failed — output unavailable", tone: "danger" }
        : { label: "failed", tone: "danger" };
    default:
      return { label: run.status, tone: "neutral" };
  }
}

function RunRow({ run }: { run: RunNode }) {
  const [commit] = useMutation<runsRequestCancelMutation>(RunRequestCancelMutation);
  const [pending, setPending] = useState(false);
  const state = runStateLabel(run);
  const cancelable = !TERMINAL.has(run.status) && run.status !== "cancel_requested";
  const cancel = () => {
    setPending(true);
    commit({
      variables: { input: { runId: run.id } },
      onCompleted: () => setPending(false),
      onError: () => setPending(false),
    });
  };
  const attempts = [...(run.attempts ?? [])];
  return (
    <li data-run-id={run.id} data-status={run.status}>
      <p>
        <Badge tone={state.tone}>{state.label}</Badge>{" "}
        <Badge tone="neutral">{run.kind}</Badge>{" "}
        <span>
          attempt {run.attemptCount}/{run.maxAttempts}
        </span>
      </p>
      {run.error ? (
        <p role="note">
          error: {String((run.error as Record<string, unknown>)?.code ?? "unknown")}
        </p>
      ) : null}
      {attempts.length > 0 && (
        <ul aria-label="attempts">
          {attempts.map((a) => (
            <li key={a.id} data-attempt-status={a.status}>
              #{a.attemptNumber} {a.status}
              {a.workerId ? ` · ${a.workerId}` : ""}
            </li>
          ))}
        </ul>
      )}
      {cancelable && (
        <Button
          type="button"
          disabled={pending}
          onClick={cancel}
          aria-label={`cancel ${run.kind} run`}
        >
          cancel
        </Button>
      )}
      {!TERMINAL.has(run.status) && (
        <Link to={`/compute/fallback/${encodeURIComponent(run.id)}`}>fallback review</Link>
      )}
    </li>
  );
}

/** Runs for a task, kept live via the bounded task channel: every
 * outbox event triggers a refetch of the authoritative snapshot, so a
 * reconnect can never duplicate or resurrect state. */
export function RunsPanel({ taskId }: { taskId: string }) {
  const [fetchKey, setFetchKey] = useState(0);
  const [live, setLive] = useState(false);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const data = useLazyLoadQuery<runsTaskRunsQuery>(
    TaskRunsQuery,
    { taskId },
    { fetchKey, fetchPolicy: "network-only" },
  );

  useEffect(() => {
    let source: EventSource | null = null;
    let cancelled = false;
    const bump = () => {
      if (debounce.current) clearTimeout(debounce.current);
      debounce.current = setTimeout(() => setFetchKey((k) => k + 1), 100);
    };
    void fetchEventSnapshot("task", taskId)
      .then((snap) => {
        if (cancelled) return;
        source = openStream("task", taskId, snap.maxSeq, {
          onEvent: bump,
          onOpen: () => {
            setLive(true);
            bump(); // snapshot may have changed while connecting
          },
          onError: () => setLive(false),
        });
      })
      .catch(() => setLive(false));
    return () => {
      cancelled = true;
      source?.close();
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [taskId]);

  const runs = data.taskRuns.edges.map((e) => e.node).filter((n) => n != null);
  return (
    <section aria-label="runs">
      <p>
        {live ? (
          <Badge tone="info">live</Badge>
        ) : (
          <Badge tone="neutral">reconnecting…</Badge>
        )}
      </p>
      {runs.length === 0 ? (
        <EmptyState title="no runs yet" />
      ) : (
        <ul aria-label="task runs">
          {runs.map((run) => (
            <RunRow key={run.id} run={run} />
          ))}
        </ul>
      )}
    </section>
  );
}
