import { useState, type ReactNode } from "react";
import { Button } from "../../components/atoms/Button";
import { Checkbox } from "../../components/atoms/Checkbox";
import { messageOf, patch } from "../workspace/useWorkspace";
import type { Notebook, NotebookFolder } from "./types";

function options(folders: NotebookFolder[], parent: string | null = null, depth = 0, excluded = new Set<string>()): ReactNode[] {
  if (depth > folders.length) return [];
  return folders.filter((folder) => folder.parentId === parent && !excluded.has(folder.id)).flatMap((folder) => [
    <option key={folder.id} value={folder.id}>{`${"— ".repeat(depth)}${folder.name}`}</option>,
    ...options(folders, folder.id, depth + 1, excluded),
  ]);
}
export function NotebookSettings({ notebook, folders, refresh, onError }: { notebook: Notebook; folders: NotebookFolder[]; refresh: () => Promise<void>; onError: (message: string) => void }) {
  const [title, setTitle] = useState(notebook.title);
  const [busy, setBusy] = useState(false);
  const save = async (values: Record<string, unknown>) => {
    if (busy) return; setBusy(true);
    try { await patch(`/api/library/notebooks/${notebook.id}`, { ...values, expectedRevision: notebook.revision }); await refresh(); }
    catch (e) { onError(messageOf(e)); } finally { setBusy(false); }
  };
  return <details className="cs-notebook-settings"><summary>Notebook settings</summary><form onSubmit={(event) => { event.preventDefault(); void save({ title }); }}><label className="cs-field"><span className="cs-field__label">Notebook title</span><input className="cs-input" value={title} required maxLength={300} onChange={(event) => setTitle(event.target.value)} /></label><Button type="submit" disabled={busy}>Rename notebook</Button></form><label className="cs-field"><span className="cs-field__label">Move notebook to folder</span><select className="cs-input" disabled={busy} value={notebook.folderId ?? ""} onChange={(event) => void save({ folderId: event.target.value || null })}><option value="">Unfiled</option>{options(folders)}</select></label><Checkbox label="Allow my agent to use this notebook" checked={notebook.aiEnabled !== false} disabled={busy} onChange={(event) => void save({ aiEnabled: event.target.checked })} /><Checkbox label="Allow local training from this notebook" checked={notebook.trainingEnabled !== false} disabled={busy} onChange={(event) => void save({ trainingEnabled: event.target.checked })} /><p className="cs-field__hint">Private notebook access and permission to send content to an external provider are separate settings.</p></details>;
}
export function FolderSettings({ folder, folders, refresh, onError }: { folder: NotebookFolder; folders: NotebookFolder[]; refresh: () => Promise<void>; onError: (message: string) => void }) {
  const [name, setName] = useState(folder.name);
  const [parentId, setParentId] = useState(folder.parentId ?? "");
  const [busy, setBusy] = useState(false);
  return <details className="cs-notebook-settings"><summary>Folder settings</summary><form onSubmit={(event) => {
    event.preventDefault(); if (busy) return; setBusy(true);
    void patch(`/api/library/folders/${folder.id}`, { name, parentId: parentId || null, expectedRevision: folder.revision }).then(refresh).catch((e) => onError(messageOf(e))).finally(() => setBusy(false));
  }}><label className="cs-field"><span className="cs-field__label">Folder name</span><input className="cs-input" value={name} maxLength={200} required onChange={(event) => setName(event.target.value)} /></label><label className="cs-field"><span className="cs-field__label">Parent folder</span><select className="cs-input" value={parentId} onChange={(event) => setParentId(event.target.value)}><option value="">Top level</option>{options(folders, null, 0, new Set([folder.id]))}</select></label><Button type="submit" disabled={busy}>Save folder</Button></form></details>;
}
