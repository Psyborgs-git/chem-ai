/** Task workspace (§22.1, PAR-09): the six approved primary groups —
 * overview, research, candidates, experiments, evidence, decisions —
 * map the existing panels; learning, analysis and run surfaces stay
 * reachable under "advanced" through progressive disclosure, never
 * deleted. Group and subview are URL state (/tasks/:id/:group?view=x)
 * so refresh, back and deep links restore the exact context. The
 * context header keeps objective, selected contract revision,
 * evidence gaps and the next authorized action visible — every field
 * is read from the task query, nothing decorative. */
import { Suspense } from "react";
import { useLazyLoadQuery } from "react-relay";
import { Link, NavLink, Navigate, useParams, useSearchParams } from "react-router";

import { Badge } from "../../components/atoms/Badge";
import { StatusIndicator } from "../../components/atoms/StatusIndicator";
import { EmptyState, LoadingState } from "../../components/states/states";
import { CandidatePanel } from "../candidates/CandidatePanel";
import { EvidencePanel } from "../evidence/EvidencePanel";
import { QualityPanel } from "../evidence/quality/QualityPanel";
import { PlansPanel } from "../lab/plans/PlansPanel";
import { ResultsPanel } from "../lab/results/ResultsPanel";
import { DatasetsPanel } from "../learning/datasets/DatasetsPanel";
import { EvaluationsPanel } from "../learning/evaluations/EvaluationsPanel";
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

export const GROUPS = [
  { key: "overview", label: "overview" },
  { key: "research", label: "research" },
  { key: "candidates", label: "candidates" },
  { key: "experiments", label: "experiments" },
  { key: "evidence", label: "evidence" },
  { key: "decisions", label: "decisions" },
  { key: "advanced", label: "advanced" },
] as const;
export type GroupKey = (typeof GROUPS)[number]["key"];

/** Subviews within a group — the previous flat sections, mapped under
 * their group. "advanced" is the progressive-disclosure bucket for
 * run/learning/analysis capability (§22.1: disclosed, not hidden). */
export const SUBVIEWS: Record<GroupKey, { key: string; label: string }[]> = {
  overview: [],
  research: [],
  candidates: [],
  experiments: [
    { key: "plans", label: "plans" },
    { key: "results", label: "results" },
  ],
  evidence: [
    { key: "claims", label: "claims" },
    { key: "quality", label: "source quality" },
  ],
  decisions: [
    { key: "log", label: "decision log" },
    { key: "closeout", label: "closeout" },
    { key: "report", label: "report" },
  ],
  advanced: [
    { key: "runs", label: "runs" },
    { key: "datasets", label: "datasets" },
    { key: "training", label: "training" },
    { key: "models", label: "models" },
    { key: "evaluations", label: "evaluations" },
    { key: "optimization", label: "optimization" },
    { key: "analysis", label: "analysis" },
  ],
};

export function isGroup(key: string | undefined): key is GroupKey {
  return GROUPS.some((g) => g.key === key);
}

export function defaultView(group: GroupKey): string | null {
  return SUBVIEWS[group][0]?.key ?? null;
}

export function taskUrl(taskId: string, group: GroupKey, view?: string | null) {
  const base = `/tasks/${encodeURIComponent(taskId)}/${group}`;
  return view ? `${base}?view=${view}` : base;
}

type DetailData = tasksTaskDetailQuery["response"];
type TaskNode = NonNullable<DetailData["node"]> & { id?: string };

type NextAction = { label: string; to?: string };

/** Derive the next authorized action from real state: blocking gaps
 * first (re-assessment, blocking questions), then workflow position,
 * then the candidate → plan → evidence progression (§22.1). Every
 * suggestion links to the group that can actually carry it out. */
function nextAction(
  tid: string,
  workflowState: string,
  contractStatus: string | null,
  candidateStatuses: string[],
  planStatuses: string[],
  blockingQuestions: number,
  needsReassessment: boolean,
): NextAction {
  if (needsReassessment) {
    return {
      label: "re-assess — task inputs changed since the last evaluation",
      to: taskUrl(tid, "decisions", "closeout"),
    };
  }
  if (blockingQuestions > 0) {
    return {
      label: `resolve ${blockingQuestions} blocking research question${blockingQuestions === 1 ? "" : "s"}`,
      to: taskUrl(tid, "research"),
    };
  }
  const hasCandidate = candidateStatuses.length > 0;
  const hasAccepted = candidateStatuses.includes("accepted_for_research");
  const hasApprovedPlan = planStatuses.includes("approved");
  switch (workflowState) {
    case "closed":
      return {
        label: "read the final report and closure decision",
        to: taskUrl(tid, "decisions", "report"),
      };
    case "awaiting_review":
      return {
        label: "review the evaluation and record the closure decision",
        to: taskUrl(tid, "decisions", "closeout"),
      };
    case "cancelled":
      return { label: "task is cancelled — no authorized actions remain" };
    case "paused":
      return { label: "task is paused — resume it before continuing work" };
    case "draft":
      if (!contractStatus) {
        return { label: "draft the success contract", to: taskUrl(tid, "overview") };
      }
      if (contractStatus === "draft") {
        return {
          label: "finish and freeze the success contract",
          to: taskUrl(tid, "overview"),
        };
      }
      if (!hasCandidate) {
        return { label: "propose a candidate", to: taskUrl(tid, "candidates") };
      }
      return {
        label: "a reviewer must transition the task to active — see closeout",
        to: taskUrl(tid, "decisions", "closeout"),
      };
    default:
      if (!hasCandidate) {
        return { label: "propose a candidate", to: taskUrl(tid, "candidates") };
      }
      if (!hasAccepted) {
        return {
          label: "submit a candidate for human review",
          to: taskUrl(tid, "candidates"),
        };
      }
      if (!hasApprovedPlan) {
        return {
          label: "open an experiment plan for the accepted candidate",
          to: taskUrl(tid, "experiments"),
        };
      }
      return {
        label: "record lab results, then send to review when evidence is complete",
        to: taskUrl(tid, "experiments", "results"),
      };
  }
}

function GroupBody({
  task,
  group,
  view,
}: {
  task: TaskNode;
  group: GroupKey;
  view: string | null;
}) {
  const tid = task.id as string;
  const workflowState = task.workflowState ?? "unknown";
  switch (group) {
    case "overview":
      return (
        <section aria-labelledby="contract-heading">
          <h3 id="contract-heading">success contract</h3>
          <ContractEditor taskId={tid} workflowState={workflowState} />
        </section>
      );
    case "research":
      return (
        <section aria-labelledby="research-heading">
          <h3 id="research-heading">research memory</h3>
          <ResearchPanel taskId={tid} />
        </section>
      );
    case "candidates":
      return (
        <section aria-labelledby="candidates-heading">
          <h3 id="candidates-heading">candidates</h3>
          <CandidatePanel taskId={tid} />
        </section>
      );
    case "experiments":
      return view === "results" ? (
        <section aria-labelledby="results-heading">
          <h3 id="results-heading">results</h3>
          <ResultsPanel taskId={tid} />
        </section>
      ) : (
        <section aria-labelledby="plans-heading">
          <h3 id="plans-heading">experiment plans</h3>
          <PlansPanel taskId={tid} />
        </section>
      );
    case "evidence":
      return view === "quality" ? (
        <section aria-labelledby="quality-heading">
          <h3 id="quality-heading">source quality</h3>
          <QualityPanel />
        </section>
      ) : (
        <section aria-labelledby="evidence-heading">
          <h3 id="evidence-heading">evidence claims</h3>
          <EvidencePanel />
        </section>
      );
    case "decisions":
      if (view === "closeout") {
        return (
          <section aria-labelledby="closeout-heading">
            <h3 id="closeout-heading">closeout evaluation</h3>
            <CloseoutPanel taskId={tid} workflowState={workflowState} />
          </section>
        );
      }
      if (view === "report") {
        return (
          <section aria-labelledby="report-heading">
            <h3 id="report-heading">task report</h3>
            <TaskReportPanel taskId={tid} />
          </section>
        );
      }
      return (
        <section aria-labelledby="decisions-heading">
          <h3 id="decisions-heading">decision log</h3>
          <DecisionsPanel taskId={tid} />
        </section>
      );
    case "advanced":
      switch (view) {
        case "runs":
          return (
            <section aria-labelledby="runs-heading">
              <h3 id="runs-heading">runs</h3>
              <RunsPanel taskId={tid} />
            </section>
          );
        case "datasets":
          return (
            <section aria-labelledby="datasets-heading">
              <h3 id="datasets-heading">dataset snapshots</h3>
              <DatasetsPanel taskId={tid} />
            </section>
          );
        case "training":
          return (
            <section aria-labelledby="training-heading">
              <h3 id="training-heading">training runs</h3>
              <TrainingPanel taskId={tid} />
            </section>
          );
        case "models":
          return (
            <section aria-labelledby="models-heading">
              <h3 id="models-heading">model registry</h3>
              <ModelsPanel taskId={tid} />
            </section>
          );
        case "evaluations":
          return (
            <section aria-label="evaluations">
              <h3>evaluations & promotion</h3>
              <EvaluationsPanel taskId={tid} />
            </section>
          );
        case "optimization":
          return task.optimization ? (
            <section aria-label="optimization">
              <h3>optimization</h3>
              <OptimizationPanel taskRef={task.optimization} />
            </section>
          ) : null;
        case "analysis":
          return task.analysis ? (
            <section aria-label="reference analysis">
              <h3>reference analysis</h3>
              <ReferenceAnalysisPanel taskRef={task.analysis} />
            </section>
          ) : null;
        default:
          return null;
      }
    default:
      return null;
  }
}

function TaskDetail({
  taskId,
  group,
  view,
}: {
  taskId: string;
  group: GroupKey;
  view: string | null;
}) {
  const data = useLazyLoadQuery<tasksTaskDetailQuery>(TaskDetailQuery, {
    id: taskId,
    includeOptimization: group === "advanced" && view === "optimization",
    includeAnalysis: group === "advanced" && view === "analysis",
  });
  const node = data.node;
  if (!node || !("title" in node) || !node.id) {
    return <EmptyState title="Task not found in this workspace." />;
  }
  const task: TaskNode = node;
  const tid = node.id;
  const workflowState = task.workflowState ?? "unknown";
  const contract = data.taskContractRevisions.edges[0]?.node ?? null;
  const candidateStatuses = data.taskCandidateRevisions.edges.map(
    (e) => e.node.status,
  );
  const planStatuses = data.taskPlans.edges.map((e) => e.node.status);
  const blockingQuestions = (data.taskQuestions ?? []).filter(
    (q) => q.blocking && q.status === "open",
  ).length;
  const reassessment = (data.taskReassessmentStatus ?? {}) as Record<
    string,
    unknown
  >;
  const needsReassessment = reassessment.needsReassessment === true;

  const gaps: string[] = [...(task.unresolvedInputs ?? [])];
  if (needsReassessment) gaps.push("task inputs changed — re-assessment due");
  if (blockingQuestions > 0) {
    gaps.push(
      `${blockingQuestions} blocking research question${blockingQuestions === 1 ? "" : "s"}`,
    );
  }
  const next = nextAction(
    tid,
    workflowState,
    contract?.status ?? null,
    candidateStatuses,
    planStatuses,
    blockingQuestions,
    needsReassessment,
  );

  return (
    <div>
      <header className="cs-task-context">
        <h2>{task.title}</h2>
        <p>
          <StatusIndicator
            status={workflowState as Parameters<typeof StatusIndicator>[0]["status"]}
          />{" "}
          <Badge tone="info">mode: {task.mode}</Badge>{" "}
          <Badge tone="neutral">cycle {task.evaluationCycle}</Badge>{" "}
          {task.project && (
            <Link to={`/projects/${encodeURIComponent(task.project.id)}`}>
              {task.project.name}
            </Link>
          )}
        </p>
        {task.objective && (
          <p data-field="objective">
            <strong>objective:</strong> {task.objective}
          </p>
        )}
        <p data-field="contract-state">
          <strong>contract:</strong>{" "}
          {contract
            ? `rev ${contract.revision} (${contract.status})`
            : "none drafted"}{" "}
          <Link to={taskUrl(tid, "overview")}>edit</Link>
        </p>
        {gaps.length > 0 && (
          <div
            role="note"
            aria-label="blockers"
            data-field="gaps"
          >
            <strong>evidence gaps &amp; blockers:</strong> {gaps.join("; ")}
          </div>
        )}
        <p data-field="next-action">
          <strong>next authorized action:</strong>{" "}
          {next.to ? <Link to={next.to}>{next.label}</Link> : next.label}
        </p>
      </header>
      <GroupBody task={task} group={group} view={view} />
    </div>
  );
}

/** Task workspace shell: primary group nav + per-group subview nav,
 * both URL-driven (path segment + ?view=) so deep links, refresh and
 * back restore context (PAR-09). Group/subview come from the route;
 * TaskPage validates the group segment. */
export function TaskWorkspace({ taskId }: { taskId: string }) {
  const { group } = useParams();
  const [searchParams] = useSearchParams();
  if (!isGroup(group)) {
    return <Navigate to={taskUrl(taskId, "overview")} replace />;
  }
  const subviews = SUBVIEWS[group];
  const rawView = searchParams.get("view");
  const view = subviews.some((v) => v.key === rawView)
    ? rawView
    : defaultView(group);
  return (
    <div>
      <nav aria-label="task sections">
        {GROUPS.map((g) => (
          <NavLink
            key={g.key}
            to={taskUrl(taskId, g.key, defaultView(g.key))}
            className={({ isActive }) =>
              isActive ? "cs-tab cs-tab--active" : "cs-tab"
            }
          >
            {g.label}
          </NavLink>
        ))}
      </nav>
      {subviews.length > 0 && (
        <nav aria-label="section views">
          {subviews.map((v) => (
            <Link
              key={v.key}
              to={taskUrl(taskId, group, v.key)}
              className={view === v.key ? "cs-tab cs-tab--active" : "cs-tab"}
              aria-current={view === v.key ? "page" : undefined}
            >
              {v.label}
            </Link>
          ))}
        </nav>
      )}
      <Suspense fallback={<LoadingState label="loading task…" />}>
        <TaskDetail taskId={taskId} group={group} view={view} />
      </Suspense>
      <p>
        <Link to="/projects">back to projects</Link>
      </p>
    </div>
  );
}
