import { Component, Suspense, useEffect, useState, type ReactNode, type RefObject } from "react";
import { graphql, useLazyLoadQuery } from "react-relay";
import { useNavigate } from "react-router";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useWorkspace } from "../../features/workspace/useWorkspace";
import { PRIMARY_DESTINATIONS, StudioIcon, WORKSPACE_DESTINATIONS } from "./StudioLayout";
import type { WorkspaceFinderQuery } from "../../__generated__/WorkspaceFinderQuery.graphql";

const FinderQuery = graphql`
  query WorkspaceFinderQuery {
    projects(first: 50) { edges { node { id name } } }
    tasks(first: 50) { edges { node { id title project { name } } } }
  }
`;
type ResourceHit = { id: string; kind: string; title: string; notebookId?: string };
const actions = [
  { label: "Ask agent", icon: "models", to: "$agent", words: "chat assistant question" },
  { label: "Find papers", icon: "research", to: "/library/research?focus=search", words: "search resources sources literature" },
  { label: "New notebook", icon: "notebooks", to: "/notebooks?new=notebook", words: "write notes recipe formula" },
  { label: "Train model", icon: "models", to: "/learning?tab=new", words: "training fine tune dataset" },
  { label: "Explore molecule", icon: "materials", to: "/?focus=molecule", words: "SMILES structure calculate properties" },
  { label: "New research task", icon: "projects", to: "/?new=research", words: "project discover improve match" },
];
class FinderBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <p className="cs-finder-status" role="alert">Your saved work couldn't load. Close search and try again.</p> : this.props.children; }
}
export function resourceDestination(resource: ResourceHit) {
  if (resource.kind === "page" && resource.notebookId) return `/notebooks?notebook=${encodeURIComponent(resource.notebookId)}&page=${encodeURIComponent(resource.id)}`;
  if (resource.kind === "source") return `/downloads?source=${encodeURIComponent(resource.id)}`;
  if (resource.kind === "memory") return `/memory?memory=${encodeURIComponent(resource.id)}`;
  return "/notebooks";
}
function FinderDestinations({ term, onSelect }: { term: string; onSelect: (destination: string) => void }) {
  const filter = term.toLocaleLowerCase().trim();
  const destinations = (filter ? WORKSPACE_DESTINATIONS : PRIMARY_DESTINATIONS).filter((item) => item.label.toLocaleLowerCase().includes(filter));
  const matches = actions.filter((action) => `${action.label} ${action.words}`.toLocaleLowerCase().includes(filter));
  return <>
    {matches.length > 0 && <CommandGroup heading="Quick actions">{matches.map((action) => <CommandItem key={action.to} value={`action:${action.label}`} onSelect={() => onSelect(action.to)}><StudioIcon name={action.icon} /><span className="cs-finder-row-label">{action.label}</span></CommandItem>)}</CommandGroup>}
    {destinations.length > 0 && <CommandGroup heading="Go to">{destinations.map((item) => <CommandItem key={item.to} value={`destination:${item.to}`} onSelect={() => onSelect(item.to)}><StudioIcon name={item.icon} /><span className="cs-finder-row-label">{item.label}</span></CommandItem>)}</CommandGroup>}
  </>;
}
function FinderResults({ term, onSelect }: { term: string; onSelect: (destination: string) => void }) {
  const data = useLazyLoadQuery<WorkspaceFinderQuery>(FinderQuery, {}, { fetchPolicy: "store-and-network" });
  const filter = term.toLocaleLowerCase().trim();
  const resources = useWorkspace<{ results: ResourceHit[] }>(filter.length >= 2 ? `/api/library/search?q=${encodeURIComponent(term.trim())}&limit=12` : null);
  const projects = data.projects.edges.map((edge) => edge.node).filter((project) => project.name.toLocaleLowerCase().includes(filter));
  const tasks = data.tasks.edges.map((edge) => edge.node).filter((task) => `${task.title} ${task.project?.name ?? ""}`.toLocaleLowerCase().includes(filter)).slice(0, filter ? 20 : 5);
  return <>
    {tasks.length > 0 && <CommandGroup heading="Recent tasks">{tasks.map((task) => <CommandItem key={task.id} value={`task:${task.id}`} onSelect={() => onSelect(`/tasks/${encodeURIComponent(task.id)}`)}><StudioIcon name="lab" /><span className="cs-finder-row-copy"><span>{task.title}</span><small>{task.project?.name ?? "Research task"}</small></span></CommandItem>)}</CommandGroup>}
    {projects.length > 0 && <CommandGroup heading="Projects">{projects.slice(0, filter ? 20 : 5).map((project) => <CommandItem key={project.id} value={`project:${project.id}`} onSelect={() => onSelect(`/projects/${encodeURIComponent(project.id)}`)}><StudioIcon name="projects" /><span className="cs-finder-row-label">{project.name}</span></CommandItem>)}</CommandGroup>}
    {!!resources.data?.results.length && <CommandGroup heading="Notes, sources & memory">{resources.data.results.map((resource) => <CommandItem key={`${resource.kind}:${resource.id}`} value={`resource:${resource.kind}:${resource.id}`} onSelect={() => onSelect(resourceDestination(resource))}><StudioIcon name={resource.kind === "source" ? "research" : "notebooks"} /><span className="cs-finder-row-copy"><span>{resource.title}</span><small>{resource.kind === "page" ? "Notebook page" : resource.kind === "source" ? "Saved source" : "Research memory"}</small></span></CommandItem>)}</CommandGroup>}
    {resources.loading && <p className="cs-finder-status" role="status">Searching your saved resources…</p>}
    {resources.error && <p className="cs-finder-status" role="status">Saved resources couldn't load. Navigation and recent tasks are still available.</p>}
    <CommandEmpty>No matching work. Try a task, paper, notebook, or destination.</CommandEmpty>
  </>;
}
export function WorkspaceFinder({ open, onClose, returnFocusRef }: { open: boolean; onClose: () => void; returnFocusRef?: RefObject<HTMLButtonElement | null> }) {
  const [term, setTerm] = useState(""), [query, setQuery] = useState("");
  const navigate = useNavigate();
  useEffect(() => { if (open) { setTerm(""); setQuery(""); } }, [open]);
  useEffect(() => { const timer = window.setTimeout(() => setQuery(term.trim()), 150); return () => window.clearTimeout(timer); }, [term]);
  const select = (destination: string) => { onClose(); if (destination === "$agent") window.dispatchEvent(new CustomEvent("studio-agent-open", { detail: {} })); else navigate(destination); };
  return <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }}><DialogContent className="cs-workspace-search-dialog" aria-label="Find your work" onCloseAutoFocus={returnFocusRef ? (event) => { event.preventDefault(); returnFocusRef.current?.focus(); } : undefined}><DialogHeader className="sr-only"><DialogTitle>Find your work</DialogTitle><DialogDescription>Navigate to tasks, projects, saved resources, and tools.</DialogDescription></DialogHeader><Command label="Search your workspace" shouldFilter={false}><CommandInput aria-label="Search your workspace" placeholder="Search tasks, papers, notes, or tools…" value={term} onValueChange={setTerm} autoFocus /><CommandList><FinderDestinations term={query} onSelect={select} /><FinderBoundary><Suspense fallback={<p className="cs-finder-status" role="status">Loading your recent work…</p>}><FinderResults term={query} onSelect={select} /></Suspense></FinderBoundary></CommandList></Command></DialogContent></Dialog>;
}
