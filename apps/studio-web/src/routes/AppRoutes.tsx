import { Suspense, useEffect, useState, type ReactNode } from "react";
import { Component } from "react";
import { RelayEnvironmentProvider, useLazyLoadQuery } from "react-relay";
import {
  Link,
  NavLink,
  Route,
  BrowserRouter as Router,
  Routes,
  useLocation,
  useParams,
} from "react-router";

import {
  EmptyState,
  ErrorState,
  ForbiddenState,
  LoadingState,
} from "../components";
import { EvidencePanel } from "../features/evidence/EvidencePanel";
import { QualityPanel } from "../features/evidence/quality/QualityPanel";
import { ComputePanel } from "../features/compute/ComputePanel";
import { FallbackPanel } from "../features/compute/fallback/FallbackPanel";
import { ImportReview } from "../features/imports/ImportReview";
import { ExportReviewPanel } from "../features/privacy/export-review/ExportReviewPanel";
import { LabPage } from "../features/lab/plans/LabPage";
import { ModelsPanel } from "../features/learning/models/ModelsPanel";
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

type QueryFailureKind = "auth" | "forbidden" | "not_found" | "unknown";

type WireError = { message?: unknown; extensions?: { code?: unknown } };

/** Relay throws a RelayError for GraphQL failures; `error.source.errors`
 * carries the server's raw `errors[]`, whose `extensions.code` holds
 * the §8.3 typed code (DomainErrorExtensions). Message text is the
 * fallback classifier for errors that carry no code. */
function wireErrors(error: unknown): WireError[] {
  const source = (error as { source?: { errors?: unknown } } | null)?.source;
  return Array.isArray(source?.errors) ? (source.errors as WireError[]) : [];
}

function wireCodes(error: unknown): string[] {
  return wireErrors(error)
    .map((e) => e?.extensions?.code)
    .filter((c): c is string => typeof c === "string" && c.length > 0);
}

function queryErrorMessages(error: unknown): string[] {
  const messages = wireErrors(error)
    .map((e) => e?.message)
    .filter((m): m is string => typeof m === "string" && m.length > 0);
  if (messages.length === 0 && error instanceof Error && error.message) {
    messages.push(error.message);
  }
  return messages;
}

function classifyQueryError(error: unknown): QueryFailureKind {
  const codes = new Set(wireCodes(error));
  if (codes.has("UNAUTHENTICATED")) return "auth";
  if (codes.has("FORBIDDEN")) return "forbidden";
  if (codes.has("NOT_FOUND") || codes.has("VALIDATION")) return "not_found";
  // Code-less failures (bad GlobalID coercion, pre-strawberry errors)
  // still classify by their message when it's specific enough.
  const text = queryErrorMessages(error).join("\n");
  if (/\bUNAUTHENTICATED\b/.test(text)) return "auth";
  if (/\bFORBIDDEN\b/.test(text)) return "forbidden";
  if (/\b(NOT_FOUND|VALIDATION)\b/.test(text) || /GlobalID|base64/i.test(text)) {
    return "not_found";
  }
  return "unknown";
}

function queryErrorDetail(error: unknown): string {
  return queryErrorMessages(error).join("; ") || "unknown error";
}

/** Shell-level error boundary: only an UNAUTHENTICATED failure renders
 * the signed-out copy — any other query failure is reported honestly
 * instead of lying about the session (CS-1201). */
class QueryBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    const { error } = this.state;
    if (error == null) return this.props.children;
    const kind = classifyQueryError(error);
    if (kind === "auth") {
      return <ErrorState title="Not signed in" detail="Sign in to continue." />;
    }
    if (kind === "forbidden") return <ForbiddenState />;
    return <ErrorState detail={queryErrorDetail(error)} />;
  }
}

/** Fallback review boundary: the runId is user/URL input, so an
 * unknown or malformed run is an empty state — never the signed-out
 * copy for a signed-in user (CS-1201). */
class FallbackQueryBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    const { error } = this.state;
    if (error == null) return this.props.children;
    switch (classifyQueryError(error)) {
      case "auth":
        return (
          <ErrorState title="Not signed in" detail="Sign in to continue." />
        );
      case "forbidden":
        return <ForbiddenState />;
      case "not_found":
        return <EmptyState title="Run not found." />;
      default:
        return <ErrorState detail={queryErrorDetail(error)} />;
    }
  }
}

/** Persistent navigation (§22.1). Research chat is a task surface,
 * not the app shell. */
/** Persistent navigation (§22.1): every entry must resolve to a real
 * surface — a nav link that 404s is a defect, not a placeholder
 * (CS-1201). Materials work lives inside task flows and no settings
 * surface exists, so those links were removed rather than stubbed. */
const NAV = [
  { to: "/projects", label: "Projects" },
  { to: "/imports", label: "Imports" },
  { to: "/evidence", label: "Evidence" },
  { to: "/lab", label: "Lab" },
  { to: "/models", label: "Models & Learning" },
  { to: "/compute", label: "Compute" },
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

function ModelsPage() {
  return (
    <div>
      <h1>model registry</h1>
      <ModelsPanel taskId={null} />
    </div>
  );
}

/** `/compute/fallback/:runId` carries a Relay GlobalID
 * (`base64(Run:<uuid>)`); a param that cannot decode to one is an
 * invalid id — render not-found without issuing the query. */
const RUN_GLOBAL_ID = /^Run:[0-9a-fA-F]{8}-[0-9a-fA-F-]{27}$/;

function isRunGlobalId(raw: string): boolean {
  try {
    return RUN_GLOBAL_ID.test(atob(raw));
  } catch {
    return false;
  }
}

function FallbackPage() {
  const { runId = "" } = useParams();
  const decoded = decodeURIComponent(runId);
  if (!isRunGlobalId(decoded)) {
    return <EmptyState title="Run not found." />;
  }
  return (
    <FallbackQueryBoundary>
      <Suspense fallback={<LoadingState label="loading fallback review…" />}>
        <FallbackPanel runId={decoded} />
      </Suspense>
    </FallbackQueryBoundary>
  );
}

function ExportReviewPage() {
  const { proposalId = "" } = useParams();
  return <ExportReviewPanel proposalId={decodeURIComponent(proposalId)} />;
}

function ShellContent() {
  // Keyed by pathname so a failed query on one page does not wedge
  // every other route — navigating away remounts the boundary (CS-1201).
  const { pathname } = useLocation();
  return (
    <QueryBoundary key={pathname}>
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
          <Route path="/models" element={<ModelsPage />} />
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
    </QueryBoundary>
  );
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
                <AppShell>
                  <ShellContent />
                </AppShell>
              </RelayEnvironmentProvider>
            )
          }
        />
      </Routes>
    </Router>
  );
}
