import { type ReactNode, useEffect, useId, useState } from "react";
import { Link } from "react-router";
import { Button } from "../atoms/Button";
import "../../styles/navigation.css";

export const PRIMARY_DESTINATIONS = [
  { to: "/", label: "Home", icon: "home" },
  { to: "/projects", label: "Projects", icon: "projects" },
  { to: "/notebooks", label: "Notebooks", icon: "notebooks" },
  { to: "/library/research", label: "Research library", icon: "research" },
  { to: "/learning", label: "Local learning", icon: "models" },
];
export const SECONDARY_DESTINATIONS = [
  { label: "Saved work", destinations: [
    { to: "/downloads", label: "Downloads", icon: "imports" },
    { to: "/memory", label: "Research memory", icon: "notebooks" },
    { to: "/lab", label: "Lab", icon: "lab" },
  ] },
  { label: "Tools & settings", destinations: [
    { to: "/materials", label: "Materials & Products", icon: "materials" },
    { to: "/evidence", label: "Evidence", icon: "evidence" },
    { to: "/imports", label: "Imports", icon: "imports" },
    { to: "/models", label: "Model registry", icon: "models" },
    { to: "/compute", label: "Compute", icon: "compute" },
    { to: "/settings/providers", label: "Providers", icon: "providers" },
    { to: "/help", label: "Help & documentation", icon: "help" },
  ] },
];
export const WORKSPACE_DESTINATIONS = [...PRIMARY_DESTINATIONS, ...SECONDARY_DESTINATIONS.flatMap((group) => group.destinations)];
const isDestination = (pathname: string, to: string) => to === "/" ? pathname === "/" : pathname === to || pathname.startsWith(`${to}/`);

export function WorkspaceNavigation({ pathname, onNavigate }: { pathname: string; onNavigate: () => void }) {
  const secondaryActive = SECONDARY_DESTINATIONS.some((group) => group.destinations.some((item) => isDestination(pathname, item.to)));
  const [moreOpen, setMoreOpen] = useState(secondaryActive);
  const moreId = useId();
  useEffect(() => { if (secondaryActive) setMoreOpen(true); }, [pathname, secondaryActive]);
  const destination = (item: typeof PRIMARY_DESTINATIONS[number]) => {
    const active = isDestination(pathname, item.to) || (item.to === "/projects" && pathname.startsWith("/tasks/"));
    return <Link key={item.to} to={item.to} className={active ? "active" : undefined} aria-current={active ? "page" : undefined} onClick={onNavigate}><StudioIcon name={item.icon} /><span>{item.label}</span></Link>;
  };
  return <nav aria-label="primary" id="primary-navigation" className="cs-focused-navigation">
    <div className="cs-nav-primary">{PRIMARY_DESTINATIONS.map(destination)}</div>
    <Button variant="ghost" className={`cs-nav-more-trigger${secondaryActive ? " is-active" : ""}`} aria-expanded={moreOpen} aria-controls={moreId} onClick={() => setMoreOpen(!moreOpen)}><StudioIcon name="more" /><span>More</span><StudioIcon name="chevron" className="cs-nav-more-chevron" /></Button>
    <div id={moreId} className="cs-nav-secondary" hidden={!moreOpen}>{SECONDARY_DESTINATIONS.map((group) => <section key={group.label} className="cs-nav-secondary-group" aria-label={group.label}><h2>{group.label}</h2>{group.destinations.map(destination)}</section>)}</div>
  </nav>;
}

/** Shared research surfaces keep the same hierarchy without hiding scientific context. */
export function PageHeader({ eyebrow, title, description, actions, level = 1 }: {
  eyebrow?: string; title: string; description?: ReactNode; actions?: ReactNode; level?: 1 | 2;
}) {
  const Heading = level === 2 ? "h2" : "h1";
  return <header className="cs-page-header">
    <div>{eyebrow && <p className="cs-eyebrow">{eyebrow}</p>}<Heading>{title}</Heading>
      {description && <p className="cs-page-description">{description}</p>}</div>
    {actions && <div className="cs-page-actions">{actions}</div>}
  </header>;
}

export function Panel({ title, description, children, className = "", actions }: {
  title: string; description?: ReactNode; children: ReactNode; className?: string; actions?: ReactNode;
}) {
  const id = useId();
  return <section className={`cs-panel ${className}`} aria-labelledby={id}>
    <header className="cs-panel__header"><div><h2 id={id}>{title}</h2>
      {description && <p className="cs-field__hint">{description}</p>}</div>{actions}</header>
    <div className="cs-panel__body">{children}</div>
  </section>;
}

export function FeatureSurface({ title, description, children, className = "" }: {
  title: string; description: ReactNode; children: ReactNode; className?: string;
}) {
  return <div className={`cs-family-page ${className}`}>
    <header className="cs-feature-heading"><h2>{title}</h2><p className="cs-page-description">{description}</p></header>
    <div className="cs-feature-body">{children}</div>
  </div>;
}

export function humanize(value: string): string {
  return value.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]/g, " ");
}

/** Readable view first; exact source data remains available for inspection. */
export function StructuredData({ value, label = "Record", depth = 0 }: {
  value: unknown; label?: string; depth?: number;
}) {
  if (value === null || value === undefined) return <span className="cs-unknown">Not recorded</span>;
  if (typeof value !== "object") return <span>{typeof value === "boolean" ? (value ? "Yes" : "No") : String(value)}</span>;
  if (Array.isArray(value)) return value.length ? <ul className="cs-data-list">{value.map((v, i) =>
    <li key={i}><StructuredData value={v} depth={depth + 1} /></li>)}</ul> : <span className="cs-unknown">None recorded</span>;
  const entries = Object.entries(value as Record<string, unknown>);
  if (!entries.length) return <span className="cs-unknown">No details recorded</span>;
  if (depth > 2) return <details className="cs-technical"><summary>{label} details</summary><pre>{JSON.stringify(value, null, 2)}</pre></details>;
  return <dl className="cs-record">{entries.map(([key, v]) => <div key={key}>
    <dt>{humanize(key)}</dt><dd><StructuredData value={v} depth={depth + 1} label={humanize(key)} /></dd>
  </div>)}</dl>;
}

export function TechnicalDetails({ value, label = "Inspect exact record" }: { value: unknown; label?: string }) {
  return <details className="cs-technical"><summary>{label}</summary><pre>{JSON.stringify(value, null, 2)}</pre></details>;
}

export function StudioIcon({ name, className = "" }: { name: string; className?: string }) {
  const paths: Record<string, ReactNode> = {
    help: <><circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 2-2.5 2-2.5 4m0 3v.5" /></>,
    home: <><path d="m3 10 9-7 9 7v10H3Z" /><path d="M9 20v-7h6v7" /></>,
    projects: <><path d="M3 6h6l2 2h10v12H3Z" /><path d="M3 6V4h7l2 2h9v2" /></>,
    materials: <><path d="m12 3 8 5v8l-8 5-8-5V8Z" /><path d="m4 8 8 5 8-5M12 13v8" /></>,
    imports: <><path d="M5 3h10l4 4v14H5Z" /><path d="M15 3v5h4M12 10v7m-3-3 3 3 3-3" /></>,
    evidence: <><path d="M4 4h16v16H4Z" /><path d="m8 11 2 2 6-6M8 17h8" /></>,
    lab: <><path d="M9 3h6M10 3v7L4 20h16l-6-10V3M7 15h10" /></>,
    models: <><circle cx="12" cy="12" r="3" /><circle cx="4" cy="4" r="1.5" /><circle cx="20" cy="4" r="1.5" /><circle cx="4" cy="20" r="1.5" /><circle cx="20" cy="20" r="1.5" /><path d="m5 5 5 5m4 4 5 5M19 5l-5 5m-4 4-5 5" /></>,
    compute: <><rect x="5" y="5" width="14" height="14" rx="2" /><path d="M9 9h6v6H9ZM9 2v3m6-3v3M9 19v3m6-3v3M2 9h3m-3 6h3m14-6h3m-3 6h3" /></>,
    providers: <><path d="M8 3v5m8-5v5M6 8h12v3a6 6 0 0 1-12 0ZM12 17v4" /></>,
    notebooks: <><path d="M5 3h14v18H5Z" /><path d="M8 3v18M11 7h5M11 11h5M11 15h3M3 7h3M3 12h3M3 17h3" /></>,
    research: <><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6M7 8h6M7 11h4" /></>,
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    arrow: <path d="M4 12h15m-5-5 5 5-5 5" />,
    more: <><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></>,
    chevron: <path d="m8 10 4 4 4-4" />,
  };
  return <svg className={`cs-icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] ?? paths.materials}</svg>;
}
