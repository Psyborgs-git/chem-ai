import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { useLazyLoadQuery } from "react-relay";

import { Badge } from "../../components/atoms/Badge";
import { EmptyState } from "../../components/states/states";
import { fetchEventSnapshot } from "../../relay/network";
import {
  classifySnapshotError,
  openStream,
  retryDelayMs,
  streamClosed,
} from "../research/stream";
import { TaskRunsQuery } from "./operations";
import { RunResult, RunTime } from "./RunResult";
import { RunCancelControl } from "./RunCancelControl";
import "./calculations.css";

import type { runsTaskRunsQuery } from "../../__generated__/runsTaskRunsQuery.graphql";

type RunNode = NonNullable<
  runsTaskRunsQuery["response"]["taskRuns"]["edges"][number]["node"]
>;

const TERMINAL = new Set(["succeeded", "failed", "timed_out", "cancelled", "interrupted"]);

function RunRow({ run }: { run: RunNode }) {
  const attempts = [...(run.attempts ?? [])];
  return (
    <li className="cs-run-card" data-run-id={run.id} data-status={run.status}>
      <div className="cs-run-card__header">
        <h3><Link to={`/runs/${encodeURIComponent(run.id)}`}>{run.kind === "rdkit_descriptors" ? "Molecular calculation" : run.kind.replaceAll("_", " ")}</Link></h3>
        <span className="cs-field__hint">
          attempt {run.attemptCount}/{run.maxAttempts}
        </span>
      </div>
      <RunResult run={run} compact />
      <p className="cs-field__hint">{run.finishedAt ? <>Finished <RunTime value={run.finishedAt} /></> : run.startedAt ? <>Started <RunTime value={run.startedAt} /></> : <>Queued <RunTime value={run.queuedAt} /></>}</p>
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
      <RunCancelControl run={run} />
      {!TERMINAL.has(run.status) && (
        <Link to={`/compute/fallback/${encodeURIComponent(run.id)}`}>fallback review</Link>
      )}
    </li>
  );
}

type RunsStreamStatus = "connecting" | "live" | "reconnecting" | "unavailable" | "ended";

const RUNS_BADGE: Record<RunsStreamStatus, { tone: "info" | "neutral" | "warning"; label: string }> = {
  connecting: { tone: "neutral", label: "connecting…" },
  live: { tone: "info", label: "live" },
  reconnecting: { tone: "neutral", label: "reconnecting…" },
  unavailable: { tone: "warning", label: "updates unavailable — retrying" },
  ended: { tone: "warning", label: "updates ended" },
};

/** Runs for a task, kept live via the bounded task channel: every
 * outbox event triggers a refetch of the authoritative snapshot, so a
 * reconnect can never duplicate or resurrect state. Snapshot failure
 * is classified (PAR-08a): terminal 401/403/404 stops retrying instead
 * of presenting a dead channel as reconnecting. */
export function RunsPanel({ taskId, refreshKey = 0 }: { taskId: string; refreshKey?: number }) {
  const [fetchKey, setFetchKey] = useState(0);
  const [status, setStatus] = useState<RunsStreamStatus>("connecting");
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const data = useLazyLoadQuery<runsTaskRunsQuery>(
    TaskRunsQuery,
    { taskId },
    { fetchKey: fetchKey + refreshKey, fetchPolicy: "network-only" },
  );

  useEffect(() => {
    let source: EventSource | null = null;
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    const bump = () => {
      if (debounce.current) clearTimeout(debounce.current);
      debounce.current = setTimeout(() => setFetchKey((k) => k + 1), 100);
    };
    function closeSource() {
      source?.close();
      source = null;
    }
    function scheduleRetry() {
      if (cancelled || retryTimer != null) return;
      attempt += 1;
      retryTimer = setTimeout(() => {
        retryTimer = null;
        void connect();
      }, retryDelayMs(attempt));
    }
    async function connect() {
      try {
        const snap = await fetchEventSnapshot("task", taskId);
        if (cancelled) return;
        attempt = 0;
        if (source == null || streamClosed(source)) {
          closeSource();
          source = openStream("task", taskId, snap.maxSeq, {
            onEvent: bump,
            onOpen: () => {
              if (cancelled) return;
              setStatus("live");
              bump(); // snapshot may have changed while connecting
            },
            onError: () => {
              if (cancelled) return;
              setStatus("reconnecting");
              // EventSource auto-retries network drops; a closed socket
              // (non-2xx) is classified via a snapshot probe instead.
              if (source != null && streamClosed(source)) {
                closeSource();
                void connect();
              }
            },
          });
        }
      } catch (err) {
        if (cancelled) return;
        const kind = classifySnapshotError(err);
        if (kind === "transient") {
          setStatus("unavailable");
          scheduleRetry();
          return;
        }
        closeSource();
        setStatus("ended");
      }
    }
    void connect();
    return () => {
      cancelled = true;
      if (retryTimer != null) clearTimeout(retryTimer);
      closeSource();
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [taskId]);

  const runs = data.taskRuns.edges.map((e) => e.node).filter((n) => n != null);
  const badge = RUNS_BADGE[status];
  return (
    <section aria-label="runs">
      <p>
        <Badge tone={badge.tone}>{badge.label}</Badge>
      </p>
      {runs.length === 0 ? (
        <EmptyState title="No runs yet. Run a local calculation to save the first result." />
      ) : (
        <ul className="cs-run-list" aria-label="task runs">
          {runs.map((run) => (
            <RunRow key={run.id} run={run} />
          ))}
        </ul>
      )}
    </section>
  );
}
