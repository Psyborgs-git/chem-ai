import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { describe, expect, it, vi } from "vitest";
const state = vi.hoisted(() => ({ paths: [] as (string | null)[], pending: false }));
vi.mock("react-relay", () => ({ graphql: () => ({}), useLazyLoadQuery: () => { if (state.pending) throw new Promise(() => {}); return { projects: { edges: [{ node: { id: "project-one", name: "Silk programme" } }] }, tasks: { edges: [{ node: { id: "task-one", title: "Silk yarn study", project: { name: "Silk programme" } } }] } }; } }));
vi.mock("../../features/workspace/useWorkspace", () => ({ useWorkspace: (path: string | null) => { state.paths.push(path); return { data: path?.includes("silk") ? { results: [{ kind: "source", id: "source-one", title: "Retained silk paper" }] } : null, loading: false, error: null }; } }));
import { WorkspaceFinder, resourceDestination } from "./WorkspaceFinder";
function Location() { const location = useLocation(); return <output data-testid="location">{location.pathname}{location.search}</output>; }
function mount() { return render(<MemoryRouter><WorkspaceFinder open onClose={() => {}} /><Location /></MemoryRouter>); }

describe("workspace command search", () => {
  it("finds an owned saved resource and waits for selection before navigating", async () => {
    state.paths = []; mount();
    const dialog = screen.getByRole("dialog", { name: "Find your work" });
    expect(dialog).toBeVisible();
    await userEvent.type(screen.getByRole("combobox", { name: "Search your workspace" }), "silk");
    const item = await screen.findByRole("option", { name: /Retained silk paper/ });
    expect(screen.getByTestId("location")).toHaveTextContent("/");
    expect(state.paths).toContain("/api/library/search?q=silk&limit=12");
    await userEvent.click(item);
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/downloads?source=source-one"));
  });
  it("offers actual task routes and an agent opener without inference", async () => {
    const listener = vi.fn(); window.addEventListener("studio-agent-open", listener);
    mount();
    await userEvent.click(screen.getByRole("option", { name: /Silk yarn study/ }));
    expect(screen.getByTestId("location")).toHaveTextContent("/tasks/task-one");
    expect(listener).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("option", { name: "Ask agent" }));
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener("studio-agent-open", listener);
  });
  it("constructs exact notebook and memory destinations without content in URLs", () => {
    expect(resourceDestination({ kind: "page", id: "page-one", notebookId: "notebook-one", title: "Private formula" })).toBe("/notebooks?notebook=notebook-one&page=page-one");
    expect(resourceDestination({ kind: "memory", id: "memory-one", title: "Private finding" })).toBe("/memory?memory=memory-one");
  });
  it("keeps known actions immediately usable while saved work is still loading", async () => {
    state.pending = true;
    try {
      mount();
      expect(screen.getByRole("option", { name: "New notebook" })).toBeVisible();
      expect(screen.getByRole("status")).toHaveTextContent("Loading your recent work");
      await userEvent.click(screen.getByRole("option", { name: "New notebook" }));
      expect(screen.getByTestId("location")).toHaveTextContent("/notebooks?new=notebook");
    } finally { state.pending = false; }
  });
});
