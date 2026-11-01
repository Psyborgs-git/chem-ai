import { Input } from "@/components/ui/input";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectGroup, SelectItem } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { useState, type ReactNode } from "react";
import { Button } from "../../components/atoms/Button";
import { messageOf, patch } from "../workspace/useWorkspace";
import type { Notebook, NotebookFolder } from "./types";

function options(folders: NotebookFolder[], parent: string | null = null, depth = 0, excluded = new Set<string>()): ReactNode[] {
  if (depth > folders.length) return [];
  return folders.filter((folder) => folder.parentId === parent && !excluded.has(folder.id)).flatMap((folder) => [
    <SelectItem key={folder.id} value={folder.id}>{`${"— ".repeat(depth)}${folder.name}`}</SelectItem>,
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
  return <details className="cs-notebook-settings"><summary>Notebook settings</summary><form onSubmit={(event) => { event.preventDefault(); void save({ title }); }}><label className="cs-field"><span className="cs-field__label">Notebook title</span><Input value={title} required maxLength={300} onChange={(event) => setTitle(event.target.value)} /></label><Button type="submit" disabled={busy}>Rename notebook</Button></form><label className="cs-field"><span className="cs-field__label">Move notebook to folder</span><Select disabled={busy} value={notebook.folderId ?? ""} onValueChange={(selectedValue) => { const value = selectedValue === "__none" ? "" : selectedValue; void save({ folderId: value || null }); }}><SelectTrigger className="w-full" aria-label="Move notebook to folder"><SelectValue placeholder="Unfiled" /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="__none">Unfiled</SelectItem>{options(folders)}</SelectGroup></SelectContent></Select></label><div className="flex items-center gap-2 py-2"><Checkbox id={`notebook-ai-${notebook.id}`} checked={notebook.aiEnabled !== false} disabled={busy} onCheckedChange={(checked) => void save({ aiEnabled: checked === true })} /><Label htmlFor={`notebook-ai-${notebook.id}`}>Allow my agent to use this notebook</Label></div><div className="flex items-center gap-2 py-2"><Checkbox id={`notebook-training-${notebook.id}`} checked={notebook.trainingEnabled !== false} disabled={busy} onCheckedChange={(checked) => void save({ trainingEnabled: checked === true })} /><Label htmlFor={`notebook-training-${notebook.id}`}>Allow local training from this notebook</Label></div><p className="cs-field__hint">Private notebook access and permission to send content to an external provider are separate settings.</p></details>;
}
export function FolderSettings({ folder, folders, refresh, onError }: { folder: NotebookFolder; folders: NotebookFolder[]; refresh: () => Promise<void>; onError: (message: string) => void }) {
  const [name, setName] = useState(folder.name);
  const [parentId, setParentId] = useState(folder.parentId ?? "");
  const [busy, setBusy] = useState(false);
  return <details className="cs-notebook-settings"><summary>Folder settings</summary><form onSubmit={(event) => {
    event.preventDefault(); if (busy) return; setBusy(true);
    void patch(`/api/library/folders/${folder.id}`, { name, parentId: parentId || null, expectedRevision: folder.revision }).then(refresh).catch((e) => onError(messageOf(e))).finally(() => setBusy(false));
  }}><label className="cs-field"><span className="cs-field__label">Folder name</span><Input value={name} maxLength={200} required onChange={(event) => setName(event.target.value)} /></label><label className="cs-field"><span className="cs-field__label">Parent folder</span><Select value={parentId} onValueChange={(selectedValue) => { const value = selectedValue === "__none" ? "" : selectedValue; setParentId(value); }}><SelectTrigger className="w-full" aria-label="Parent folder"><SelectValue placeholder="Top level" /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="__none">Top level</SelectItem>{options(folders, null, 0, new Set([folder.id]))}</SelectGroup></SelectContent></Select></label><Button type="submit" disabled={busy}>Save folder</Button></form></details>;
}
