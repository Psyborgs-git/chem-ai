import { Component, Suspense, useState, type ReactNode } from "react";
import { useLazyLoadQuery } from "react-relay";
import { Link } from "react-router";
import { WorkspaceHomeQuery } from "../../features/home/operations";
import { CreateSheet } from "./CreateSheet";
import { StudioIcon } from "./StudioLayout";
import { TextField } from "../atoms/TextField";
import type { homeWorkspaceQuery } from "../../__generated__/homeWorkspaceQuery.graphql";

class FinderBoundary extends Component<{children: ReactNode}, {failed: boolean}> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <p role="alert">Search couldn't load. Close and try again when the connection is back.</p> : this.props.children; }
}
function FinderResults({ term, onClose }: { term: string; onClose: () => void }) {
  const data = useLazyLoadQuery<homeWorkspaceQuery>(WorkspaceHomeQuery, {}, { fetchPolicy: "store-and-network" });
  const filter = term.toLocaleLowerCase().trim();
  const projects = data.projects.edges.map((edge) => edge.node).filter((project) => project.name.toLocaleLowerCase().includes(filter));
  const tasks = data.recent.edges.map((edge) => edge.node).filter((task) => `${task.title} ${task.project?.name ?? ""}`.toLocaleLowerCase().includes(filter));
  return <div className="cs-finder-results"><p className="cs-field__hint">Projects and recent research</p>{!projects.length && !tasks.length && <p role="status">No matching projects or recent tasks.</p>}
    {projects.length > 0 && <section><h3>Projects</h3>{projects.map((project) => <Link key={project.id} to={`/projects/${encodeURIComponent(project.id)}`} onClick={onClose}><StudioIcon name="projects" /><span>{project.name}</span><StudioIcon name="arrow" /></Link>)}</section>}
    {tasks.length > 0 && <section><h3>Recent research</h3>{tasks.map((task) => <Link key={task.id} to={`/tasks/${encodeURIComponent(task.id)}`} onClick={onClose}><StudioIcon name="lab" /><span>{task.title}<small>{task.project?.name}</small></span><StudioIcon name="arrow" /></Link>)}</section>}
  </div>;
}
export function WorkspaceFinder({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [term, setTerm] = useState("");
  return <CreateSheet open={open} onClose={onClose} title="Find your work"><TextField label="Search projects and recent research" value={term} onChange={(event) => setTerm(event.target.value)} placeholder="A project, question, or molecule…" /><FinderBoundary><Suspense fallback={<p role="status">Finding your work…</p>}><FinderResults term={term} onClose={onClose} /></Suspense></FinderBoundary></CreateSheet>;
}
