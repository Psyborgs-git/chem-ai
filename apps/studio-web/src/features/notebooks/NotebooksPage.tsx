import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button } from "../../components/atoms/Button";
import { PageHeader } from "../../components/layout/StudioLayout";
import { workspaceRequest } from "../../relay/network";
import { messageOf, patch, post, useWorkspace } from "../workspace/useWorkspace";
import { MarkdownPreview } from "./MarkdownPreview";
import { readNotebookDraft, removeNotebookDraft, writeNotebookDraft } from "./drafts";
import { openAgent } from "./ResearchLibraryPage";
import { FolderSettings, NotebookSettings } from "./NotebookSettings";
import type { Library, NotebookCitation, NotebookContent, NotebookPage, PageRevision, ResearchSource } from "./types";
import "./notebooks.css";

type PageDetail = NotebookPage & { revisions: PageRevision[] };
const blankContent: NotebookContent = { markdown: "" };

function StructurePreview({ smiles }: { smiles: string }) {
  const query = useWorkspace<{ canonicalSmiles?: string; formula?: string; svg?: string; error?: string }>(smiles.trim() ? `/api/library/structures/preview?smiles=${encodeURIComponent(smiles)}` : null);
  if (!smiles.trim()) return null;
  return <div className="cs-notebook-structure">{query.error || query.data?.error ? <p role="alert">{query.error ?? query.data?.error}</p> : query.loading ? <p>Checking structure…</p> : <>
    {query.data?.svg && <img alt={`Molecular structure of ${query.data.canonicalSmiles ?? smiles}`} src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(query.data.svg)}`} />}
    <div><strong>{query.data?.formula}</strong><code>{query.data?.canonicalSmiles}</code></div>
  </>}</div>;
}

export function PageEditor({ page, onSaved, flushRef, ownerKey, sources = [], aiEnabled = true, onTrashed, onRecovered }: { page: NotebookPage; onSaved: () => void; flushRef: React.RefObject<(() => Promise<void>) | null>; ownerKey?: string; sources?: ResearchSource[]; aiEnabled?: boolean; onTrashed?: () => void; onRecovered?: (id: string) => void }) {
  const recovered = useRef(readNotebookDraft(ownerKey, page.id));
  const [title, setTitle] = useState(recovered.current?.title ?? page.title);
  const [content, setContent] = useState<NotebookContent>(recovered.current?.content ?? page.content ?? blankContent);
  const [citations, setCitations] = useState<NotebookCitation[]>(recovered.current?.citations ?? page.citations ?? []);
  const [revision, setRevision] = useState(recovered.current?.revision ?? page.revision);
  const [dirty, setDirty] = useState(Boolean(recovered.current));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const [history, setHistory] = useState<PageRevision[] | null>(null);
  const [sourceId, setSourceId] = useState("");
  const [locator, setLocator] = useState("");
  const [reviewSource, setReviewSource] = useState("");
  const [confirmTrash, setConfirmTrash] = useState(false);
  const sourceReview = useWorkspace<ResearchSource & { extractedText?: string }>(reviewSource ? `/api/library/sources/${reviewSource}` : null);
  const generation = useRef(0);
  const inFlight = useRef<Promise<void> | null>(null);
  const latest = useRef({ title, content, citations, dirty, revision });
  latest.current = { title, content, citations, dirty, revision };
  useEffect(() => {
    if (dirty || saving || inFlight.current || page.revision <= latest.current.revision) return;
    const current = { title: page.title, content: page.content ?? blankContent, citations: page.citations ?? [], dirty: false, revision: page.revision };
    latest.current = current;
    setTitle(current.title); setContent(current.content); setCitations(current.citations); setRevision(current.revision);
  }, [page.title, page.content, page.citations, page.revision, dirty, saving]);
  const save = async (): Promise<void> => {
    if (inFlight.current) { await inFlight.current; if (latest.current.dirty) return save(); return; }
    const draft = latest.current;
    if (!draft.dirty) return;
    const savedGeneration = generation.current;
    setSaving(true); setError(null);
    const promise = patch<NotebookPage>(`/api/library/pages/${page.id}`, { title: draft.title, content: draft.content, citations: draft.citations, expectedRevision: draft.revision }).then((saved) => {
      setRevision(saved.revision); latest.current.revision = saved.revision;
      if (savedGeneration === generation.current) { setDirty(false); latest.current.dirty = false; removeNotebookDraft(ownerKey, page.id); }
      else writeNotebookDraft(ownerKey, page.id, latest.current);
      onSaved();
    }).catch((e: unknown) => { setError(messageOf(e)); throw e; }).finally(() => { setSaving(false); inFlight.current = null; });
    inFlight.current = promise;
    return promise;
  };
  flushRef.current = save;
  const saveRef = useRef(save);
  saveRef.current = save;
  useEffect(() => { if (dirty) writeNotebookDraft(ownerKey, page.id, latest.current); }, [dirty, title, content, citations, revision, ownerKey, page.id]);
  useEffect(() => {
    if (!dirty || saving || error) return;
    const timer = window.setTimeout(() => { void save().catch(() => undefined); }, 900);
    return () => window.clearTimeout(timer);
  });
  useEffect(() => {
    const leave = (event: BeforeUnloadEvent) => { if (latest.current.dirty) { writeNotebookDraft(ownerKey, page.id, latest.current); event.preventDefault(); } };
    window.addEventListener("beforeunload", leave);
    return () => { window.removeEventListener("beforeunload", leave); if (latest.current.dirty) { writeNotebookDraft(ownerKey, page.id, latest.current); void saveRef.current().catch(() => undefined); } };
  }, [ownerKey, page.id]);
  const change = (next: NotebookContent) => { generation.current++; setContent(next); setDirty(true); setError(null); };
  const loadHistory = async () => {
    try { const detail = await workspaceRequest<PageDetail>(`/api/library/pages/${page.id}`); setHistory(detail.revisions ?? []); }
    catch (e) { setError(messageOf(e)); }
  };
  const restore = (previous: PageRevision) => { generation.current++; setTitle(previous.title); setCitations(previous.citations ?? []); change(previous.content); setHistory(null); };
  const duplicate = async () => {
    try { const copy = await post<NotebookPage>("/api/library/pages", { notebookId: page.notebookId, title: `${title} (recovered draft)`, kind: page.kind, content, citations }); setDirty(false); latest.current.dirty = false; removeNotebookDraft(ownerKey, page.id); onSaved(); onRecovered?.(copy.id); setError("Your draft was saved as a separate page. Open the recovered draft from the page list."); }
    catch (e) { setError(messageOf(e)); }
  };
  const ask = async () => { try { await save(); openAgent(`Continue research from notebook page ${page.id}, “${latest.current.title}”. Read its current content and citations before proposing next steps.`, { notebookId: page.notebookId, pageId: page.id }); } catch (e) { setError(messageOf(e)); } };
  const trash = async () => { try { await save(); await workspaceRequest(`/api/library/pages/${page.id}?expectedRevision=${latest.current.revision}`, { method: "DELETE" }); latest.current.dirty = false; removeNotebookDraft(ownerKey, page.id); setConfirmTrash(false); onTrashed?.(); onSaved(); } catch (e) { setError(messageOf(e)); } };
  const changeCitations = (next: NotebookCitation[]) => { generation.current++; setCitations(next); setDirty(true); setError(null); };
  const attach = () => { const source = sources.find((item) => item.id === sourceId); if (!source) return; changeCitations([...citations, { sourceId: source.id, title: source.title, url: source.sourceUrl ?? source.url, locator: locator.trim() ? { text: locator.trim() } : {} }]); setSourceId(""); setLocator(""); };
  return <section className="cs-notebook-editor" aria-label="Notebook editor">
    <header className="cs-notebook-toolbar"><span className="cs-kicker">{page.kind} · private</span><span role="status" className="cs-field__hint">{saving ? "Saving…" : dirty ? "Unsaved changes" : `Saved · revision ${revision}`}</span><Button variant="ghost" onClick={() => setPreview(!preview)}>{preview ? "Edit" : "Preview"}</Button><Button variant="ghost" onClick={() => { void loadHistory(); }}>History</Button><Button onClick={() => { void save().catch(() => undefined); }} disabled={!dirty || saving}>Save</Button><Button disabled={!aiEnabled || saving} onClick={() => void ask()} title={!aiEnabled ? "Enable AI access in notebook settings first" : undefined}>Ask agent</Button><Button variant="ghost" disabled={saving} onClick={() => setConfirmTrash(true)}>Trash page</Button></header>
    {recovered.current && dirty && <p className="cs-field__hint" role="status">Your unsaved draft was recovered for this account.</p>}
    {error && <div className="cs-workspace-error" role="alert"><p>{error}</p>{dirty && <><p>Your draft is still open. Retry saving or preserve a separate copy.</p><Button onClick={() => { void duplicate(); }}>Save a separate copy</Button></>}</div>}
    <label className="cs-field"><span className="cs-field__label">Page title</span><input className="cs-input cs-notebook-title" value={title} onChange={(event) => { generation.current++; setTitle(event.target.value); setDirty(true); setError(null); }} /></label>
    {preview ? <div className="cs-notebook-preview">
      {content.latex && <MarkdownPreview content={`$$\n${content.latex}\n$$`} />}
      {content.smiles && <StructurePreview smiles={content.smiles} />}
      {!!content.ingredients?.length && <table><thead><tr><th>Ingredient</th><th>Amount</th><th>Unit</th></tr></thead><tbody>{content.ingredients.map((row, index) => <tr key={index}><td>{row.name}</td><td>{row.amount}</td><td>{row.unit}</td></tr>)}</tbody></table>}
      {!!content.steps?.length && <ol>{content.steps.map((step, index) => <li key={index}>{step}</li>)}</ol>}
      <MarkdownPreview content={content.markdown ?? ""} />
    </div> : <>
      {page.kind === "formula" && <label className="cs-field"><span className="cs-field__label">Formula · LaTeX</span><textarea className="cs-input cs-mono" rows={3} value={content.latex ?? ""} placeholder="c = \\frac{n}{V}" onChange={(event) => change({ ...content, latex: event.target.value })} /></label>}
      {page.kind === "smiles" && <label className="cs-field"><span className="cs-field__label">Molecular structure · SMILES</span><input className="cs-input cs-mono" value={content.smiles ?? ""} placeholder="CCO" onChange={(event) => change({ ...content, smiles: event.target.value })} /></label>}
      {page.kind === "recipe" && <div className="cs-recipe-editor"><h3>Ingredients</h3>{(content.ingredients ?? []).map((row, index) => <div className="cs-recipe-row" key={index}>{(["name", "amount", "unit"] as const).map((key) => <input className="cs-input" aria-label={`Ingredient ${index + 1} ${key}`} key={key} placeholder={key} value={row[key]} onChange={(event) => change({ ...content, ingredients: content.ingredients?.map((item, i) => i === index ? { ...item, [key]: event.target.value } : item) })} />)}<Button variant="ghost" aria-label={`Remove ingredient ${index + 1}`} onClick={() => change({ ...content, ingredients: content.ingredients?.filter((_, i) => i !== index) })}>×</Button></div>)}<Button onClick={() => change({ ...content, ingredients: [...(content.ingredients ?? []), { name: "", amount: "", unit: "" }] })}>Add ingredient</Button><label className="cs-field"><span className="cs-field__label">Procedure · one step per line</span><textarea className="cs-input" rows={5} value={(content.steps ?? []).join("\n")} onChange={(event) => change({ ...content, steps: event.target.value.split("\n") })} /></label></div>}
      <label className="cs-field cs-notebook-body"><span className="cs-field__label">Notes · Markdown and $LaTeX$ supported</span><textarea className="cs-input cs-mono" rows={18} value={content.markdown ?? ""} placeholder="Write your observations, references, ideas, or next research question…" onChange={(event) => change({ ...content, markdown: event.target.value })} /></label>
    </>}
    <section className="cs-notebook-citations" aria-label="Page citations"><h3>Sources and citations</h3>{citations.length ? <ol>{citations.map((citation, index) => <li key={`${citation.sourceId ?? citation.url}-${index}`}><div><strong>{citation.title ?? sources.find((source) => source.id === citation.sourceId)?.title ?? "Saved source"}</strong><small>{String(citation.locator?.text ?? "No passage locator")}</small>{citation.archiveStatus === "unavailable" && <small>Original could not be archived.</small>}</div>{citation.sourceId && <Button onClick={() => setReviewSource(citation.sourceId!)}>Review source</Button>}<Button variant="ghost" aria-label={`Remove citation ${index + 1}`} onClick={() => changeCitations(citations.filter((_, item) => item !== index))}>Remove</Button></li>)}</ol> : <p className="cs-field__hint">Attach saved resources to preserve the source behind this page.</p>}<div className="cs-citation-attach"><label className="cs-field"><span className="cs-field__label">Saved source</span><select className="cs-input" value={sourceId} onChange={(event) => setSourceId(event.target.value)}><option value="">Choose a source</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.title}</option>)}</select></label><label className="cs-field"><span className="cs-field__label">Passage, page or table</span><input className="cs-input" value={locator} maxLength={2000} placeholder="Page 4, Table 2" onChange={(event) => setLocator(event.target.value)} /></label><Button onClick={attach} disabled={!sourceId}>Attach citation</Button></div>{reviewSource && <div className="cs-notebook-source-review" aria-label="Citation source review"><header><h4>{sourceReview.data?.title ?? "Source review"}</h4><Button variant="ghost" onClick={() => setReviewSource("")}>Close source review</Button></header>{sourceReview.loading ? <p role="status">Loading your saved source…</p> : sourceReview.error ? <p role="alert">{sourceReview.error}</p> : <><p className="cs-field__hint">{sourceReview.data?.sourceUrl ?? sourceReview.data?.url}</p><code>{sourceReview.data?.checksum}</code><a className="cs-btn cs-btn--secondary" href={`/api/library/sources/${reviewSource}/content?format=original`}>Download cited original</a><MarkdownPreview content={(sourceReview.data?.extractedText ?? sourceReview.data?.text ?? "No text was extracted from this source.").slice(0,12000)} /></>}</div>}</section>
    {history && <section className="cs-notebook-history"><h3>Page history</h3><p className="cs-field__hint">Restoring copies an earlier revision into your draft. Save it to create a new revision.</p>{history.length ? history.map((old) => <div key={old.id ?? old.revision}><span>Revision {old.revision} · {old.title}</span><Button onClick={() => restore(old)}>Restore as new revision</Button></div>) : <p>No earlier revisions.</p>}<Button variant="ghost" onClick={() => setHistory(null)}>Close history</Button></section>}
    {confirmTrash && <div className="cs-notebook-trash-confirm" role="alertdialog" aria-labelledby="trash-page-title"><h3 id="trash-page-title">Move this page to trash?</h3><p>“{title}” and its history can be recovered from this notebook’s trash. Derived research memory will become stale.</p><div className="cs-actions"><Button variant="danger" onClick={() => void trash()} disabled={saving}>Move page to trash</Button><Button onClick={() => setConfirmTrash(false)}>Keep page</Button></div></div>}
  </section>;
}

export function NotebooksPage() {
  const { data, error, loading, refresh } = useWorkspace<Library>("/api/library");
  const [folderId, setFolderId] = useState("");
  const [notebookId, setNotebookId] = useState("");
  const [pageId, setPageId] = useState("");
  const [name, setName] = useState("");
  const [creating, setCreating] = useState<"folder" | "notebook" | null>(null);
  const [kind, setKind] = useState("note");
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const flushRef = useRef<(() => Promise<void>) | null>(null);
  const notebooks = (data?.notebooks ?? []).filter((n) => !folderId || n.folderId === folderId);
  const selectedNotebook = notebookId ? data?.notebooks.find((n) => n.id === notebookId) : notebooks[0];
  const selectedFolder = data?.folders.find((folder) => folder.id === folderId);
  const pages = (data?.pages ?? []).filter((p) => p.notebookId === selectedNotebook?.id && (!search || `${p.title} ${p.content?.markdown ?? ""}`.toLowerCase().includes(search.toLowerCase())));
  const selectedPage = pageId ? data?.pages.find((p) => p.id === pageId && p.notebookId === selectedNotebook?.id) : pages[0];
  const firstNotebookId = notebooks[0]?.id;
  const firstPageId = pages[0]?.id;
  useEffect(() => { if (!notebookId && firstNotebookId) setNotebookId(firstNotebookId); }, [notebookId, firstNotebookId]);
  useEffect(() => { if (!pageId && firstPageId) setPageId(firstPageId); }, [pageId, firstPageId]);
  const trashPages = (data?.trash ?? []).filter((page) => page.notebookId === selectedNotebook?.id);
  const restoreTrashed = async (page: NotebookPage) => { try { await flushRef.current?.(); const restored = await post<NotebookPage>(`/api/library/pages/${page.id}/restore`, { expectedRevision: page.revision }); setPageId(restored.id); await refresh(); } catch (e) { setNotice(messageOf(e)); } };
  const navigate = async (change: () => void) => { try { await flushRef.current?.(); flushRef.current = null; change(); setNotice(null); } catch { setNotice("Save or recover the current page before switching."); } };
  const create = async (event: FormEvent) => {
    event.preventDefault(); if (!name.trim() || busy) return; setBusy(true);
    try { await flushRef.current?.(); const record = await post<{ id: string }>(`/api/library/${creating === "folder" ? "folders" : "notebooks"}`, creating === "folder" ? { name, parentId: folderId || null } : { title: name, folderId: folderId || null }); if (creating === "folder") { setFolderId(record.id); setNotebookId(""); setPageId(""); } else { setNotebookId(record.id); setPageId(""); } setName(""); setCreating(null); await refresh(); }
    catch (e) { setNotice(messageOf(e)); } finally { setBusy(false); }
  };
  const createPage = async () => {
    if (!selectedNotebook || busy) return; setBusy(true);
    try { await flushRef.current?.(); const next = await post<NotebookPage>("/api/library/pages", { notebookId: selectedNotebook.id, title: `Untitled ${kind}`, kind, content: blankContent }); setPageId(next.id); await refresh(); }
    catch (e) { setNotice(messageOf(e)); } finally { setBusy(false); }
  };
  const folderOptions = (parent: string | null, depth = 0): React.ReactNode => (data?.folders ?? []).filter((f) => f.parentId === parent).flatMap((f) => [<option key={f.id} value={f.id}>{`${"— ".repeat(depth)}${f.name}`}</option>, folderOptions(f.id, depth + 1)]);
  return <div className="cs-notebooks-page"><PageHeader eyebrow="Your private library" title="Notebooks" description="Keep observations, recipes, formulae, and structures together. Your agent can use them to continue your research." actions={<div className="cs-actions"><Button onClick={() => setCreating("folder")}>New folder</Button><Button variant="primary" onClick={() => setCreating("notebook")}>New notebook</Button></div>} />
    {(error || notice) && <p className="cs-workspace-error" role="alert">{notice ?? error}</p>}
    {creating && <form className="cs-inline-create" onSubmit={(event) => { void create(event); }}><label className="cs-field"><span className="cs-field__label">{creating === "folder" ? "Folder name" : "Notebook title"}</span><input autoFocus className="cs-input" value={name} required maxLength={creating === "folder" ? 200 : 300} onChange={(event) => setName(event.target.value)} /></label><Button type="submit" variant="primary" disabled={busy}>Create {creating}</Button><Button onClick={() => setCreating(null)}>Cancel</Button></form>}
    {loading ? <p role="status">Loading your notebooks…</p> : <div className="cs-notebook-workspace"><aside className="cs-notebook-index" aria-label="Notebooks and pages"><label className="cs-field"><span className="cs-field__label">Folder</span><select className="cs-input" value={folderId} onChange={(event) => { const value = event.target.value; void navigate(() => { setFolderId(value); setNotebookId(""); setPageId(""); }); }}><option value="">All folders</option>{folderOptions(null)}</select></label>
      {selectedFolder && <FolderSettings key={selectedFolder.id} folder={selectedFolder} folders={data?.folders ?? []} refresh={refresh} onError={setNotice} />}
      <div className="cs-notebook-list">{notebooks.map((notebook) => <button key={notebook.id} className={notebook.id === selectedNotebook?.id ? "is-selected" : ""} onClick={() => { void navigate(() => { setNotebookId(notebook.id); setPageId(""); }); }}><span aria-hidden="true">▤</span>{notebook.title}</button>)}</div>
      {selectedNotebook && <><div className="cs-notebook-index-heading"><h2>{selectedNotebook.title}</h2><span className="cs-count">{pages.length}</span></div><input className="cs-input" aria-label="Search pages" placeholder="Find a page…" value={search} onChange={(event) => setSearch(event.target.value)} /><div className="cs-notebook-page-list">{pages.map((page) => <button className={page.id === selectedPage?.id ? "is-selected" : ""} key={page.id} onClick={() => { void navigate(() => setPageId(page.id)); }}><span>{page.title}</span><small>{page.kind}</small></button>)}</div><div className="cs-new-page"><select className="cs-input" aria-label="New page kind" value={kind} onChange={(event) => setKind(event.target.value)}><option value="note">Note</option><option value="recipe">Recipe</option><option value="formula">Formula</option><option value="smiles">SMILES structure</option></select><Button onClick={() => { void createPage(); }} disabled={busy}>Add page</Button></div><NotebookSettings key={selectedNotebook.id} notebook={selectedNotebook} folders={data?.folders ?? []} refresh={refresh} onError={setNotice} />{trashPages.length > 0 && <details className="cs-notebook-settings"><summary>Trash ({trashPages.length})</summary>{trashPages.map((page) => <div key={page.id}><p>{page.title}</p><Button onClick={() => void restoreTrashed(page)}>Restore page</Button></div>)}</details>}</>}
      <p className="cs-field__hint">Only you and your delegated agent can access this library. You control AI access and local training for each notebook.</p>
    </aside>{selectedPage ? <PageEditor key={`${data?.ownerKey}:${selectedPage.id}`} page={selectedPage} ownerKey={data?.ownerKey} sources={data?.sources ?? []} aiEnabled={selectedNotebook?.aiEnabled !== false} flushRef={flushRef} onSaved={() => { void refresh(); }} onTrashed={() => setPageId("")} onRecovered={setPageId} /> : <div className="cs-friendly-empty"><span className="cs-notebook-empty-symbol" aria-hidden="true">▤</span><h2>{selectedNotebook ? "A fresh page for your next idea" : "Your research, remembered"}</h2><p>{selectedNotebook ? "Add a note, recipe, formula, or molecular structure to this notebook." : "Create a private notebook to start collecting your work."}</p><Button variant="primary" onClick={() => selectedNotebook ? void createPage() : setCreating("notebook")}>{selectedNotebook ? "Add first page" : "Create first notebook"}</Button></div>}</div>}
  </div>;
}
