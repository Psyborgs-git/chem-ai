import { Suspense, useState } from "react";
import { useLazyLoadQuery } from "react-relay";
import { Link, useSearchParams } from "react-router";
import { ResearchSheet } from "../tasks/ResearchSheet";
import { Badge } from "../../components/atoms/Badge";
import { ChemistryArt } from "../../components/layout/ChemistryArt";
import { StudioIcon, humanize } from "../../components/layout/StudioLayout";
import { LoadingState } from "../../components/states/states";
import { taskUrl } from "../tasks/navigation";
import { QuickCalculation } from "./QuickCalculation";
import { WorkspaceHomeQuery } from "./operations";
import type { homeWorkspaceQuery } from "../../__generated__/homeWorkspaceQuery.graphql";

function HomeInner() {
  const [refresh, setRefresh] = useState(0);
  const data = useLazyLoadQuery<homeWorkspaceQuery>(WorkspaceHomeQuery, {}, { fetchPolicy: "store-and-network", fetchKey: refresh });
  const [params, setParams] = useSearchParams();
  const closeResearch = () => { const next = new URLSearchParams(params); next.delete("new"); setParams(next, {replace:true}); };
  const recent = data.recent.edges.map((edge) => edge.node);
  const pending = data.pendingDecisions.edges.map((edge) => edge.node);
  return <div className="cs-product-home">
    <ResearchSheet open={params.get("new") === "research"} onClose={closeResearch} projects={data.projects.edges.map((edge) => edge.node)} />
    <header className="cs-home-heading"><div><p className="cs-kicker">Your workspace</p><h1>What are you working on?</h1><p>Explore a molecule, develop an idea, or pick up your research.</p></div><span className="cs-local-tag"><span className="cs-live-dot" />Local workspace</span></header>
    <div className="cs-home-launchpad"><QuickCalculation onSaved={() => setRefresh((value) => value + 1)} projects={data.projects.edges.map((edge) => edge.node)} /><div className="cs-home-shortcuts">
      <Link className="cs-intent-launch cs-intent-launch--research" to="/?new=research"><ChemistryArt kind="research" /><div><span className="cs-kicker">Develop an idea</span><h2>Start research</h2><p>Explore, improve a formulation, or match a product.</p><span className="cs-text-action">Start a research task <StudioIcon name="arrow" /></span></div></Link>
      <Link className="cs-intent-launch cs-intent-launch--lab" to="/lab"><ChemistryArt kind="experiment" /><div><span className="cs-kicker">At the bench</span><h2>Open your lab notebook</h2><p>Plan an experiment or record what happened.</p><span className="cs-text-action">Open lab notebook <StudioIcon name="arrow" /></span></div></Link>
    </div></div>
    <div className="cs-home-work"><section aria-labelledby="recent-work-title"><div className="cs-section-heading"><div><p className="cs-kicker">Pick up where you left off</p><h2 id="recent-work-title">Recent research</h2></div><Link to="/projects">All projects <StudioIcon name="arrow" /></Link></div>
      {recent.length ? <ul className="cs-recent-work" data-field="recent-tasks">{recent.map((task) => <li key={task.id}><Link to={taskUrl(task.id, "overview")}><span className="cs-record-symbol"><StudioIcon name={task.mode === "match_reference" ? "materials" : "lab"} /></span><div><strong>{task.title}</strong><span>{task.project?.name ?? "Research"} <span aria-hidden="true">·</span> {task.mode === "discover" ? "Explore" : task.mode === "match_reference" ? "Match a reference" : humanize(task.mode)}</span></div><Badge tone={task.workflowState === "closed" ? "success" : task.workflowState === "awaiting_review" ? "warning" : "neutral"}>{humanize(task.workflowState)}</Badge><StudioIcon name="arrow" /></Link></li>)}</ul> : <div className="cs-friendly-empty"><ChemistryArt kind="research" /><h3>A fresh page for your research</h3><p>Start with a molecule above, or create a project for a larger question.</p><Link className="cs-btn cs-btn--secondary" to="/projects?new=project">Create your first project</Link></div>}
    </section><section className="cs-home-review" aria-labelledby="review-title"><div className="cs-section-heading"><h2 id="review-title">Ready for your review</h2><span className="cs-count">{pending.length}</span></div>{pending.length ? <ul className="cs-review-list" data-field="pending-decisions">{pending.map((task) => <li key={task.id}><Link to={taskUrl(task.id, "decisions", "closeout")}><span className="cs-review-dot" /><div><strong>{task.title}</strong><span>{task.project?.name}</span></div><StudioIcon name="arrow" /></Link></li>)}</ul> : <div className="cs-review-clear"><span className="cs-review-check" aria-hidden="true">✓</span><h3>You're all caught up</h3><p>Research that needs a decision will appear here.</p></div>}</section></div>
  </div>;
}

export function HomePage() {
  return <Suspense fallback={<LoadingState label="Opening your workspace…" />}><HomeInner /></Suspense>;
}
