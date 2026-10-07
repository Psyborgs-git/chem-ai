/** Home surface (§22.1, PAR-09): recent tasks and pending decisions —
 * not a decorative dashboard. Every row is a real workspace task read
 * from the tasks connection; pending decisions deep-link into the
 * task's closeout view. */
import { Suspense } from "react";
import { useLazyLoadQuery } from "react-relay";
import { Link } from "react-router";

import { Badge } from "../../components/atoms/Badge";
import { EmptyState, LoadingState } from "../../components/states/states";
import { taskUrl } from "../tasks/TaskWorkspace";
import { WorkspaceHomeQuery } from "./operations";

import type { homeWorkspaceQuery } from "../../__generated__/homeWorkspaceQuery.graphql";

function HomeInner() {
  const data = useLazyLoadQuery<homeWorkspaceQuery>(WorkspaceHomeQuery, {});
  const recent = data.recent.edges.map((e) => e.node);
  const pending = data.pendingDecisions.edges.map((e) => e.node);
  return (
    <>
      <section aria-labelledby="pending-decisions-heading">
        <h2 id="pending-decisions-heading">pending decisions</h2>
        {pending.length === 0 ? (
          <EmptyState title="Nothing is waiting on a review decision." />
        ) : (
          <ul data-field="pending-decisions">
            {pending.map((t) => (
              <li key={t.id}>
                <Link to={taskUrl(t.id, "decisions", "closeout")}>
                  {t.title}
                </Link>{" "}
                <Badge tone="info">awaiting review</Badge>
                {t.project && (
                  <>
                    {" "}
                    <span className="cs-field__hint">{t.project.name}</span>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-labelledby="recent-tasks-heading">
        <h2 id="recent-tasks-heading">recent tasks</h2>
        {recent.length === 0 ? (
          <EmptyState title="No tasks yet — open a project to create one." />
        ) : (
          <ul data-field="recent-tasks">
            {recent.map((t) => (
              <li key={t.id}>
                <Link to={taskUrl(t.id, "overview")}>{t.title}</Link>{" "}
                <Badge tone="neutral">{t.workflowState}</Badge>{" "}
                <Badge tone="neutral">{t.mode}</Badge>
                {t.project && (
                  <>
                    {" "}
                    <span className="cs-field__hint">{t.project.name}</span>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

export function HomePage() {
  return (
    <div>
      <h1>Chemistry Studio</h1>
      <Suspense fallback={<LoadingState label="loading workspace…" />}>
        <HomeInner />
      </Suspense>
      <p>
        <Link to="/projects">Open projects</Link>
      </p>
    </div>
  );
}
