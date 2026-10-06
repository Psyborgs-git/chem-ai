import { Suspense, useEffect, useState, type ReactNode } from "react";
import { Component } from "react";
import { RelayEnvironmentProvider, useLazyLoadQuery } from "react-relay";
import {
  Link,
  NavLink,
  Route,
  BrowserRouter as Router,
  Routes,
  useParams,
} from "react-router";

import { EmptyState, ErrorState, LoadingState } from "../components";
import { EvidencePanel } from "../features/evidence/EvidencePanel";
import { QualityPanel } from "../features/evidence/quality/QualityPanel";
import { ComputePanel } from "../features/compute/ComputePanel";
import { FallbackPanel } from "../features/compute/fallback/FallbackPanel";
import { ImportReview } from "../features/imports/ImportReview";
import { ExportReviewPanel } from "../features/privacy/export-review/ExportReviewPanel";
import { LabPage } from "../features/lab/plans/LabPage";
import { TaskCreateForm } from "../features/tasks/TaskCreateForm";
import { TaskWorkspace } from "../features/tasks/TaskWorkspace";
import {
  ProjectListQuery,
  ProjectTasksQuery,
} from "../features/tasks/operations";
import { getRelayEnvironment } from "../relay/environment";
import { fetchSetupNeeded } from "../relay/network";
import { writeTheme } from "../theme";
import { DevComponents } from "./DevComponents";
import { graphql } from "react-relay";

import type { tasksProjectListQuery } from "../__generated__/tasksProjectListQuery.graphql";
import type { tasksProjectTasksQuery } from "../__generated__/tasksProjectTasksQuery.graphql";
import type { AppViewerQuery as AppViewerQueryType } from "../__generated__/AppViewerQuery.graphql";

const ViewerQuery = graphql`
  query AppViewerQuery {
    viewer {
      id
      displayName
      kind
    }
  }
`;

class QueryBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <ErrorState title="Not signed in" detail="Sign in to continue." />
    ) : (
      this.props.children
    );
  }
}

/** Persistent navigation (§22.1). Research chat is a task surface,
 * not the app shell. */
const NAV = [
  { to: "/projects", label: "Projects" },
  { to: "/materials", label: "Materials & Products" },
  { to: "/imports", label: "Imports" },
  { to: "/evidence", label: "Evidence" },
  { to: "/lab", label: "Lab" },
  { to: "/models", label: "Models & Learning" },
  { to: "/compute", label: "Compute" },
  { to: "/settings", label: "Settings" },
];

function ThemeToggle() {
  const [theme, setTheme] = useState(
    () => document.documentElement.dataset.theme ?? "light",
  );
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      className="cs-btn cs-btn--ghost cs-theme-toggle"
      aria-pressed={theme === "dark"}
      onClick={() => {
        document.documentElement.dataset.theme = next;
        writeTheme(next);
        setTheme(next);
      }}
    >
      theme: {theme}
    </button>
  );
}

function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="cs-shell">
      <a className="cs-skip-link" href="#main">
        Skip to content
      </a>
      <header className="cs-shell__header">
        <Link to="/" className="cs-shell__brand">
          Chemistry Studio
        </Link>
        <nav aria-label="primary">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <ThemeToggle />
      </header>
      <main id="main" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}

function ProjectsPage() {
  const data = useLazyLoadQuery<tasksProjectListQuery>(ProjectListQuery, {});
  const projects = data.projects.edges.map((e) => e.node);
  return (
    <div>
      <h1>Projects</h1>
      {projects.length === 0 ? (
        <EmptyState title="No projects yet." />
      ) : (
        <ul>
          {projects.map((p) => (
            <li key={p.id}>
              <Link to={`/projects/${p.id}`}>{p.name}</Link>{" "}
              <small>({p.slug})</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ProjectDetailPage() {
  const { projectId = "" } = useParams();
  const data = useLazyLoadQuery<tasksProjectTasksQuery>(ProjectTasksQuery, {
    projectId,
  });
  const tasks = data.projectTasks.edges.map((e) => e.node);
  return (
    <div>
      <h1>Project</h1>
      <h2>tasks</h2>
      {tasks.length === 0 ? (
        <EmptyState title="No tasks yet — create one below." />
      ) : (
        <ul>
          {tasks.map((t) => (
            <li key={t.id}>
              <Link to={`/tasks/${t.id}`}>{t.title}</Link>{" "}
              <small>
                {t.mode} · {t.workflowState}
                {t.unresolvedInputs.length > 0 &&
                  ` · blockers: ${t.unresolvedInputs.join(", ")}`}
              </small>
            </li>
          ))}
        </ul>
      )}
      <h2>new task</h2>
      <TaskCreateForm projectId={projectId} />
    </div>
  );
}

function TaskPage() {
  const { taskId = "" } = useParams();
  return <TaskWorkspace taskId={decodeURIComponent(taskId)} />;
}

function FallbackPage() {
  const { runId = "" } = useParams();
  return <FallbackPanel runId={decodeURIComponent(runId)} />;
}

function ExportReviewPage() {
  const { proposalId = "" } = useParams();
  return <ExportReviewPanel proposalId={decodeURIComponent(proposalId)} />;
}

function ViewerStatus() {
  const data = useLazyLoadQuery<AppViewerQueryType>(ViewerQuery, {});
  return <p>Signed in as {data.viewer.displayName}.</p>;
}

function HomePage() {
  return (
    <div>
      <h1>Chemistry Studio</h1>
      <ViewerStatus />
      <p>
        <Link to="/projects">Open projects</Link>
      </p>
    </div>
  );
}

type SetupState =
  | { kind: "loading" }
  | { kind: "ready"; setupNeeded: boolean }
  | { kind: "error"; message: string };

export function AppRoutes() {
  const [state, setState] = useState<SetupState>({ kind: "loading" });
  useEffect(() => {
    let cancelled = false;
    fetchSetupNeeded()
      .then((setupNeeded) => {
        if (!cancelled) setState({ kind: "ready", setupNeeded });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "unknown error",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Router>
      <Routes>
        {/* dev-only showcase — no auth required */}
        <Route path="/dev/components" element={<DevComponents />} />
        <Route
          path="*"
          element={
            state.kind === "loading" ? (
              <LoadingState label="checking setup…" />
            ) : state.kind === "error" ? (
              <ErrorState
                title="Backend unreachable"
                detail={state.message}
              />
            ) : state.setupNeeded ? (
              <EmptyState title="Workspace setup required — an owner account must be created." />
            ) : (
              <RelayEnvironmentProvider environment={getRelayEnvironment()}>
                <QueryBoundary>
                  <AppShell>
                    <Suspense fallback={<LoadingState label="loading…" />}>
                      <Routes>
                        <Route path="/" element={<HomePage />} />
                        <Route path="/projects" element={<ProjectsPage />} />
                        <Route
                          path="/projects/:projectId"
                          element={<ProjectDetailPage />}
                        />
                        <Route path="/tasks/:taskId" element={<TaskPage />} />
                        <Route path="/imports" element={<ImportReview />} />
                        <Route path="/evidence" element={<EvidencePanel />} />
                        <Route
                          path="/evidence/quality"
                          element={<QualityPanel />}
                        />
                        <Route path="/lab" element={<LabPage />} />
                        <Route path="/compute" element={<ComputePanel />} />
                        <Route
                          path="/compute/fallback/:runId"
                          element={<FallbackPage />}
                        />
                        <Route
                          path="/privacy/exports/:proposalId"
                          element={<ExportReviewPage />}
                        />
                        <Route
                          path="*"
                          element={<EmptyState title="Page not found." />}
                        />
                      </Routes>
                    </Suspense>
                  </AppShell>
                </QueryBoundary>
              </RelayEnvironmentProvider>
            )
          }
        />
      </Routes>
    </Router>
  );
}
