import userEvent from "@testing-library/user-event";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ResearchLibraryPage } from "./ResearchLibraryPage";
const state = vi.hoisted(() => ({ request: vi.fn(), post: vi.fn(), refresh: vi.fn() }));
const source = { id: "paper-one", title: "Silk fibre structure", sourceUrl: "https://example.org/silk", originalName: "silk.pdf", mediaType: "application/pdf", checksum: "retained-checksum", citation: { doi: "10.1000/example" } };
const memory = { id: "memory-one", title: "Test crystallinity next", body: "Compare wet-state tensile strength.", sourceRefs: [{ kind: "page", id: "private-page", revision: 1 }] };
vi.mock("../../relay/network", () => ({ workspaceRequest: state.request }));
vi.mock("../workspace/useWorkspace", () => ({ post: state.post, messageOf: (error: Error) => error.message, useWorkspace: () => ({ data: { sources: [source], memory: [memory], notebooks: [], folders: [], pages: [], downloadsRoot: "/private/review-copies" }, loading: false, error: null, refresh: state.refresh }) }));
vi.mock("./MarkdownPreview", () => ({ MarkdownPreview: ({ content }: { content: string }) => <div>{content}</div> }));
afterEach(cleanup);
beforeEach(() => { state.request.mockReset().mockResolvedValue(source); state.post.mockReset(); state.refresh.mockReset().mockResolvedValue(undefined); });
describe("research library workbench", () => {
  it("focuses the paper-search shortcut without starting a search", () => {
    render(<MemoryRouter initialEntries={["/library/research?focus=search"]}><ResearchLibraryPage /></MemoryRouter>);
    expect(screen.getByRole("textbox", { name: "Search resources" })).toHaveFocus();
    expect(state.request).not.toHaveBeenCalled();
    expect(state.post).not.toHaveBeenCalled();
  });
  it("opens the exact saved source selected in the command palette", async () => {
    render(<MemoryRouter initialEntries={["/downloads?source=paper-one"]}><ResearchLibraryPage view="downloads" /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole("region", { name: "Source details" })).toHaveTextContent(source.title));
    expect(state.request).toHaveBeenCalledWith("/api/library/sources/paper-one");
    expect(state.post).not.toHaveBeenCalled();
  });
  it("opens a selected source inspector with original and citation actions, keeping exact metadata collapsed", async () => {
    render(<MemoryRouter><ResearchLibraryPage view="downloads" /></MemoryRouter>);
    expect(screen.getByText("Select a source to review its file and citation.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /Silk fibre structure/ }));
    const inspector = await screen.findByRole("region", { name: "Source details" });
    expect(within(inspector).getByRole("link", { name: "Download original" })).toHaveAttribute("href", "/api/library/sources/paper-one/content?format=original");
    expect(within(inspector).getByText(/retained-checksum/)).not.toBeVisible();
    await userEvent.click(within(inspector).getByRole("button", { name: "Cite" }));
    expect(await screen.findByRole("menuitem", { name: "Export BibTeX" })).toBeVisible();
    await userEvent.keyboard("{Escape}");
    fireEvent.click(within(inspector).getByText("Citation and file details", { exact: true }));
    expect(within(inspector).getByText(/retained-checksum/)).toBeVisible();
  });
  it("shows memory content in the selected inspector and opens a blank form only on request", () => {
    render(<MemoryRouter><ResearchLibraryPage view="memory" /></MemoryRouter>);
    expect(screen.getByRole("region", { name: "Memory details" })).toHaveTextContent(memory.body);
    expect(screen.queryByLabelText("Finding, decision, or question")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Add memory" }));
    expect(screen.getByLabelText("Finding, decision, or question")).toBeVisible();
    expect(screen.getByLabelText("Finding, decision, or question")).toHaveValue("");
  });
  it("continues from the selected memory with its owned context ID", async () => {
    const listener = vi.fn(); window.addEventListener("studio-agent-open", listener);
    render(<MemoryRouter><ResearchLibraryPage view="memory" /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(listener).toHaveBeenCalled());
    expect((listener.mock.calls[0][0] as CustomEvent).detail).toEqual(expect.objectContaining({ memoryId: "memory-one" }));
    window.removeEventListener("studio-agent-open", listener);
  });
  it("searches the chosen resource connector through the custom source picker", async () => {
    state.request.mockResolvedValue({ results: [] });
    render(<MemoryRouter><ResearchLibraryPage /></MemoryRouter>);
    await userEvent.click(screen.getByRole("combobox", { name: "Source" }));
    await userEvent.click(await screen.findByRole("option", { name: "Crossref" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Search resources" }), { target: { value: "silk hand" } });
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(state.request).toHaveBeenCalledWith("/api/library/research/search?connector=crossref&q=silk%20hand"));
  });
});
