import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { createRef } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NotebooksPage, PageEditor } from "./NotebooksPage";
import { NotebookSettings } from "./NotebookSettings";
import { clearNotebookDrafts, readNotebookDraft } from "./drafts";
import type { Library, NotebookPage } from "./types";

const state = vi.hoisted(() => ({
  patch: vi.fn(), post: vi.fn(), request: vi.fn(), refresh: vi.fn(),
  library: null as Library | null,
  source: { id: "own-source", title: "My retained paper", sourceUrl: "https://example.org/paper", checksum: "recorded-sha", extractedText: "Source-backed ethanol result." },
}));
vi.mock("../../relay/network", () => ({ workspaceRequest: state.request }));
vi.mock("../workspace/useWorkspace", () => ({
  patch: state.patch, post: state.post,
  messageOf: (error: unknown) => error instanceof Error ? error.message : "Request failed",
  useWorkspace: (path: string | null) => ({ data: path === "/api/library" ? state.library : path === "/api/library/sources/own-source" ? state.source : null, error: null, loading: false, refresh: state.refresh }),
}));
vi.mock("./MarkdownPreview", () => ({ MarkdownPreview: ({ content }: { content: string }) => <div>{content}</div> }));

const page: NotebookPage = { id: "private-page", notebookId: "private-notebook", title: "Ethanol notes", kind: "note", revision: 1, content: { markdown: "Original note" }, citations: [] };
const savePage = async () => { await userEvent.click(screen.getByRole("button", { name: "Page actions" })); await userEvent.click(await screen.findByRole("menuitem", { name: "Save" })); };
const props = () => ({ page, ownerKey: "workspace:alice", onSaved: vi.fn(), flushRef: createRef<(() => Promise<void>) | null>() });
afterEach(() => { cleanup(); clearNotebookDrafts(); vi.restoreAllMocks(); });
beforeEach(() => { clearNotebookDrafts(); state.patch.mockReset().mockResolvedValue({ ...page, revision: 2 }); state.post.mockReset().mockResolvedValue({ ...page, id: "recovered-page" }); state.request.mockReset(); state.refresh.mockReset().mockResolvedValue(undefined); state.library = null; });

describe("private notebook editor", () => {
  it("adopts an agent's newer page revision only while the editor is clean", async () => {
    const editorProps = props();
    const view = render(<PageEditor {...editorProps} />);
    const updated = { ...page, title: "Agent updated this page", revision: 3, content: { markdown: "New source-backed findings" }, citations: [{ sourceId: "own-source", title: "Retained source" }] };
    state.patch.mockResolvedValue({ ...updated, revision: 4 });
    view.rerender(<PageEditor {...editorProps} page={updated} />);
    expect(screen.getByLabelText("Notes · Markdown and $LaTeX$ supported")).toHaveValue("New source-backed findings");
    fireEvent.change(screen.getByLabelText("Notes · Markdown and $LaTeX$ supported"), { target: { value: "My follow-up to the new findings" } });
    await savePage();
    await waitFor(() => expect(state.patch).toHaveBeenCalledWith("/api/library/pages/private-page", expect.objectContaining({ title: updated.title, expectedRevision: 3, content: { markdown: "My follow-up to the new findings" }, citations: updated.citations })));
  });

  it("preserves a dirty draft and its conflict revision when an agent updates the page", async () => {
    state.patch.mockRejectedValue(new Error("Revision conflict"));
    const editorProps = props();
    const view = render(<PageEditor {...editorProps} />);
    fireEvent.change(screen.getByLabelText("Notes · Markdown and $LaTeX$ supported"), { target: { value: "My unsaved observation" } });
    view.rerender(<PageEditor {...editorProps} page={{ ...page, revision: 3, content: { markdown: "Agent update" } }} />);
    expect(screen.getByLabelText("Notes · Markdown and $LaTeX$ supported")).toHaveValue("My unsaved observation");
    await savePage();
    await waitFor(() => expect(state.patch).toHaveBeenCalledWith("/api/library/pages/private-page", expect.objectContaining({ expectedRevision: 1, content: { markdown: "My unsaved observation" } })));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Revision conflict"));
    expect(readNotebookDraft("workspace:alice", page.id)?.content.markdown).toBe("My unsaved observation");
  });

  it("does not roll back a saved revision when an older library response arrives", async () => {
    const editorProps = props();
    const view = render(<PageEditor {...editorProps} />);
    fireEvent.change(screen.getByLabelText("Notes · Markdown and $LaTeX$ supported"), { target: { value: "Saved current observation" } });
    await savePage();
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Saved"));
    view.rerender(<PageEditor {...editorProps} page={{ ...page }} />);
    expect(screen.getByLabelText("Notes · Markdown and $LaTeX$ supported")).toHaveValue("Saved current observation");
    fireEvent.change(screen.getByLabelText("Notes · Markdown and $LaTeX$ supported"), { target: { value: "Another observation" } });
    await savePage();
    await waitFor(() => expect(state.patch).toHaveBeenLastCalledWith("/api/library/pages/private-page", expect.objectContaining({ expectedRevision: 2 })));
  });

  it("retains the draft after a revision conflict and recovers it only for its owner", async () => {
    state.patch.mockRejectedValue(new Error("Page changed since expected revision; reload and retry"));
    const first = render(<PageEditor {...props()} />);
    fireEvent.change(screen.getByLabelText("Notes · Markdown and $LaTeX$ supported"), { target: { value: "Unsaved private observation" } });
    await savePage();
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Page changed"));
    expect((screen.getByLabelText("Notes · Markdown and $LaTeX$ supported") as HTMLTextAreaElement).value).toBe("Unsaved private observation");
    expect(readNotebookDraft("workspace:alice", page.id)?.content.markdown).toBe("Unsaved private observation");
    expect(readNotebookDraft("workspace:admin", page.id)).toBeNull();
    first.unmount();
    render(<PageEditor {...props()} />);
    expect((screen.getByLabelText("Notes · Markdown and $LaTeX$ supported") as HTMLTextAreaElement).value).toBe("Unsaved private observation");
    expect(screen.getByText("Your unsaved draft was recovered for this account.")).toBeTruthy();
  });

  it("attaches a saved source with its exact locator and reviews only the selected owner source", async () => {
    render(<PageEditor {...props()} sources={[state.source]} />);
    expect(state.request).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("combobox", { name: "Saved source" }));
    await userEvent.click(await screen.findByRole("option", { name: "My retained paper" }));
    fireEvent.change(screen.getByLabelText("Passage, page or table"), { target: { value: "Page 4, Table 2" } });
    fireEvent.click(screen.getByRole("button", { name: "Attach citation" }));
    await savePage();
    await waitFor(() => expect(state.patch).toHaveBeenCalledWith("/api/library/pages/private-page", expect.objectContaining({ citations: [{ sourceId: "own-source", title: "My retained paper", url: "https://example.org/paper", locator: { text: "Page 4, Table 2" } }] })));
    fireEvent.click(screen.getByRole("button", { name: "Review source" }));
    expect(screen.getByLabelText("Citation source review").textContent).toContain("Source-backed ethanol result.");
    expect(screen.getByRole("link", { name: "Download cited original" }).getAttribute("href")).toBe("/api/library/sources/own-source/content?format=original");
    expect(screen.queryByText("Other owner's private paper")).toBeNull();
  });

  it("requires explicit trash confirmation and keeps current changes on cancel", async () => {
    render(<PageEditor {...props()} />);
    await userEvent.click(screen.getByRole("button", { name: "Page actions" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Trash page" }));
    expect(screen.getByRole("alertdialog")).toBeTruthy();
    expect(state.request).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Keep page" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(state.request).not.toHaveBeenCalled();
  });

  it("passes notebook and page context to the agent after saving", async () => {
    const listener = vi.fn(); window.addEventListener("studio-agent-open", listener);
    render(<PageEditor {...props()} />);
    fireEvent.click(screen.getByRole("button", { name: "Ask agent" }));
    await waitFor(() => expect(listener).toHaveBeenCalled());
    expect((listener.mock.calls[0][0] as CustomEvent).detail).toEqual(expect.objectContaining({ notebookId: "private-notebook", pageId: "private-page" }));
    window.removeEventListener("studio-agent-open", listener);
  });
});

it("clears the previous notebook and page when creating an empty folder", async () => {
  state.library = { ownerKey: "workspace:alice", folders: [], notebooks: [{ id: page.notebookId, title: "Existing notebook", folderId: null, revision: 1 }], pages: [page], sources: [], memory: [], downloadsRoot: "/tmp/private-downloads" };
  state.post.mockResolvedValue({ id: "new-empty-folder" });
  state.refresh.mockImplementation(async () => { state.library = { ...state.library!, folders: [{ id: "new-empty-folder", name: "New folder", parentId: null, revision: 1 }] }; });
  render(<MemoryRouter><NotebooksPage /></MemoryRouter>);
  expect(screen.getByLabelText("Notes · Markdown and $LaTeX$ supported")).toHaveValue("Original note");
  fireEvent.click(screen.getByRole("button", { name: "New folder" }));
  fireEvent.change(screen.getByLabelText("Folder name"), { target: { value: "New folder" } });
  fireEvent.click(screen.getByRole("button", { name: "Create folder" }));
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Folder" })).toHaveTextContent("New folder"));
  expect(screen.queryByLabelText("Notes · Markdown and $LaTeX$ supported")).toBeNull();
  expect(screen.getByRole("button", { name: "Create first notebook" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "Add page" })).toBeNull();
});

it("keeps unfiled and notebook privacy choices intact through the custom controls", async () => {
  const refresh = vi.fn().mockResolvedValue(undefined);
  const onError = vi.fn();
  render(<NotebookSettings notebook={{ id: "private-notebook", title: "Private notes", revision: 7, folderId: "folder-one", aiEnabled: true, trainingEnabled: true }} folders={[{ id: "folder-one", name: "Research", revision: 1, parentId: null }]} refresh={refresh} onError={onError} />);
  fireEvent.click(screen.getByText("Notebook settings", { exact: true }));
  await userEvent.click(screen.getByRole("combobox", { name: "Move notebook to folder" }));
  await userEvent.click(await screen.findByRole("option", { name: "Unfiled" }));
  await waitFor(() => expect(state.patch).toHaveBeenCalledWith("/api/library/notebooks/private-notebook", { folderId: null, expectedRevision: 7 }));
  await waitFor(() => expect(screen.getByRole("checkbox", { name: "Allow my agent to use this notebook" })).toBeEnabled());
  await userEvent.click(screen.getByRole("checkbox", { name: "Allow my agent to use this notebook" }));
  await waitFor(() => expect(state.patch).toHaveBeenCalledWith("/api/library/notebooks/private-notebook", { aiEnabled: false, expectedRevision: 7 }));
  expect(screen.getByRole("checkbox", { name: "Allow local training from this notebook" })).toBeChecked();
  expect(onError).not.toHaveBeenCalled();
  expect(JSON.stringify(state.patch.mock.calls)).not.toContain("__none");
});


it("opens a blank notebook form from a shortcut without creating anything", async () => {
  state.library = { ownerKey: "workspace:alice", folders: [], notebooks: [], pages: [], sources: [], memory: [], downloadsRoot: "/tmp/private-downloads" };
  render(<MemoryRouter initialEntries={["/notebooks?new=notebook"]}><NotebooksPage /></MemoryRouter>);
  expect(await screen.findByRole("button", { name: "Create notebook" })).toBeVisible();
  expect(screen.getByLabelText("Notebook title")).toHaveValue("");
  expect(state.post).not.toHaveBeenCalled();
});

it("opens the exact owned page selected in workspace search", async () => {
  const second = { ...page, id: "second-page", notebookId: "second-notebook", title: "Selected search result", content: { markdown: "Selected owned content" } };
  state.library = { ownerKey: "workspace:alice", folders: [], notebooks: [{ id: page.notebookId, title: "First notebook", folderId: null, revision: 1 }, { id: second.notebookId, title: "Search notebook", folderId: null, revision: 1 }], pages: [page, second], sources: [], memory: [], downloadsRoot: "/tmp/private-downloads" };
  render(<MemoryRouter initialEntries={["/notebooks?notebook=second-notebook&page=second-page"]}><NotebooksPage /></MemoryRouter>);
  await waitFor(() => expect(screen.getByLabelText("Page title")).toHaveValue("Selected search result"));
  expect(screen.getByLabelText("Notes · Markdown and $LaTeX$ supported")).toHaveValue("Selected owned content");
  expect(state.post).not.toHaveBeenCalled();
});
