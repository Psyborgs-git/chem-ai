import { Suspense, useState } from "react";
import { useLazyLoadQuery } from "react-relay";
import { Link } from "react-router";

import { Badge } from "../../components/atoms/Badge";
import { StatusIndicator } from "../../components/atoms/StatusIndicator";
import {
  EmptyState,
  LoadingState,
} from "../../components/states/states";
import { CandidatePanel } from "../candidates/CandidatePanel";
import { DatasetsPanel } from "../learning/datasets/DatasetsPanel";
import { ModelsPanel } from "../learning/models/ModelsPanel";
import { TrainingPanel } from "../learning/training/TrainingPanel";
import { OptimizationPanel } from "../optimization/OptimizationPanel";
import { ReferenceAnalysisPanel } from "../reference-analysis/ReferenceAnalysisPanel";
import { ResearchPanel } from "../research/ResearchPanel";
import { RunsPanel } from "../runs/RunsPanel";
import { ContractEditor } from "./ContractEditor";
import { CloseoutPanel } from "./closeout/CloseoutPanel";
import { DecisionsPanel } from "./report/DecisionsPanel";
import { TaskReportPanel } from "./report/TaskReportPanel";
import { TaskDetailQuery } from "./operations";

import type { tasksTaskDetailQuery } from "../../__generated__/tasksTaskDetailQuery.graphql";

const SECTIONS = [
  "overview",
  "candidates",
  "research",
  "runs",
  "closeout",
  "report",
  "decisions",
  "datasets",
  "training",
  "models",
  "optimization",
  "analysis",
] as const;
type Section = (typeof SECTIONS)[number];

function TaskDetail({ taskId, section }: { taskId: string; section: Section }) {
  const data = useLazyLoadQuery<tasksTaskDetailQuery>(TaskDetailQuery, {
    id: taskId,
    includeOptimization: section === "optimization",
    includeAnalysis: section === "analysis",
  });
  const node = data.node;
  if (!node || !("title" in node) || !node.id) {
    return <EmptyState title="Task not found in this workspace." />;
  }
  const task = node;
  const tid = node.id; // narrowed to string by the guard above
  const blockers = task.unresolvedInputs ?? [];
  const workflowState = task.workflowState ?? "unknown";
  return (
    <div>
      <header>
        <h2>{task.title}</h2>
        <p>
          <StatusIndicator
            status={workflowState as Parameters<typeof StatusIndicator>[0]["status"]}
          />{" "}
          <Badge tone="info">mode: {task.mode}</Badge>{" "}
          <Badge tone="neutral">cycle {task.evaluationCycle}</Badge>
        </p>
        {blockers.length > 0 && (
          <div role="note" aria-label="blockers">
            <strong>current blockers:</strong> {blockers.join(", ")}
          </div>
        )}
      </header>
      {section === "overview" && (
        <section aria-labelledby="contract-heading">
          <h3 id="contract-heading">success contract</h3>
          <ContractEditor taskId={tid} workflowState={workflowState} />
        </section>
      )}
      {section === "candidates" && (
        <section aria-labelledby="candidates-heading">
          <h3 id="candidates-heading">candidates</h3>
          <CandidatePanel taskId={tid} />
        </section>
      )}
      {section === "research" && (
        <section aria-labelledby="research-heading">
          <h3 id="research-heading">research memory</h3>
          <ResearchPanel taskId={tid} />
        </section>
      )}
      {section === "runs" && (
        <section aria-labelledby="runs-heading">
          <h3 id="runs-heading">runs</h3>
          <RunsPanel taskId={tid} />
        </section>
      )}
      {section === "closeout" && (
        <section aria-labelledby="closeout-heading">
          <h3 id="closeout-heading">closeout evaluation</h3>
          <CloseoutPanel taskId={tid} workflowState={workflowState} />
        </section>
      )}
      {section === "report" && (
        <section aria-labelledby="report-heading">
          <h3 id="report-heading">task report</h3>
          <TaskReportPanel taskId={tid} />
        </section>
      )}
      {section === "decisions" && (
        <section aria-labelledby="decisions-heading">
          <h3 id="decisions-heading">decisions</h3>
          <DecisionsPanel taskId={tid} />
        </section>
      )}
      {section === "datasets" && (
        <section aria-labelledby="datasets-heading">
          <h3 id="datasets-heading">dataset snapshots</h3>
          <DatasetsPanel taskId={tid} />
        </section>
      )}
      {section === "training" && (
        <section aria-labelledby="training-heading">
          <h3 id="training-heading">training runs</h3>
          <TrainingPanel taskId={tid} />
        </section>
      )}
      {section === "models" && (
        <section aria-labelledby="models-heading">
          <h3 id="models-heading">model registry</h3>
          <ModelsPanel taskId={tid} />
        </section>
      )}
      {section === "optimization" && task.optimization && <section aria-label="optimization"><h3>optimization</h3><OptimizationPanel taskRef={task.optimization} /></section>}
      {section === "analysis" && task.analysis && <section aria-label="reference analysis"><h3>reference analysis</h3><ReferenceAnalysisPanel taskRef={task.analysis} /></section>}
    </div>
  );
}

/** Task workspace (§22.1): persistent sections — overview keeps the
 * contract and active blockers in view. */
export function TaskWorkspace({ taskId }: { taskId: string }) {
  const [section, setSection] = useState<Section>("overview");
  return (
    <div>
      <nav aria-label="task sections">
        {SECTIONS.map((s) => (
          <button
            key={s}
            type="button"
            aria-pressed={section === s}
            className={section === s ? "cs-tab cs-tab--active" : "cs-tab"}
            onClick={() => setSection(s)}
          >
            {s}
          </button>
        ))}
      </nav>
      <Suspense fallback={<LoadingState label="loading task…" />}>
        <TaskDetail taskId={taskId} section={section} />
      </Suspense>
      <p>
        <Link to="/projects">back to projects</Link>
      </p>
    </div>
  );
}
