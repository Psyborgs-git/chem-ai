import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { Button } from "../../components/atoms/Button";
import { PageHeader, StructuredData } from "../../components/layout/StudioLayout";
import { workspaceRequest } from "../../relay/network";
import { messageOf, post, useWorkspace } from "../workspace/useWorkspace";
import { MarkdownPreview } from "./MarkdownPreview";
import type { Library, ResearchMemory, ResearchSource } from "./types";
import "./notebooks.css";

type SearchResult = { title?: string; url?: string; downloadUrl?: string; doi?: string; id?: string; authors?: unknown; snippet?: string; abstract?: string; [key: string]: unknown };
function safeUrl(value: string | undefined) { try { const parsed = new URL(value ?? ""); return ["http:", "https:"].includes(parsed.protocol) && !parsed.username && !parsed.password ? parsed.href : undefined; } catch { return undefined; } }
export function openAgent(message = "", context?: Record<string, unknown>) { window.dispatchEvent(new CustomEvent("studio-agent-open", { detail: { message, ...context } })); }
function downloadText(name: string, content: string, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const element = document.createElement("a"); element.href = url; element.download = name; element.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ResearchLibraryPage({ view = "research" }: { view?: "research" | "downloads" | "memory" }) {
  const library = useWorkspace<Library>("/api/library");
  const [query, setQuery] = useState("");
  const [connector, setConnector] = useState("openalex");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selected, setSelected] = useState<ResearchSource | null>(null);
  const [memoryTitle, setMemoryTitle] = useState("");
  const [memoryBody, setMemoryBody] = useState("");
  const sources = (library.data?.sources ?? []).filter((source) => !query || `${source.title} ${source.sourceUrl ?? source.url ?? ""}`.toLowerCase().includes(query.toLowerCase()));
  const search = async (event: FormEvent) => {
    event.preventDefault(); if (busy || !query.trim()) return; setBusy("search"); setNotice(null);
    try { const response = await workspaceRequest<{ results: SearchResult[] }>(`/api/library/research/search?connector=${connector}&q=${encodeURIComponent(query)}`); setResults(response.results ?? []); }
    catch (e) { setNotice(messageOf(e)); } finally { setBusy(null); }
  };
  const fetchSource = async (sourceUrl: string, result?: SearchResult) => {
    if (busy) return; setBusy(sourceUrl); setNotice(null);
    try { const source = await post<ResearchSource>("/api/library/sources/fetch", { url: sourceUrl, title: result?.title, citation: result ?? {} }); setSelected(source); setUrl(""); setNotice("Source retained in your private Downloads library."); await library.refresh(); }
    catch (e) { setNotice(messageOf(e)); } finally { setBusy(null); }
  };
  const selectSource = async (id: string) => { try { setSelected(await workspaceRequest<ResearchSource>(`/api/library/sources/${id}`)); } catch (e) { setNotice(messageOf(e)); } };
  const saveMemory = async (event: FormEvent) => {
    event.preventDefault(); setBusy("memory");
    try {
      const notebook = library.data?.notebooks.find((item) => item.title === "Research memory") ?? await post<{ id: string }>("/api/library/notebooks", { title: "Research memory" });
      const page = await post<{ id: string; revision: number }>("/api/library/pages", { notebookId: notebook.id, title: memoryTitle, kind: "note", content: { markdown: memoryBody } });
      await post<ResearchMemory>("/api/library/memory", { title: memoryTitle, body: memoryBody, sourceRefs: [{ kind: "page", id: page.id, revision: page.revision }] }); setMemoryTitle(""); setMemoryBody(""); await library.refresh();
    }
    catch (e) { setNotice(messageOf(e)); } finally { setBusy(null); }
  };
  const reveal = async () => {
    try { await post("/api/library/downloads/reveal"); }
    catch (e) { setNotice(messageOf(e)); }
  };
  const uploadSource = async (file: File | undefined) => {
    if (!file || busy) return;
    setBusy("upload"); setNotice(null);
    try { const form = new FormData(); form.append("file", file); form.append("title", file.name); setSelected(await workspaceRequest<ResearchSource>("/api/library/sources/upload", { method: "POST", body: form })); await library.refresh(); setNotice("Original file and review copy retained."); }
    catch (e) { setNotice(messageOf(e)); } finally { setBusy(null); }
  };
  const exportBibtex = (source: ResearchSource) => {
    const escaped = (value: unknown) => String(value ?? "").replace(/[\\{}]/g, (character) => `\\${character}`).replace(/[\r\n]+/g, " ");
    const citation = source.citation ?? {};
    downloadText("citation.bib", `@misc{studio_${source.id.replaceAll("-", "")},\n  title = {${escaped(source.title)}},\n  url = {${escaped(source.sourceUrl ?? source.url)}},\n  doi = {${escaped(citation.doi)}},\n  note = {Retained by Chemistry Studio; source ${source.id}}\n}\n`, "application/x-bibtex");
  };
  const title = view === "memory" ? "Research memory" : view === "downloads" ? "Downloads" : "Research library";
  return <div className="cs-library-page"><PageHeader eyebrow="Your private research" title={title} description={view === "memory" ? "Decisions, findings, and open questions that help your agent continue over time." : view === "downloads" ? "Original sources, citations, and saved copies for future review." : "Find papers, chemical records, and web resources. Keep the sources behind every finding."} actions={<div className="cs-actions">{view === "downloads" && <Button onClick={() => { void reveal(); }}>Open in Finder</Button>}<Button variant="primary" onClick={() => openAgent("Continue my research using my saved sources and notes.")}>Continue with agent</Button></div>} />
    <nav className="cs-library-tabs" aria-label="Research library"><Link to="/library/research" aria-current={view === "research" ? "page" : undefined}>Discover</Link><Link to="/downloads" aria-current={view === "downloads" ? "page" : undefined}>Downloads</Link><Link to="/memory" aria-current={view === "memory" ? "page" : undefined}>Memory</Link><Link to="/notebooks">Notebooks</Link></nav>
    {(notice || library.error) && <p role="status" className="cs-workspace-notice">{notice ?? library.error}</p>}
    {view === "downloads" && <label className="cs-field cs-library-upload"><span className="cs-field__label">Retain a paper, dataset, or reference file</span><input className="cs-input" type="file" disabled={!!busy} onChange={(event) => { void uploadSource(event.target.files?.[0]); event.target.value = ""; }} /></label>}
    {view === "research" && <div className="cs-research-discovery"><form className="cs-research-search" onSubmit={(event) => { void search(event); }}><label className="cs-field"><span className="cs-field__label">Search resources</span><input className="cs-input" required value={query} placeholder="A research question, compound, paper title, or DOI…" onChange={(event) => setQuery(event.target.value)} /></label><label className="cs-field"><span className="cs-field__label">Source</span><select className="cs-input" value={connector} onChange={(event) => setConnector(event.target.value)}><option value="openalex">OpenAlex papers</option><option value="crossref">Crossref</option><option value="pubchem">PubChem</option><option value="web">Web search</option></select></label><Button type="submit" variant="primary" disabled={!!busy}>{busy === "search" ? "Searching…" : "Search"}</Button></form>
      <form className="cs-research-url" onSubmit={(event) => { event.preventDefault(); void fetchSource(url); }}><label className="cs-field"><span className="cs-field__label">Save a source URL</span><input className="cs-input" type="url" required placeholder="https://…" value={url} onChange={(event) => setUrl(event.target.value)} /></label><Button type="submit" disabled={!!busy}>Download and retain</Button></form>
      <div className="cs-source-search-results">{results.map((result, index) => <article className="cs-source-result" key={result.id ?? result.url ?? index}><div><h2>{result.title ?? "Resource"}</h2>{(result.snippet || result.abstract) && <p>{String(result.snippet ?? result.abstract).slice(0, 700)}</p>}{result.doi && <code>{result.doi}</code>}{safeUrl(result.url) && <a href={safeUrl(result.url)} rel="noopener noreferrer" target="_blank">View source ↗</a>}</div>{safeUrl(result.downloadUrl ?? result.url) && <Button disabled={!!busy} onClick={() => { void fetchSource(result.downloadUrl ?? result.url ?? "", result); }}>{busy === (result.downloadUrl ?? result.url) ? "Retaining…" : "Save source"}</Button>}</article>)}</div>
    </div>}
    {view === "memory" ? <div className="cs-memory-layout"><form className="cs-panel" onSubmit={(event) => { void saveMemory(event); }}><h2>Remember for future research</h2><label className="cs-field"><span className="cs-field__label">Title</span><input className="cs-input" required value={memoryTitle} onChange={(event) => setMemoryTitle(event.target.value)} /></label><label className="cs-field"><span className="cs-field__label">Finding, decision, or question</span><textarea className="cs-input" rows={5} required value={memoryBody} onChange={(event) => setMemoryBody(event.target.value)} /></label><Button type="submit" disabled={!!busy}>Remember</Button></form><div className="cs-memory-list">{library.data?.memory?.length ? library.data.memory.map((memory) => <article className="cs-panel" key={memory.id}><header><h2>{memory.title}</h2><span className="cs-count">{memory.stale ? "Source changed" : memory.sourceRefs?.length ? "Source linked" : "Personal memory"}</span></header><MarkdownPreview content={memory.body} />{!!memory.sourceRefs?.length && <details><summary>Sources</summary><StructuredData value={memory.sourceRefs} /></details>}<div className="cs-actions"><Button onClick={() => openAgent(`Continue research from this saved memory: ${memory.title}`, { memoryId: memory.id })}>Continue</Button><Button variant="ghost" onClick={() => { void workspaceRequest(`/api/library/memory/${memory.id}`, { method: "DELETE" }).then(library.refresh).catch((e) => setNotice(messageOf(e))); }}>Forget</Button></div></article>) : <p className="cs-field__hint">Your agent will collect source-linked memory as research progresses. You can also save a decision here.</p>}</div></div> : <>
      <div className="cs-section-heading"><h2>Saved sources <span className="cs-count">{library.data?.sources?.length ?? 0}</span></h2>{view === "downloads" && <input className="cs-input" aria-label="Filter saved sources" placeholder="Find a saved source…" value={query} onChange={(event) => setQuery(event.target.value)} />}</div>
      {view === "downloads" && library.data?.downloadsRoot && <p className="cs-field__hint">Review folder: <code>{library.data.downloadsRoot}</code></p>}
      {library.loading ? <p role="status">Loading saved sources…</p> : sources.length ? <div className="cs-source-grid">{sources.map((source) => <article className="cs-source-card" key={source.id}><span className="cs-kicker">{source.mediaType ?? "Saved source"}</span><h2><button onClick={() => { void selectSource(source.id); }}>{source.title}</button></h2><p>{source.originalName ?? source.sourceUrl ?? source.url}</p><div className="cs-actions"><a className="cs-btn cs-btn--secondary" href={`/api/library/sources/${source.id}/content?format=original`}>Open original</a><Button variant="ghost" onClick={() => { void selectSource(source.id); }}>Citation & details</Button></div></article>)}</div> : <div className="cs-friendly-empty"><h2>Your references will stay here</h2><p>Saved papers, webpages, supplements, and datasets remain available for later review.</p><Link className="cs-btn cs-btn--primary" to="/library/research">Find a source</Link></div>}
    </>}
    {selected && <section className="cs-panel cs-source-detail" aria-label="Source details"><header className="cs-section-heading"><h2>{selected.title}</h2><Button variant="ghost" onClick={() => setSelected(null)}>Close</Button></header>{safeUrl(selected.sourceUrl ?? selected.url) && <a href={safeUrl(selected.sourceUrl ?? selected.url)} target="_blank" rel="noopener noreferrer">Original source ↗</a>}<dl className="cs-record"><div><dt>File</dt><dd>{selected.originalName}</dd></div><div><dt>Checksum</dt><dd><code>{selected.checksum ?? selected.checksumSha256}</code></dd></div><div><dt>Saved</dt><dd>{selected.createdAt ? new Date(selected.createdAt).toLocaleString() : "Retained"}</dd></div></dl><StructuredData value={selected.citation ?? selected.metadata} label="Citation metadata" /><div className="cs-actions"><a className="cs-btn cs-btn--primary" href={`/api/library/sources/${selected.id}/content?format=original`}>Download original</a><a className="cs-btn cs-btn--secondary" href={`/api/library/sources/${selected.id}/content?format=text`}>Extracted text</a><Button onClick={() => downloadText("citation.json", JSON.stringify(selected, null, 2), "application/json")}>Export citation</Button><Button onClick={() => exportBibtex(selected)}>Export BibTeX</Button>{safeUrl(selected.sourceUrl ?? selected.url) && <Button disabled={!!busy} onClick={() => { setBusy("refresh"); void post<ResearchSource>("/api/library/sources/fetch", { url: selected.sourceUrl ?? selected.url, title: selected.title, citation: selected.citation ?? {}, forceRefresh: true }).then(async (source) => { setSelected(source); await library.refresh(); }).catch((e) => setNotice(messageOf(e))).finally(() => setBusy(null)); }}>Check for source update</Button>}<Button onClick={() => openAgent(`Review my saved source ${selected.id}: ${selected.title}. Cite source passages and identify open questions.`, { sourceId: selected.id })}>Research this source</Button></div></section>}
  </div>;
}
