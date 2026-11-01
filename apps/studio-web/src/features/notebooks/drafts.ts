import type { NotebookCitation, NotebookContent } from "./types";

export type NotebookDraft = { title: string; content: NotebookContent; citations: NotebookCitation[]; revision: number };
const PREFIX = "chemistry-studio:private-notebook-draft:";
const key = (ownerKey: string, pageId: string) => `${PREFIX}${encodeURIComponent(ownerKey)}:${pageId}`;

export function readNotebookDraft(ownerKey: string | undefined, pageId: string): NotebookDraft | null {
  if (!ownerKey) return null;
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(key(ownerKey, pageId)) ?? "null");
    if (!value || typeof value !== "object") return null;
    const draft = value as Partial<NotebookDraft>;
    return typeof draft.title === "string" && draft.content && typeof draft.content === "object" &&
      typeof draft.revision === "number" && Array.isArray(draft.citations) ? draft as NotebookDraft : null;
  } catch { return null; }
}
export function writeNotebookDraft(ownerKey: string | undefined, pageId: string, value: NotebookDraft): boolean {
  if (!ownerKey) return false;
  try { sessionStorage.setItem(key(ownerKey, pageId), JSON.stringify(value)); return true; } catch { return false; }
}
export function removeNotebookDraft(ownerKey: string | undefined, pageId: string) {
  if (ownerKey) { try { sessionStorage.removeItem(key(ownerKey, pageId)); } catch { /* Draft remains in memory. */ } }
}
export function clearNotebookDrafts() {
  try { for (let index = sessionStorage.length - 1; index >= 0; index--) { const name = sessionStorage.key(index); if (name?.startsWith(PREFIX)) sessionStorage.removeItem(name); } } catch { /* Storage can be unavailable. */ }
}
if (typeof window !== "undefined") window.addEventListener("studio-auth-cleared", clearNotebookDrafts);
