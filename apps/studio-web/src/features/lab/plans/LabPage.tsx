import { Suspense, useState } from "react";
import { useLazyLoadQuery } from "react-relay";

import { EmptyState, LoadingState } from "../../../components/states/states";
import {
  ProjectListQuery,
  ProjectTasksQuery,
} from "../../tasks/operations";
import { PlansPanel } from "./PlansPanel";
import { ResultsPanel } from "../results/ResultsPanel";

import type { tasksProjectListQuery } from "../../../__generated__/tasksProjectListQuery.graphql";
import type { tasksProjectTasksQuery } from "../../../__generated__/tasksProjectTasksQuery.graphql";

function TaskPicker({
  projectId,
  taskId,
  onPick,
}: {
  projectId: string;
  taskId: string;
  onPick: (taskId: string) => void;
}) {
  const data = useLazyLoadQuery<tasksProjectTasksQuery>(ProjectTasksQuery, {
    projectId,
  });
  const tasks = data.projectTasks.edges.map((e) => e.node);
  if (tasks.length === 0) {
    return <EmptyState title="no tasks in this project." />;
  }
  return (
    <div className="cs-field">
      <label className="cs-field__label" htmlFor="lab-task">
        research task
      </label>
      <select
        id="lab-task"
        className="cs-input"
        value={taskId}
        onChange={(e) => onPick(e.target.value)}
      >
        <option value="">select a task…</option>
        {tasks.map((t) => (
          <option key={t.id} value={t.id}>
            {t.title}
          </option>
        ))}
      </select>
    </div>
  );
}

/** Lab surface (§14.1, CS-0501): experiment planning and scientific
 * review. Plans bind immutable revisions; approval releases only a
 * manual-execution packet — the system never starts equipment. */
export function LabPage() {
  const data = useLazyLoadQuery<tasksProjectListQuery>(ProjectListQuery, {});
  const [projectId, setProjectId] = useState("");
  const [taskId, setTaskId] = useState("");
  const projects = data.projects.edges.map((e) => e.node);

  return (
    <div>
      <h1>Lab</h1>
      <p>
        Manual-first experiment planning. Approved plans release a packet for
        qualified human operators — no equipment execution.
      </p>
      {projects.length === 0 ? (
        <EmptyState title="No projects yet." />
      ) : (
        <>
          <div className="cs-field">
            <label className="cs-field__label" htmlFor="lab-project">
              project
            </label>
            <select
              id="lab-project"
              className="cs-input"
              value={projectId}
              onChange={(e) => {
                setProjectId(e.target.value);
                setTaskId("");
              }}
            >
              <option value="">select a project…</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          {projectId && (
            <Suspense fallback={<LoadingState label="loading tasks…" />}>
              <TaskPicker
                projectId={projectId}
                taskId={taskId}
                onPick={setTaskId}
              />
            </Suspense>
          )}
          {taskId && (
            <Suspense fallback={<LoadingState label="loading plans…" />}>
              <PlansPanel key={taskId} taskId={taskId} />
            </Suspense>
          )}
          {taskId && (
            <Suspense fallback={<LoadingState label="loading executions…" />}>
              <ResultsPanel key={`r-${taskId}`} taskId={taskId} />
            </Suspense>
          )}
        </>
      )}
    </div>
  );
}
