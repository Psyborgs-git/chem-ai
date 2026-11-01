import { Suspense, useEffect, useState } from "react";
import { useLazyLoadQuery } from "react-relay";
import { Link, useParams } from "react-router";

import { Button } from "../../components/atoms/Button";
import { EmptyState, LoadingState } from "../../components/states/states";
import { RunDetailQuery } from "./operations";
import { RunResult, TERMINAL_RUN_STATES } from "./RunResult";
import { RunCancelControl } from "./RunCancelControl";

import type { runsDetailQuery } from "../../__generated__/runsDetailQuery.graphql";
import "./calculations.css";

function RunDetail({ runId }: { runId: string }) {
  const [fetchKey, setFetchKey] = useState(0);
  const [polls, setPolls] = useState(0);
  const data = useLazyLoadQuery<runsDetailQuery>(RunDetailQuery, { runId }, { fetchKey, fetchPolicy: "network-only" });
  const node = data.node;
  const run = node?.__typename === "Run" ? node : null;
  const status = run?.status;

  // A detail URL works independently of a mounted task SSE channel.
  // Bounded polling stops on terminal state or after one minute.
  useEffect(() => {
    if (!status || TERMINAL_RUN_STATES.has(status) || polls >= 30) return;
    const timer = setTimeout(() => {
      setPolls((value) => value + 1);
      setFetchKey((value) => value + 1);
    }, 2000);
    return () => clearTimeout(timer);
  }, [status, polls]);

  if (!run) return <EmptyState title="Run not found in this workspace." action={<Link to="/projects">Open projects</Link>} />;
  const taskUrl = run.taskId ? `/tasks/${encodeURIComponent(run.taskId)}/experiments?view=calculations` : "/projects";
  return (
    <article aria-labelledby="run-title">
      <nav aria-label="Run breadcrumb" className="cs-run-details__breadcrumb"><Link to={taskUrl}>← {run.taskId ? "Back to task calculations" : "Back to projects"}</Link></nav>
      <div className="cs-calculation-header"><div><p className="cs-field__hint">SAVED RUN</p><h1 id="run-title">{run.kind === "rdkit_descriptors" ? "Molecular calculation" : run.kind.replaceAll("_", " ")}</h1><p className="cs-field__hint">A durable record of this run and its result.</p></div><Button onClick={() => { setPolls(0); setFetchKey((value) => value + 1); }}>Refresh run</Button></div>
      <RunResult run={run} />
      <RunCancelControl run={run} onChanged={() => { setPolls(0); setFetchKey((value) => value + 1); }} />
      {run.status === "blocked" && <p><Link to={`/compute/fallback/${encodeURIComponent(run.id)}`}>Review local capacity and fallback options</Link></p>}
      {run.attempts.length > 0 && <details className="cs-calculation-raw"><summary>Execution attempts ({run.attempts.length})</summary><ol aria-label="Execution attempts">{run.attempts.map((attempt) => <li key={attempt.id}><strong>Attempt {attempt.attemptNumber}</strong> · {attempt.status} · {attempt.queue}{attempt.workerId && <> · {attempt.workerId}</>}</li>)}</ol></details>}
      <p className="cs-field__hint">Run ID: <code>{run.id}</code></p>
      {!TERMINAL_RUN_STATES.has(run.status) && polls >= 30 && <p role="status">Automatic refresh paused. Use Refresh run to check the latest state.</p>}
    </article>
  );
}

export function RunDetailsPage() {
  const { runId } = useParams();
  if (!runId) return <EmptyState title="Run not found." />;
  return <Suspense fallback={<LoadingState label="Loading saved run…" />}><RunDetail key={runId} runId={runId} /></Suspense>;
}
