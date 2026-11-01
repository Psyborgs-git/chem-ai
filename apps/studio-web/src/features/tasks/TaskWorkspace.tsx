/** Task workspace (§22.1, PAR-09): the six approved primary groups —
 * overview, research, candidates, experiments, evidence, decisions —
 * map the existing panels; learning, analysis and run surfaces stay
 * reachable under "advanced" through progressive disclosure, never
 * deleted. Group and subview are URL state (/tasks/:id/:group?view=x)
 * so refresh, back and deep links restore the exact context. The
 * context header keeps objective, selected contract revision,
 * evidence gaps and the next authorized action visible — every field
 * is read from the task query, nothing decorative. */
import { Suspense, useRef, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";
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
import { CalculationPanel } from "../runs/CalculationPanel";
import { TaskOverview } from "./TaskOverview";
import { CloseoutPanel } from "./closeout/CloseoutPanel";
import { DecisionsPanel } from "./report/DecisionsPanel";
import { TaskReportPanel } from "./report/TaskReportPanel";
import { TaskDetailQuery } from "./operations";
import { Button } from "../../components/atoms/Button";
import { StudioIcon } from "../../components/layout/StudioLayout";
import { ChemistryArt } from "../../components/layout/ChemistryArt";
import { TaskTransitionMutation } from "./closeout/operations";
import type { tasksCloseoutTransitionMutation } from "../../__generated__/tasksCloseoutTransitionMutation.graphql";

import type { tasksTaskDetailQuery } from "../../__generated__/tasksTaskDetailQuery.graphql";
import { GROUPS, SUBVIEWS, defaultView, isGroup, taskUrl, type GroupKey } from "./navigation";
export { GROUPS, SUBVIEWS, defaultView, isGroup, taskUrl, type GroupKey } from "./navigation";

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
      label: "Reassess changed evidence",
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
        label: "Read the final report",
        to: taskUrl(tid, "decisions", "report"),
      };
    case "awaiting_review":
      return {
        label: "Review evidence and decide",
        to: taskUrl(tid, "decisions", "closeout"),
      };
    case "cancelled":
      return { label: "This task is cancelled" };
    case "paused":
      return { label: "Resume when you are ready" };
    case "draft":
      if (!contractStatus) {
        return { label: "Define success criteria", to: `${taskUrl(tid, "overview")}?edit=criteria` };
      }
      if (contractStatus === "draft") {
        return {
          label: "Finish and freeze your criteria",
          to: `${taskUrl(tid, "overview")}?edit=criteria`,
        };
      }
      if (!hasCandidate) {
        return { label: "Add a candidate", to: taskUrl(tid, "candidates") };
      }
      return {
        label: "Start your research when you are ready",
      };
    default:
      if (!contractStatus || contractStatus === "draft") return { label: !contractStatus ? "Define success criteria" : "Finish and freeze your criteria", to: `${taskUrl(tid, "overview")}?edit=criteria` };
      if (!hasCandidate) {
        return { label: "Add a candidate", to: taskUrl(tid, "candidates") };
      }
      if (!hasAccepted) {
        return {
          label: "Review a candidate",
          to: taskUrl(tid, "candidates"),
        };
      }
      if (!hasApprovedPlan) {
        return {
          label: "Plan an experiment",
          to: taskUrl(tid, "experiments"),
        };
      }
      return {
        label: "Record results and review the evidence",
        to: taskUrl(tid, "experiments", "results"),
      };
  }
}

function GroupBody({
  task,
  group,
  view,
  contract,
  onCriteriaSaved,
}: {
  task: TaskNode;
  group: GroupKey;
  view: string | null;
  contract: { revision: number; status: string; payload?: unknown } | null;
  onCriteriaSaved: () => void;
}) {
  const tid = task.id as string;
  const workflowState = task.workflowState ?? "unknown";
  switch (group) {
    case "overview":
      return <TaskOverview taskId={tid} workflowState={workflowState} contract={contract} onCriteriaSaved={onCriteriaSaved} />;
    case "research":
      return (
        <section aria-label="Task research" data-task-view="research">
          <ResearchPanel taskId={tid} />
        </section>
      );
    case "candidates":
      return (
        <section aria-label="Task candidates" data-task-view="candidates">
          <CandidatePanel taskId={tid} />
        </section>
      );
    case "experiments":
      if (view === "calculations") {
        return <section aria-label="Task calculations"><CalculationPanel taskId={tid} workflowState={workflowState} /></section>;
      }
      return view === "results" ? (
        <section aria-label="Task results" data-task-view="results">
          <ResultsPanel taskId={tid} />
        </section>
      ) : (
        <section aria-label="Task experiment plans" data-task-view="plans">
          <PlansPanel taskId={tid} />
        </section>
      );
    case "evidence":
      return view === "quality" ? (
        <section aria-label="Task source quality" data-task-view="quality">
          <QualityPanel />
        </section>
      ) : (
        <section aria-label="Task sources" data-task-view="evidence">
          <EvidencePanel embedded />
        </section>
      );
    case "decisions":
      if (view === "closeout") {
        return (
          <section aria-label="Task review" data-task-view="closeout">
            <h2>Review &amp; decide</h2>
            <CloseoutPanel taskId={tid} workflowState={workflowState} />
          </section>
        );
      }
      if (view === "report") {
        return (
          <section aria-label="Task report" data-task-view="report">
              <TaskReportPanel taskId={tid} />
          </section>
        );
      }
      return (
        <section aria-label="Task decision history" data-task-view="decisions">
          <DecisionsPanel taskId={tid} />
        </section>
      );
    case "advanced":
      switch (view) {
        case "runs":
          return (
            <section aria-label="Task run history" data-task-view="runs">
              <h2>Run history</h2>
              <RunsPanel taskId={tid} />
            </section>
          );
        case "datasets":
          return (
            <section aria-label="Task datasets" data-task-view="datasets">
                  <DatasetsPanel taskId={tid} />
            </section>
          );
        case "training":
          return (
            <section aria-label="Task training" data-task-view="training">
                  <TrainingPanel taskId={tid} />
            </section>
          );
        case "models":
          return (
            <section aria-label="Task models" data-task-view="models">
                  <ModelsPanel taskId={tid} />
            </section>
          );
        case "evaluations":
          return (
            <section aria-label="Task evaluations" data-task-view="evaluations">
              <EvaluationsPanel taskId={tid} />
            </section>
          );
        case "optimization":
          return task.optimization ? (
            <section aria-label="Task optimization" data-task-view="optimization">
              <OptimizationPanel taskRef={task.optimization} />
            </section>
          ) : null;
        case "analysis":
          return task.analysis ? (
            <section aria-label="Task reference analysis" data-task-view="analysis">
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

const GROUP_ICONS: Record<GroupKey, string> = { overview: "home", research: "models", candidates: "materials", experiments: "lab", evidence: "imports", decisions: "evidence", advanced: "compute" };

function TaskNavigation({ taskId, group, view, targetKind }: { taskId: string; group: GroupKey; view: string | null; targetKind?: string | null }) {
  const tools = useRef<HTMLDetailsElement>(null);
  const subviews = group === "advanced" ? [] : SUBVIEWS[group];
  return <div className="cs-workbench-navigation">
    <nav aria-label="task sections">
      {GROUPS.filter((item) => item.key !== "advanced").map((item) => <NavLink key={item.key} to={taskUrl(taskId, item.key, item.key === "experiments" && targetKind === "molecule" ? "calculations" : defaultView(item.key))} className={({ isActive }) => isActive ? "cs-tab cs-tab--active" : "cs-tab"}><StudioIcon name={GROUP_ICONS[item.key]} />{item.label}</NavLink>)}
    </nav>
    <details ref={tools} className={`cs-workbench-tools${group === "advanced" ? " is-current" : ""}`} onKeyDown={(event) => { if (event.key === "Escape") { tools.current?.removeAttribute("open"); tools.current?.querySelector("summary")?.focus(); } }}>
      <summary><StudioIcon name="compute" />Tools <span aria-hidden="true">⌄</span></summary>
      <nav aria-label="task tools">{SUBVIEWS.advanced.map((item) => <Link key={item.key} to={taskUrl(taskId, "advanced", item.key)} aria-current={group === "advanced" && view === item.key ? "page" : undefined} onClick={() => tools.current?.removeAttribute("open")}>{item.label}<span aria-hidden="true">↗</span></Link>)}</nav>
    </details>
    {subviews.length > 0 && <nav aria-label="section views">{subviews.map((item) => <Link key={item.key} to={taskUrl(taskId, group, item.key)} className={view === item.key ? "cs-tab cs-tab--active" : "cs-tab"} aria-current={view === item.key ? "page" : undefined}>{item.label}</Link>)}</nav>}
  </div>;
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
  const [fetchKey, setFetchKey] = useState(0);
  const data = useLazyLoadQuery<tasksTaskDetailQuery>(TaskDetailQuery, {
    id: taskId,
    includeOptimization: group === "advanced" && view === "optimization",
    includeAnalysis: group === "advanced" && view === "analysis",
  }, { fetchKey, fetchPolicy: fetchKey > 0 ? "network-only" : "store-or-network" });
  const [transition, transitioning] = useMutation<tasksCloseoutTransitionMutation>(TaskTransitionMutation);
  const [transitionError, setTransitionError] = useState<string | null>(null);
  const startPending = useRef(false);
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

  const accepted = candidateStatuses.filter((status) => status === "accepted_for_research").length;
  const approved = planStatuses.filter((status) => status === "approved").length;
  const phase = workflowState === "closed" || workflowState === "awaiting_review" ? "review" : !contract || contract.status === "draft" ? "scope" : accepted === 0 ? "candidates" : "test";
  const workflow = [
    { key: "scope", label: "Scope", kind: "research" as const, to: taskUrl(tid, "overview"), detail: contract?.status === "frozen" ? "Criteria frozen" : contract ? "Criteria in draft" : "Define success", done: contract?.status === "frozen" },
    { key: "candidates", label: "Candidates", kind: "molecule" as const, to: taskUrl(tid, "candidates"), detail: candidateStatuses.length ? `${accepted} accepted · ${candidateStatuses.length} total` : "Build your shortlist", done: accepted > 0 },
    { key: "test", label: "Test & calculate", kind: "experiment" as const, to: taskUrl(tid, "experiments", "calculations"), detail: planStatuses.length ? `${approved} approved · ${planStatuses.length} plans` : "Collect evidence", done: approved > 0 },
    { key: "review", label: "Review", kind: "sources" as const, to: taskUrl(tid, "decisions", "closeout"), detail: workflowState === "closed" ? "Decision recorded" : workflowState === "awaiting_review" ? "Ready for review" : "Make a supported decision", done: workflowState === "closed" },
  ];
  const start = () => {
    if (transitioning || startPending.current) return;
    startPending.current = true; setTransitionError(null);
    transition({ variables: { input: { taskId: tid, toState: "active" } },
      onCompleted: (response) => { startPending.current = false; const errors = response.taskTransition.errors; if (errors.length) setTransitionError(errors.map((error) => error.message).join("; ")); },
      onError: (error) => { startPending.current = false; setTransitionError(error.message); },
    });
  };
  return (
    <div className="cs-task-workbench">
      <header className="cs-task-context cs-workbench-header">
        <nav className="cs-workbench-breadcrumb" aria-label="Task breadcrumb"><Link to="/projects">Projects</Link><span aria-hidden="true">/</span>{task.project && <Link to={`/projects/${encodeURIComponent(task.project.id)}`}>{task.project.name}</Link>}</nav>
        <div className="cs-workbench-title-row"><div><h1 className="cs-workbench-title">{task.title}</h1>{task.objective && <p className="cs-workbench-goal" data-field="objective">{task.objective}</p>}</div><StatusIndicator status={workflowState as Parameters<typeof StatusIndicator>[0]["status"]} /></div>
        <div className="cs-workbench-next" data-field="next-action"><div><span className="cs-eyebrow">Your next step</span>{next.to ? <Link to={next.to}>{next.label}<StudioIcon name="arrow" /></Link> : <span>{next.label}</span>}</div><div className="cs-actions">
          {(workflowState === "draft" || workflowState === "paused") && <Button variant="primary" disabled={transitioning} onClick={start}>{transitioning ? "Starting…" : workflowState === "paused" ? "Resume task" : "Start task"}</Button>}
          <Link className={`cs-btn ${workflowState === "active" ? "cs-btn--primary" : "cs-btn--secondary"}`} to={taskUrl(tid, "experiments", "calculations")}>{workflowState === "closed" || workflowState === "cancelled" ? "View calculations" : "Run calculation"}</Link>
        </div></div>
        {transitionError && <p role="alert" className="cs-field__error">{transitionError}</p>}
        <details className="cs-workbench-details"><summary>Task details {gaps.length > 0 && <span className="cs-count">{gaps.length} open input{gaps.length === 1 ? "" : "s"}</span>}</summary><div className="cs-workbench-metadata">
          <p><Badge tone="info">{task.mode?.replaceAll("_", " ")}</Badge> <Badge tone="neutral">Cycle {task.evaluationCycle}</Badge></p>
          <p data-field="contract-state"><strong>Success criteria:</strong> {contract ? `rev ${contract.revision} (${contract.status})` : "none drafted"} <Link to={`${taskUrl(tid, "overview")}?edit=criteria`}>Edit criteria</Link></p>
          {gaps.length > 0 && <div role="note" aria-label="blockers" data-field="gaps"><strong>Open inputs & evidence gaps:</strong> {gaps.join("; ")}</div>}
        </div></details>
      </header>
      <ol className="cs-workflow-path" aria-label="Research path">{workflow.map((step) => <li key={step.key} data-state={step.done ? "recorded" : "open"} aria-current={phase === step.key ? "step" : undefined}><Link to={step.to}><ChemistryArt kind={step.kind} className="cs-workflow-art" /><span><strong>{step.label}</strong><small>{step.detail}</small></span>{step.done && <span className="cs-workflow-check" aria-label="Recorded">✓</span>}</Link></li>)}</ol>
      <TaskNavigation taskId={tid} group={group} view={view} targetKind={task.targetKind} />
      <GroupBody task={task} group={group} view={view} contract={contract} onCriteriaSaved={() => setFetchKey((key) => key + 1)} />
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
    <Suspense fallback={<LoadingState label="loading task…" />}>
      <TaskDetail taskId={taskId} group={group} view={view} />
    </Suspense>
  );
}
