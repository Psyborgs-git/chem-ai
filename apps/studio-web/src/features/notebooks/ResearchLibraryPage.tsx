import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectGroup, SelectItem } from "@/components/ui/select";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { Button } from "../../components/atoms/Button";
import { PageHeader, TechnicalDetails } from "../../components/layout/StudioLayout";
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
  const [searchParams, setSearchParams] = useSearchParams();
  const resourceSearch = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (view !== "research" || searchParams.get("focus") !== "search") return;
    resourceSearch.current?.focus();
    const next = new URLSearchParams(searchParams); next.delete("focus");
    setSearchParams(next, { replace: true });
  }, [view, searchParams, setSearchParams]);
  const library = useWorkspace<Library>("/api/library");
  const [query, setQuery] = useState("");
  const [sourceQuery, setSourceQuery] = useState("");
  const [selectedMemoryId, setSelectedMemoryId] = useState("");
  const [newMemory, setNewMemory] = useState(false);
  const [connector, setConnector] = useState("openalex");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selected, setSelected] = useState<ResearchSource | null>(null);
  const sourceTarget = searchParams.get("source"), memoryTarget = searchParams.get("memory");
  useEffect(() => {
    if (!sourceTarget || view === "memory") return;
    let current = true;
    void workspaceRequest<ResearchSource>(`/api/library/sources/${encodeURIComponent(sourceTarget)}`).then((source) => {
      if (!current) return;
      setSelected(source);
      setSearchParams((previous) => { const next = new URLSearchParams(previous); next.delete("source"); return next; }, { replace: true });
    }).catch((error) => { if (current) setNotice(messageOf(error)); });
    return () => { current = false; };
  }, [sourceTarget, view, setSearchParams]);
  useEffect(() => {
    if (view !== "memory" || !memoryTarget || !library.data) return;
    if (library.data.memory.some((memory) => memory.id === memoryTarget)) setSelectedMemoryId(memoryTarget);
    else setNotice("That memory is no longer available.");
    setSearchParams((previous) => { const next = new URLSearchParams(previous); next.delete("memory"); return next; }, { replace: true });
  }, [memoryTarget, view, library.data, setSearchParams]);
  const [memoryTitle, setMemoryTitle] = useState("");
  const [memoryBody, setMemoryBody] = useState("");
  const sources = (library.data?.sources ?? []).filter((source) => !sourceQuery || `${source.title} ${source.sourceUrl ?? source.url ?? ""}`.toLowerCase().includes(sourceQuery.toLowerCase()));
  const search = async (event: FormEvent) => {
    event.preventDefault(); if (busy || !query.trim()) return; setBusy("search"); setNotice(null);
    try { const response = await workspaceRequest<{ results: SearchResult[] }>(`/api/library/research/search?connector=${connector}&q=${encodeURIComponent(query)}`); setResults(response.results ?? []); }
    catch (e) { setNotice(messageOf(e)); } finally { setBusy(null); }
  };
  const fetchSource = async (sourceUrl: string, result?: SearchResult) => {
    if (busy) return; setBusy(sourceUrl); setNotice(null);
    try { const source = await post<ResearchSource>("/api/library/sources/fetch", { url: sourceUrl, title: result?.title, citation: result ?? {} }); setSelected(source); setUrl(""); setNotice("Source saved."); await library.refresh(); }
    catch (e) { setNotice(messageOf(e)); } finally { setBusy(null); }
  };
  const selectSource = async (id: string) => { try { setSelected(await workspaceRequest<ResearchSource>(`/api/library/sources/${id}`)); } catch (e) { setNotice(messageOf(e)); } };
  const saveMemory = async (event: FormEvent) => {
    event.preventDefault(); setBusy("memory");
    try {
      const notebook = library.data?.notebooks.find((item) => item.title === "Research memory") ?? await post<{ id: string }>("/api/library/notebooks", { title: "Research memory" });
      const page = await post<{ id: string; revision: number }>("/api/library/pages", { notebookId: notebook.id, title: memoryTitle, kind: "note", content: { markdown: memoryBody } });
      const savedMemory = await post<ResearchMemory>("/api/library/memory", { title: memoryTitle, body: memoryBody, sourceRefs: [{ kind: "page", id: page.id, revision: page.revision }] }); setSelectedMemoryId(savedMemory.id); setMemoryTitle(""); setMemoryBody(""); setNewMemory(false); await library.refresh();
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
    try { const form = new FormData(); form.append("file", file); form.append("title", file.name); setSelected(await workspaceRequest<ResearchSource>("/api/library/sources/upload", { method: "POST", body: form })); await library.refresh(); setNotice("File saved."); }
    catch (e) { setNotice(messageOf(e)); } finally { setBusy(null); }
  };
  const exportBibtex = (source: ResearchSource) => {
    const escaped = (value: unknown) => String(value ?? "").replace(/[\\{}]/g, (character) => `\\${character}`).replace(/[\r\n]+/g, " ");
    const citation = source.citation ?? {};
    downloadText("citation.bib", `@misc{studio_${source.id.replaceAll("-", "")},\n  title = {${escaped(source.title)}},\n  url = {${escaped(source.sourceUrl ?? source.url)}},\n  doi = {${escaped(citation.doi)}},\n  note = {Retained by Chemistry Studio; source ${source.id}}\n}\n`, "application/x-bibtex");
  };
  const title = view === "memory" ? "Research memory" : view === "downloads" ? "Downloads" : "Research library";
  const memories = library.data?.memory ?? [];
  const selectedMemory = memories.find((memory) => memory.id === selectedMemoryId) ?? memories[0];
  const sourceHost = (source: ResearchSource) => { try { const parsed = new URL(source.sourceUrl ?? source.url ?? ""); return ["http:", "https:"].includes(parsed.protocol) && parsed.hostname ? parsed.hostname : source.mediaType ?? "Saved file"; } catch { return source.mediaType ?? "Saved file"; } };
  return <div className="cs-library-page"><PageHeader title={title} actions={view === "memory" ? <Button variant="primary" onClick={() => setNewMemory(!newMemory)}>Add memory</Button> : view === "downloads" ? <Button onClick={() => void reveal()}>Open in Finder</Button> : <Button onClick={() => openAgent("Find and save sources for my current research.")}>Ask agent</Button>} />
    <nav className="cs-library-tabs" aria-label="Research library"><Link to="/library/research" aria-current={view === "research" ? "page" : undefined}>Discover</Link><Link to="/downloads" aria-current={view === "downloads" ? "page" : undefined}>Downloads</Link><Link to="/memory" aria-current={view === "memory" ? "page" : undefined}>Memory</Link><Link to="/notebooks">Notebooks</Link></nav>
    {(notice || library.error) && <p role="status" className="cs-workspace-notice">{notice ?? library.error}</p>}
    {view === "downloads" && <label className="cs-field cs-library-upload"><span className="cs-field__label">Add a file</span><Input aria-label="Retain a paper, dataset, or reference file" type="file" disabled={!!busy} onChange={(event) => { void uploadSource(event.target.files?.[0]); event.target.value = ""; }} /></label>}
    {view === "research" && <section className="cs-research-discovery" aria-label="Find sources"><form className="cs-research-search" onSubmit={(event) => void search(event)}><Input ref={resourceSearch} aria-label="Search resources" required value={query} placeholder="Search papers, compounds, or a DOI" onChange={(event) => setQuery(event.target.value)} /><Select value={connector} onValueChange={(selectedValue) => { const value = selectedValue === "__none" ? "" : selectedValue; setConnector(value); }}><SelectTrigger className="w-full" aria-label="Source"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="openalex">OpenAlex papers</SelectItem><SelectItem value="crossref">Crossref</SelectItem><SelectItem value="pubchem">PubChem</SelectItem><SelectItem value="web">Web search</SelectItem></SelectGroup></SelectContent></Select><Button type="submit" variant="primary" disabled={!!busy}>{busy === "search" ? "Searching…" : "Search"}</Button></form><details className="cs-source-url-disclosure"><summary>Save a URL</summary><form className="cs-research-url" onSubmit={(event) => { event.preventDefault(); void fetchSource(url); }}><Input aria-label="Save a source URL" type="url" required placeholder="https://…" value={url} onChange={(event) => setUrl(event.target.value)} /><Button type="submit" disabled={!!busy}>Save source</Button></form></details>
      {results.length > 0 && <div className="cs-source-search-results"><h2>{results.length} results</h2>{results.map((result, index) => <article className="cs-source-result" key={result.id ?? result.url ?? index}><div><h3>{result.title ?? "Resource"}</h3>{(result.snippet || result.abstract) && <p>{String(result.snippet ?? result.abstract).slice(0, 240)}</p>}{safeUrl(result.url) && <a href={safeUrl(result.url)} rel="noopener noreferrer" target="_blank">View source ↗</a>}</div>{safeUrl(result.downloadUrl ?? result.url) && <Button disabled={!!busy} onClick={() => void fetchSource(result.downloadUrl ?? result.url ?? "", result)}>{busy === (result.downloadUrl ?? result.url) ? "Saving…" : "Save"}</Button>}</article>)}</div>}
    </section>}
    {view === "memory" ? <><div className="cs-library-workbench"><section className="cs-library-rows" aria-label="Saved memories">{memories.length ? memories.map((memory) => <button className={`cs-library-row${memory.id === selectedMemory?.id ? " is-selected" : ""}`} key={memory.id} onClick={() => setSelectedMemoryId(memory.id)}><span><strong>{memory.title}</strong><small>{memory.stale ? "Source changed" : memory.sourceRefs?.length ? "Source linked" : "Personal memory"}</small></span><span aria-hidden="true">›</span></button>) : <div className="cs-friendly-empty"><h2>No memories yet</h2><p>Save a finding or a question to return to.</p></div>}</section>{selectedMemory && <section className="cs-library-inspector" aria-label="Memory details"><header><h2>{selectedMemory.title}</h2><span className="cs-count">{selectedMemory.stale ? "Needs review" : "Saved"}</span></header><MarkdownPreview content={selectedMemory.body} /><div className="cs-actions"><Button onClick={() => openAgent(`Continue research from this saved memory: ${selectedMemory.title}`, { memoryId: selectedMemory.id })}>Continue</Button><DropdownMenu><DropdownMenuTrigger asChild><Button>More</Button></DropdownMenuTrigger><DropdownMenuContent align="start"><DropdownMenuItem onSelect={() => void workspaceRequest(`/api/library/memory/${selectedMemory.id}`, { method: "DELETE" }).then(library.refresh).catch((e) => setNotice(messageOf(e)))}>Forget</DropdownMenuItem></DropdownMenuContent></DropdownMenu></div>{!!selectedMemory.sourceRefs?.length && <TechnicalDetails label="Sources" value={selectedMemory.sourceRefs} />}</section>}</div>{newMemory && <form className="cs-panel cs-memory-create" onSubmit={(event) => void saveMemory(event)}><header><h2>Add memory</h2><Button variant="ghost" onClick={() => setNewMemory(false)}>Close</Button></header><label className="cs-field"><span className="cs-field__label">Title</span><Input required value={memoryTitle} onChange={(event) => setMemoryTitle(event.target.value)} /></label><label className="cs-field"><span className="cs-field__label">Finding, decision, or question</span><Textarea rows={5} required value={memoryBody} onChange={(event) => setMemoryBody(event.target.value)} /></label><Button type="submit" disabled={!!busy}>Remember</Button></form>}</> : <>
      <div className="cs-library-list-heading"><h2>Saved sources <span className="cs-count">{library.data?.sources?.length ?? 0}</span></h2><Input aria-label="Filter saved sources" placeholder="Filter sources" value={sourceQuery} onChange={(event) => setSourceQuery(event.target.value)} /></div>
      <div className="cs-library-workbench"><section className="cs-library-rows" aria-label="Saved sources">{library.loading ? <p role="status">Loading sources…</p> : sources.length ? sources.map((source) => <article className={`cs-library-source-row${selected?.id === source.id ? " is-selected" : ""}`} key={source.id}><button aria-label={source.title} onClick={() => void selectSource(source.id)}><strong>{source.title}</strong><small>{sourceHost(source)}{source.createdAt ? ` · ${new Date(source.createdAt).toLocaleDateString()}` : ""}</small></button><a href={`/api/library/sources/${source.id}/content?format=original`} aria-label={`Open ${source.title}`}>Open ↗</a></article>) : <div className="cs-friendly-empty"><h2>No saved sources</h2><p>Saved papers and files stay available here.</p>{view === "downloads" && <Link className="cs-btn cs-btn--primary" to="/library/research">Find a source</Link>}</div>}</section>{selected ? <section className="cs-library-inspector" aria-label="Source details"><header><div><span className="cs-library-meta">{selected.mediaType ?? "Saved source"}</span><h2>{selected.title}</h2></div><Button variant="ghost" onClick={() => setSelected(null)}>Close</Button></header>{sourceHost(selected) !== selected.mediaType && <p className="cs-library-source-origin">{sourceHost(selected)}</p>}<div className="cs-actions"><a className="cs-btn cs-btn--primary" aria-label="Download original" href={`/api/library/sources/${selected.id}/content?format=original`}>Open ↗</a><DropdownMenu><DropdownMenuTrigger asChild><Button>Cite</Button></DropdownMenuTrigger><DropdownMenuContent align="start"><DropdownMenuItem onSelect={() => downloadText("citation.json", JSON.stringify(selected, null, 2), "application/json")}>Export citation</DropdownMenuItem><DropdownMenuItem onSelect={() => exportBibtex(selected)}>Export BibTeX</DropdownMenuItem></DropdownMenuContent></DropdownMenu><DropdownMenu><DropdownMenuTrigger asChild><Button>More</Button></DropdownMenuTrigger><DropdownMenuContent align="start"><DropdownMenuItem onSelect={() => openAgent(`Review my saved source ${selected.id}: ${selected.title}. Cite source passages and identify open questions.`, { sourceId: selected.id })}>Research source</DropdownMenuItem><DropdownMenuItem asChild><a href={`/api/library/sources/${selected.id}/content?format=text`}>Extracted text</a></DropdownMenuItem>{safeUrl(selected.sourceUrl ?? selected.url) && <DropdownMenuItem asChild><a href={safeUrl(selected.sourceUrl ?? selected.url)} target="_blank" rel="noopener noreferrer">Original website ↗</a></DropdownMenuItem>}{safeUrl(selected.sourceUrl ?? selected.url) && <DropdownMenuItem disabled={!!busy} onSelect={() => { setBusy("refresh"); void post<ResearchSource>("/api/library/sources/fetch", { url: selected.sourceUrl ?? selected.url, title: selected.title, citation: selected.citation ?? {}, forceRefresh: true }).then(async (source) => { setSelected(source); await library.refresh(); }).catch((e) => setNotice(messageOf(e))).finally(() => setBusy(null)); }}>Check for update</DropdownMenuItem>}</DropdownMenuContent></DropdownMenu></div><TechnicalDetails label="Citation and file details" value={{ file: selected.originalName, checksum: selected.checksum ?? selected.checksumSha256, saved: selected.createdAt, citation: selected.citation ?? selected.metadata }} /></section> : <section className="cs-library-inspector cs-library-inspector-empty"><p>Select a source to review its file and citation.</p></section>}</div>
      {view === "downloads" && library.data?.downloadsRoot && <details className="cs-library-storage"><summary>Storage location</summary><code>{library.data.downloadsRoot}</code></details>}
    </>}
  </div>;
}
