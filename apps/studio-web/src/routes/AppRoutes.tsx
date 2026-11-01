import { Suspense, lazy, useEffect, useRef, useState, type ReactNode } from "react";
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
  useSearchParams,
} from "react-router";

import {
  EmptyState,
  ErrorState,
  ForbiddenState,
  LoadingState,
} from "../components";
import {
  FirstRunScreen,
  SignInScreen,
} from "../features/auth/AuthScreens";
import { InlineFinding } from "../components/molecules/InlineFinding";
import { PageHeader, StudioIcon, humanize } from "../components/layout/StudioLayout";
import { CreateSheet } from "../components/layout/CreateSheet";
import { WorkspaceFinder } from "../components/layout/WorkspaceFinder";
import { ResearchSheet } from "../features/tasks/ResearchSheet";
import { BrandMark } from "../components/layout/BrandMark";
import { ChemistryArt } from "../components/layout/ChemistryArt";
import { AgentSidebar } from "../features/agent/AgentSidebar";
import { HomePage } from "../features/home/HomePage";
import {
  ProjectListQuery,
  ProjectTasksQuery,
} from "../features/tasks/operations";
import { ProjectCreateForm } from "../features/tasks/ProjectCreateForm";
import {
  getRelayEnvironment,
  resetRelayEnvironment,
} from "../relay/environment";
import {
  authSignOut,
  fetchSetupNeeded,
  probeViewer,
} from "../relay/network";
import { writeTheme } from "../theme";

import type { tasksProjectListQuery } from "../__generated__/tasksProjectListQuery.graphql";
import type { tasksProjectTasksQuery } from "../__generated__/tasksProjectTasksQuery.graphql";


// Keep first-run entry light; scientific surfaces load when opened.
const RunDetailsPage = lazy(() => import("../features/runs/RunDetailsPage").then((module) => ({ default: module.RunDetailsPage })));
const EvidencePanel = lazy(() => import("../features/evidence/EvidencePanel").then((module) => ({ default: module.EvidencePanel })));
const QualityPanel = lazy(() => import("../features/evidence/quality/QualityPanel").then((module) => ({ default: module.QualityPanel })));
const ComputePanel = lazy(() => import("../features/compute/ComputePanel").then((module) => ({ default: module.ComputePanel })));
const FallbackPanel = lazy(() => import("../features/compute/fallback/FallbackPanel").then((module) => ({ default: module.FallbackPanel })));
const ImportReview = lazy(() => import("../features/imports/ImportReview").then((module) => ({ default: module.ImportReview })));
const ExportReviewPanel = lazy(() => import("../features/privacy/export-review/ExportReviewPanel").then((module) => ({ default: module.ExportReviewPanel })));
const LabPage = lazy(() => import("../features/lab/plans/LabPage").then((module) => ({ default: module.LabPage })));
const MaterialsPage = lazy(() => import("../features/registry/MaterialsPage").then((module) => ({ default: module.MaterialsPage })));
const ModelsPanel = lazy(() => import("../features/learning/models/ModelsPanel").then((module) => ({ default: module.ModelsPanel })));
const ProvidersPage = lazy(() => import("../features/providers/ProvidersPage").then((module) => ({ default: module.ProvidersPage })));
const NotebooksPage = lazy(() => import("../features/notebooks/NotebooksPage").then((module) => ({ default: module.NotebooksPage })));
const ResearchLibraryPage = lazy(() => import("../features/notebooks/ResearchLibraryPage").then((module) => ({ default: module.ResearchLibraryPage })));
const LocalLearningPage = lazy(() => import("../features/learning/LocalLearningPage").then((module) => ({ default: module.LocalLearningPage })));
const TaskWorkspace = lazy(() => import("../features/tasks/TaskWorkspace").then((module) => ({ default: module.TaskWorkspace })));
const DevComponents = lazy(() => import("./DevComponents").then((module) => ({ default: module.DevComponents })));

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
      // UNAUTHENTICATED mid-session: the sign-in surface replaces the
      // page. The URL is preserved, so a successful sign-in reload
      // returns to the intended destination (PAR-06).
      return <SignInScreen expired />;
    }
    if (kind === "forbidden") return <ForbiddenState />;
    return <ErrorState detail={queryErrorDetail(error)} onRetry={() => window.location.reload()} />;
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
        return <SignInScreen expired />;
      case "forbidden":
        return <ForbiddenState />;
      case "not_found":
        return <EmptyState title="Run not found." />;
      default:
        return <ErrorState detail={queryErrorDetail(error)} onRetry={() => window.location.reload()} />;
    }
  }
}

/** Persistent navigation (§22.1). Research chat is a task surface,
 * not the app shell. */
/** Persistent navigation (§22.1): every entry must resolve to a real
 * surface — a nav link that 404s is a defect, not a placeholder
 * (CS-1201). PAR-07 restored "Materials & Products" now that a real
 * registry surface exists at /materials. */
const NAV = [
  { to: "/", label: "Workspace", icon: "home" },
  { to: "/projects", label: "Projects", icon: "projects" },
  { to: "/notebooks", label: "Notebooks", icon: "notebooks" },
  { to: "/library/research", label: "Research library", icon: "research" },
  { to: "/downloads", label: "Downloads", icon: "imports" },
  { to: "/memory", label: "Research memory", icon: "models" },
  { to: "/materials", label: "Materials & Products", icon: "materials" },
  { to: "/imports", label: "Imports", icon: "imports" },
  { to: "/evidence", label: "Evidence", icon: "evidence" },
  { to: "/lab", label: "Lab", icon: "lab" },
  { to: "/models", label: "Models & Learning", icon: "models" },
  { to: "/learning", label: "Local learning", icon: "models" },
  { to: "/compute", label: "Compute", icon: "compute" },
  { to: "/settings/providers", label: "Providers", icon: "providers" },
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
      aria-label={`Switch to ${next} theme`}
      onClick={() => {
        document.documentElement.dataset.theme = next;
        writeTheme(next);
        setTheme(next);
      }}
    >
      <svg className="cs-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">{theme === "dark" ? <path d="M20 14a8 8 0 0 1-10-10 8 8 0 1 0 10 10Z" /> : <><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2"/></>}</svg>{theme === "dark" ? "Dark" : "Light"}
    </button>
  );
}

/** Sign-out ends the server session, drops the identity-scoped Relay
 * store (§8.2 resetRelayEnvironment) and hard-reloads to the signed-out
 * route — the reload is the authoritative invalidation, the reset
 * covers the gap before it lands (PAR-06). */
function SignOutControl() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <>
      <button
        type="button"
        className="cs-btn cs-btn--ghost"
        disabled={pending}
        onClick={() => {
          setPending(true);
          setError(null);
          void authSignOut().then((res) => {
            if (res.ok) {
              resetRelayEnvironment();
              window.location.assign("/");
              return;
            }
            setPending(false);
            setError(res.message);
          });
        }}
      >
        {pending ? "signing out…" : "Sign out"}
      </button>
      {error && <InlineFinding severity="error" message={error} />}
    </>
  );
}

function AppShell({
  displayName,
  children,
}: {
  displayName: string;
  children: ReactNode;
}) {
  const { pathname } = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  const [finderOpen, setFinderOpen] = useState(false);
  useEffect(() => { const openFinder = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setFinderOpen((value) => !value); } }; document.addEventListener("keydown", openFinder); return () => document.removeEventListener("keydown", openFinder); }, []);
  const sidebarRef = useRef<HTMLElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);
  const closeNav = () => { setNavOpen(false); menuRef.current?.focus(); };
  const location = pathname.startsWith("/tasks/") ? "Research task"
    : pathname.startsWith("/runs/") ? "Calculation details"
    : pathname.startsWith("/privacy/") ? "Export review"
    : NAV.find((n) => n.to !== "/" && pathname.startsWith(n.to))?.label ?? "Workspace";
  useEffect(() => { setNavOpen(false); }, [pathname]);
  useEffect(() => {
    if (!navOpen || !window.matchMedia("(max-width: 767px)").matches) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    sidebarRef.current?.querySelector<HTMLButtonElement>(".cs-sidebar-close")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setNavOpen(false); menuRef.current?.focus(); }
      if (event.key !== "Tab") return;
      const controls = [...(sidebarRef.current?.querySelectorAll<HTMLElement>('a[href], button:not([disabled])') ?? [])].filter((node) => node.getClientRects().length > 0);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = previousOverflow; };
  }, [navOpen]);
  return (
    <div className="cs-shell cs-shell--workspace">
      <a className="cs-skip-link" href="#main">
        Skip to content
      </a>
      <WorkspaceFinder open={finderOpen} onClose={() => setFinderOpen(false)} />
      <aside ref={sidebarRef} className={`cs-sidebar${navOpen ? " is-open" : ""}`} aria-label="Workspace navigation">
        <Link to="/" className="cs-shell__brand">
          <span className="cs-brand-mark"><BrandMark size={35} className="cs-brand-logo" /></span> Chemistry Studio
        </Link>
        <button type="button" className="cs-icon-btn cs-sidebar-close" aria-label="Close navigation" onClick={closeNav}><StudioIcon name="close" /></button>
        <div className="cs-sidebar__workspace"><span className="cs-live-dot"/><span>Local workspace</span></div>
        <Link to="/?new=research" className="cs-sidebar__new" onClick={() => setNavOpen(false)}><span aria-hidden="true">＋</span> New research</Link>
        <nav aria-label="primary" id="primary-navigation">
          {[
            { label: "YOUR WORK", destinations: ["/", "/projects", "/notebooks", "/lab"] },
            { label: "REFERENCE LIBRARY", destinations: ["/library/research", "/downloads", "/memory", "/materials", "/evidence", "/imports"] },
            { label: "TOOLS", destinations: ["/compute", "/learning", "/models", "/settings/providers"] },
          ].map((group) => <div className="cs-navigation-group" key={group.label}><div className="cs-sidebar__label">{group.label}</div>{group.destinations.map((destination) => {
            const item = NAV.find((entry) => entry.to === destination)!;
            return <NavLink key={item.to} to={item.to} end={item.to === "/"} onClick={() => setNavOpen(false)}><StudioIcon name={item.icon}/>{item.label}</NavLink>;
          })}</div>)}
        </nav>
        <div className="cs-sidebar__footer"><span className="cs-sidebar__footer-mark">✦</span><strong>Questions become evidence.</strong><span>One connected research workspace.</span></div>
      </aside>
      <button type="button" className="cs-sidebar-backdrop" aria-label="Dismiss navigation" onClick={closeNav} tabIndex={-1} />
      <header className="cs-shell__header">
        <button ref={menuRef} type="button" className="cs-icon-btn cs-menu-button" aria-label="Open navigation" aria-expanded={navOpen} aria-controls="primary-navigation" onClick={() => setNavOpen(true)}><StudioIcon name="menu" /></button>
        <div className="cs-shell__location"><span aria-hidden="true">Studio /</span><span>{location}</span></div>
        <button className="cs-workspace-finder" type="button" onClick={() => setFinderOpen(true)}><svg className="cs-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/></svg><span>Find your work</span><kbd>⌘ K</kbd></button>
        <span className="cs-shell__session"><span className="cs-avatar" aria-hidden="true">{displayName.split(/\s+/).map((name) => name[0]).slice(0,2).join("")}</span>{displayName}</span>
        <SignOutControl />
        <ThemeToggle />
        <AgentSidebar />
      </header>
      <main id="main" tabIndex={-1}>
        <div className="cs-content">{children}</div>
      </main>
    </div>
  );
}

function ProjectsPage() {
  const data = useLazyLoadQuery<tasksProjectListQuery>(ProjectListQuery, {}, { fetchPolicy: "store-and-network" });
  const projects = data.projects.edges.map((edge) => edge.node);
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(params.get("new") === "project");
  const close = () => { setCreating(false); const next = new URLSearchParams(params); next.delete("new"); setParams(next, {replace:true}); };
  return <div className="cs-projects-page">
    <PageHeader eyebrow="Your work" title="Projects" description="Keep each research question and its evidence together." actions={<button className="cs-btn cs-btn--primary" onClick={() => setCreating(true)}><span aria-hidden="true">＋</span> New project</button>} />
    <CreateSheet open={creating} onClose={close} title="New project" description="Give this research a name. Everything else can wait."><ProjectCreateForm /></CreateSheet>
    <ResearchSheet open={params.get("new") === "research"} onClose={close} projects={projects} />
    {projects.length ? <ul className="cs-project-grid">{projects.map((project) => <li key={project.id}><Link to={`/projects/${encodeURIComponent(project.id)}`}><div className="cs-project-card__art"><ChemistryArt kind="research"/><span className="cs-count">{humanize(project.status)}</span></div><h2>{project.name}</h2><span className="cs-project-card__open">Open project <StudioIcon name="arrow"/></span></Link></li>)}</ul> : <div className="cs-friendly-empty"><ChemistryArt kind="research"/><h2>A home for your next question</h2><p>A project brings your tasks, candidates, experiments, and evidence together.</p><button className="cs-btn cs-btn--primary" onClick={() => setCreating(true)}>Create first project</button></div>}
  </div>;
}

function ProjectDetailPage() {
  const { projectId = "" } = useParams();
  const data = useLazyLoadQuery<tasksProjectTasksQuery>(ProjectTasksQuery, { projectId });
  const tasks = data.projectTasks.edges.map((edge) => edge.node);
  const project = data.node?.__typename === "Project" ? data.node : null;
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(params.get("new") === "task");
  const close = () => { setCreating(false); const next = new URLSearchParams(params); next.delete("new"); setParams(next,{replace:true}); };
  return <div className="cs-projects-page">
    <Link className="cs-project-back" to="/projects">← Projects</Link>
    <PageHeader eyebrow="Research project" title={project?.name ?? "Project"} description="Move from a question to evidence, one research task at a time." actions={<button className="cs-btn cs-btn--primary" onClick={() => setCreating(true)}><span aria-hidden="true">＋</span> New research task</button>} />
    <ResearchSheet open={creating} onClose={close} projectId={projectId} />
    {tasks.length ? <ul className="cs-recent-work">{tasks.map((task) => <li key={task.id}><Link to={`/tasks/${encodeURIComponent(task.id)}`}><span className="cs-record-symbol"><StudioIcon name="lab"/></span><div><strong>{task.title}</strong><span>{humanize(task.mode)}{task.unresolvedInputs.length ? " · More context needed" : ""}</span></div><span className="cs-count">{humanize(task.workflowState)}</span><StudioIcon name="arrow"/></Link></li>)}</ul> : <div className="cs-friendly-empty"><ChemistryArt kind="research"/><h2>What would you like to find out?</h2><p>Start with a question. Add the scientific details as the research takes shape.</p><button className="cs-btn cs-btn--primary" onClick={() => setCreating(true)}>Start first task</button></div>}
  </div>;
}

function TaskPage() {
  const { taskId = "" } = useParams();
  return <TaskWorkspace taskId={decodeURIComponent(taskId)} />;
}

function ModelsPage() {
  return (
    <div>
      <PageHeader eyebrow="Models & learning" title="Model registry" description="Review versioned releases, serving pointers and the evidence behind each model decision." actions={<Link className="cs-btn cs-btn--primary" to="/learning">Open local learning</Link>} />
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
          {/* PAR-09: the group segment carries the workspace section
             so deep links, refresh and back restore context; an
             unknown group redirects to overview inside the workspace. */}
          <Route path="/tasks/:taskId/:group" element={<TaskPage />} />
          <Route path="/materials" element={<MaterialsPage />} />
          <Route path="/imports" element={<ImportReview />} />
          <Route path="/evidence" element={<EvidencePanel />} />
          <Route
            path="/evidence/quality"
            element={<><PageHeader eyebrow="Evidence stewardship" title="Source quality" description="Inspect extraction coverage, flags and source revocations. Quality stays visible as individual findings and counts." /><QualityPanel /></>}
          />
          <Route path="/lab" element={<LabPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/learning" element={<LocalLearningPage />} />
          <Route path="/notebooks" element={<NotebooksPage />} />
          <Route path="/library/research" element={<ResearchLibraryPage />} />
          <Route path="/downloads" element={<ResearchLibraryPage view="downloads" />} />
          <Route path="/memory" element={<ResearchLibraryPage view="memory" />} />
          <Route path="/compute" element={<ComputePanel />} />
          <Route path="/settings/providers" element={<ProvidersPage />} />
          <Route path="/runs/:runId" element={<RunDetailsPage />} />
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

/** Entry gate (PAR-06): setup → first-run owner bootstrap; no session
 * → sign-in; session → the app. Identity is probed via the GraphQL
 * viewer query so the shell never mounts for a signed-out user. */
type SetupState =
  | { kind: "loading" }
  | { kind: "setup" }
  | { kind: "signed_out" }
  | { kind: "signed_in"; displayName: string }
  | { kind: "error"; message: string };

export function AppRoutes() {
  const [state, setState] = useState<SetupState>({ kind: "loading" });
  useEffect(() => {
    let cancelled = false;
    fetchSetupNeeded()
      .then(async (setupNeeded) => {
        if (setupNeeded) return { kind: "setup" } as SetupState;
        const viewer = await probeViewer();
        if (viewer.kind === "signed_in") {
          return {
            kind: "signed_in",
            displayName: viewer.displayName,
          } as SetupState;
        }
        if (viewer.kind === "signed_out") {
          return { kind: "signed_out" } as SetupState;
        }
        return { kind: "error", message: viewer.message } as SetupState;
      })
      .then((next) => {
        if (!cancelled) setState(next);
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
        <Route path="/dev/components" element={<Suspense fallback={<LoadingState label="loading components…" />}><DevComponents /></Suspense>} />
        <Route
          path="*"
          element={
            state.kind === "loading" ? (
              <LoadingState label="checking setup…" />
            ) : state.kind === "error" ? (
              <ErrorState
                title="Backend unreachable"
                detail={state.message}
                onRetry={() => window.location.reload()}
              />
            ) : state.kind === "setup" ? (
              <FirstRunScreen />
            ) : state.kind === "signed_out" ? (
              <SignInScreen />
            ) : (
              <RelayEnvironmentProvider environment={getRelayEnvironment()}>
                <AppShell displayName={state.displayName}>
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
