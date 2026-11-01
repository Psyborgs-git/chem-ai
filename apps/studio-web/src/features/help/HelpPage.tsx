import { useEffect, useRef } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router";
import { articles } from "virtual:studio-help";
import { Input } from "@/components/ui/input";
import { HELP_SECTIONS } from "./types";
import { HelpMarkdown } from "./HelpMarkdown";
import { searchHelp } from "./search";
import "./help.css";

export function HelpPage() {
  const { section, article: slug } = useParams();
  const [params, setParams] = useSearchParams();
  const { pathname, hash, search } = useLocation();
  const query = params.get("q") ?? "";
  const filter = params.get("section") ?? "";
  const selected = articles.find((article) => article.section === section && article.slug === slug);
  const unknown = pathname.replace(/\/+$/, "") !== "/help" && !selected;
  const results = searchHelp(articles, query, filter);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const lastRoute = useRef("");
  const articleUrl = (id: string) => `/help/${id}${query || filter ? `?${new URLSearchParams({ ...(query ? { q: query } : {}), ...(filter ? { section: filter } : {}) })}` : ""}`;
  const homeUrl = (nextSection = "") => `/help${query || nextSection ? `?${new URLSearchParams({ ...(query ? { q: query } : {}), ...(nextSection ? { section: nextSection } : {}) })}` : ""}`;

  useEffect(() => {
    document.title = `${selected?.title ?? "Help & documentation"} · Chemistry Studio`;
    if (hash) {
      let id: string;
      try { id = decodeURIComponent(hash.slice(1)); } catch { return; }
      const target = document.getElementById(id);
      if (target) { target.scrollIntoView({ block: "start" }); target.focus({ preventScroll: true }); }
    } else if (lastRoute.current !== pathname) {
      const target = selected ? document.querySelector<HTMLElement>(".cs-help-prose h1") : titleRef.current;
      target?.focus({ preventScroll: true });
      target?.scrollIntoView({ block: "start" });
    }
    lastRoute.current = pathname;
    return () => { document.title = "Chemistry Studio"; };
  }, [pathname, hash, selected]);

  const resultList = (compact = false) => <>
    <p className="cs-help-count" role="status">{results.length} {results.length === 1 ? "article" : "articles"}{query.trim() ? ` matching “${query.trim()}”` : ""}</p>
    {results.length ? <ul className={`cs-help-results${compact ? " is-compact" : ""}`}>{results.slice(0, compact ? 12 : 60).map(({ article, snippet }) => <li key={article.id}><Link to={articleUrl(article.id)} aria-current={article.id === selected?.id ? "page" : undefined}><small>{HELP_SECTIONS.find((value) => value.id === article.section)?.title}</small><strong>{article.title}</strong><p>{snippet}</p></Link></li>)}</ul> : <p className="cs-help-empty">No matching articles. Try a shorter term, an operation name, or another section.</p>}
    {results.length > (compact ? 12 : 60) && <p className="cs-help-count">{compact ? <Link to={homeUrl(filter)}>See all matching articles</Link> : "Showing the first 60 articles. Refine your search to narrow the results."}</p>}
  </>;

  return <div className="cs-help">
    <header className="cs-help-header"><div><p className="cs-eyebrow">Chemistry Studio handbook</p>{selected ? <p className="cs-help-title">Help & documentation</p> : <h1 ref={titleRef} tabIndex={-1}>Help & documentation</h1>}<p>Guides for your research, application changes, and local operations.</p></div><p className="cs-help-local">Included with this build · Search stays on this machine</p></header>
    <div className="cs-help-layout">
      <aside className="cs-help-sidebar" aria-label="Documentation navigation">
        <label className="cs-field"><span className="cs-field__label">Search documentation</span><Input type="search" value={query} placeholder="Notebook, backup, operation…" onChange={(event) => { const next = new URLSearchParams(params); if (event.target.value) next.set("q", event.target.value); else next.delete("q"); setParams(next, { replace: true }); }} /></label>
        <nav aria-label="Documentation sections"><Link to={homeUrl()} aria-current={!filter && !selected ? "page" : undefined}>All documentation</Link>{HELP_SECTIONS.map((item) => <Link key={item.id} to={homeUrl(item.id)} aria-current={(filter || selected?.section) === item.id ? "page" : undefined}>{item.title}</Link>)}</nav>
        {selected && (query ? resultList(true) : <nav className="cs-help-chapters" aria-label="Articles in this section">{articles.filter((item) => item.section === selected.section).map((item) => <Link key={item.id} to={articleUrl(item.id)} aria-current={item.id === selected.id ? "page" : undefined}>{item.title}</Link>)}</nav>)}
      </aside>
      <div className="cs-help-body">
        {unknown ? <section className="cs-help-empty"><h2>Article not found</h2><p>This help address does not match an article in this build.</p><Link to="/help">Browse documentation</Link></section> : selected ? <>
          <nav className="cs-help-breadcrumb" aria-label="Article breadcrumb"><Link to={homeUrl()}>Help</Link><span aria-hidden="true">/</span><Link to={homeUrl(selected.section)}>{HELP_SECTIONS.find((item) => item.id === selected.section)?.title}</Link></nav>
          <details className="cs-help-toc"><summary>On this page</summary><nav aria-label="On this page">{selected.headings.filter((heading) => heading.depth === 2 || heading.depth === 3).map((heading) => <Link key={heading.id} className={heading.depth === 3 ? "is-nested" : undefined} to={`${pathname}${search}#${heading.id}`}>{heading.text}</Link>)}</nav></details>
          <article aria-label={selected.title}><HelpMarkdown article={selected} /></article>
          <footer className="cs-help-article-footer"><p>Maintained in <code>{selected.source}</code>. Documentation changes ship with a new app build.</p><Link to={articleUrl("development/testing-and-docs")}>How to update this documentation</Link></footer>
        </> : query || filter ? <section aria-label="Documentation results"><h2>{query ? "Search results" : HELP_SECTIONS.find((item) => item.id === filter)?.title ?? "Documentation"}</h2>{resultList()}</section> : <>
          <section className="cs-help-categories" aria-label="Browse documentation">{HELP_SECTIONS.map((item) => <Link key={item.id} to={homeUrl(item.id)}><h2>{item.title}</h2><p>{item.description}</p><span>{articles.filter((article) => article.section === item.id).length} articles →</span></Link>)}</section>
          <section className="cs-help-start"><h2>Start here</h2><ul>{["usage/getting-started", "usage/chemistry-basics", "usage/guided-first-research", "usage/notebooks-and-editing", "development/local-development", "operations/backup-restore"].map((id) => { const item = articles.find((article) => article.id === id); return item ? <li key={id}><Link to={articleUrl(id)}>{item.title}</Link><p>{item.summary}</p></li> : null; })}</ul></section>
          <p className="cs-help-note">These articles describe the software and its current limits. Individual calculation, training, and simulation results retain their own validation status.</p>
        </>}
      </div>
    </div>
  </div>;
}
