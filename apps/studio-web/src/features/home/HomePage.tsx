import { Suspense, useEffect, useRef, useState } from "react";
import { useLazyLoadQuery } from "react-relay";
import { Link, useSearchParams } from "react-router";
import { Button } from "../../components/atoms/Button";
import { Badge } from "../../components/atoms/Badge";
import { StudioIcon, humanize } from "../../components/layout/StudioLayout";
import { LoadingState } from "../../components/states/states";
import { ResearchSheet } from "../tasks/ResearchSheet";
import { taskUrl } from "../tasks/navigation";
import { QuickCalculation } from "./QuickCalculation";
import { WorkspaceHomeQuery } from "./operations";
import type { homeWorkspaceQuery } from "../../__generated__/homeWorkspaceQuery.graphql";

function HomeInner() {
  const [refresh, setRefresh] = useState(0);
  const [moleculeOpen, setMoleculeOpen] = useState(false);
  const moleculeRef = useRef<HTMLElement>(null);
  const data = useLazyLoadQuery<homeWorkspaceQuery>(WorkspaceHomeQuery, {}, { fetchPolicy: "store-and-network", fetchKey: refresh });
  const [params, setParams] = useSearchParams();
  const closeResearch = () => { const next = new URLSearchParams(params); next.delete("new"); setParams(next, { replace: true }); };
  useEffect(() => {
    if (params.get("focus") !== "molecule") return;
    setMoleculeOpen(true);
    const next = new URLSearchParams(params); next.delete("focus"); setParams(next, { replace: true });
  }, [params, setParams]);
  useEffect(() => {
    if (!moleculeOpen || !moleculeRef.current) return;
    const focus = () => { const input = moleculeRef.current?.querySelector<HTMLInputElement>("#quick-structure"); if (!input) return false; input.focus(); return true; };
    if (focus()) return;
    const observer = new MutationObserver(() => { if (focus()) observer.disconnect(); });
    observer.observe(moleculeRef.current, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [moleculeOpen]);
  const recent = data.recent.edges.map((edge) => edge.node);
  const pending = data.pendingDecisions.edges.map((edge) => edge.node);
  return <div className="cs-home-simple">
    <ResearchSheet open={params.get("new") === "research"} onClose={closeResearch} projects={data.projects.edges.map((edge) => edge.node)} />
    <header className="cs-home-heading"><div><h1>Your research</h1><p>Pick up your work, or start with a question.</p></div><Button variant="primary" onClick={() => window.dispatchEvent(new CustomEvent("studio-agent-open", { detail: {} }))}>Ask agent</Button></header>
    <nav className="cs-home-quick-grid" aria-label="Start something">
      <Link className="cs-home-quick-action" to="/library/research?focus=search"><StudioIcon name="research" /><span>Find papers</span></Link>
      <Link className="cs-home-quick-action" to="/notebooks?new=notebook"><StudioIcon name="notebooks" /><span>New notebook</span></Link>
      <Link className="cs-home-quick-action" to="/learning?tab=new"><StudioIcon name="models" /><span>Train model</span></Link>
      <button type="button" className="cs-home-quick-action" aria-expanded={moleculeOpen} aria-controls="home-molecule-explorer" onClick={() => setMoleculeOpen(true)}><StudioIcon name="materials" /><span>Explore molecule</span></button>
    </nav>
    <section id="home-molecule-explorer" ref={moleculeRef} className="cs-home-molecule" aria-label="Molecule explorer" hidden={!moleculeOpen}><header><h2>Explore a molecule</h2><Button variant="ghost" aria-label="Close molecule explorer" onClick={() => setMoleculeOpen(false)}><StudioIcon name="close" /></Button></header>{moleculeOpen && <Suspense fallback={<p role="status">Opening molecule explorer…</p>}><QuickCalculation onSaved={() => setRefresh((value) => value + 1)} projects={data.projects.edges.map((edge) => edge.node)} /></Suspense>}</section>
    <div className="cs-home-work"><section className="cs-home-recents" aria-labelledby="recent-work-title"><div className="cs-section-heading"><h2 id="recent-work-title">Recent work</h2><Link to="/projects">All projects</Link></div>
      {recent.length ? <ul className="cs-recent-work" data-field="recent-tasks">{recent.map((task) => <li key={task.id}><Link to={taskUrl(task.id, "overview")}><div><strong>{task.title}</strong><span>{task.project?.name ?? "Research"} · {task.mode === "discover" ? "Explore" : task.mode === "match_reference" ? "Match a reference" : humanize(task.mode)}</span></div><Badge tone={task.workflowState === "closed" ? "success" : task.workflowState === "awaiting_review" ? "warning" : "neutral"}>{humanize(task.workflowState)}</Badge></Link></li>)}</ul> : <div className="cs-home-empty"><p>No research tasks yet.</p><Link to="/?new=research">Start a research task</Link></div>}
      {recent.length > 0 && <Link className="cs-home-new-task" to="/?new=research">New research task</Link>}
    </section><section className="cs-home-review" aria-labelledby="review-title"><div className="cs-section-heading"><h2 id="review-title">Ready for review</h2>{pending.length > 0 && <span className="cs-count">{pending.length}</span>}</div>{pending.length ? <ul className="cs-review-list" data-field="pending-decisions">{pending.map((task) => <li key={task.id}><Link to={taskUrl(task.id, "decisions", "closeout")}><div><strong>{task.title}</strong><span>{task.project?.name}</span></div><StudioIcon name="arrow" /></Link></li>)}</ul> : <p className="cs-home-empty">No decisions waiting for review.</p>}</section></div>
  </div>;
}

export function HomePage() {
  return <Suspense fallback={<LoadingState label="Opening your workspace…" />}><HomeInner /></Suspense>;
}
