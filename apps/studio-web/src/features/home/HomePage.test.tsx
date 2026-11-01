import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
const state = vi.hoisted(() => ({ calculate: vi.fn() }));
vi.mock("react-relay", () => ({ graphql: () => ({}), useLazyLoadQuery: () => ({ projects: { edges: [{ node: { id: "project-one", name: "Textile research" } }] }, recent: { edges: [{ node: { id: "task-one", title: "Silk comparison", mode: "discover", workflowState: "draft", project: { name: "Textile research" } } }] }, pendingDecisions: { edges: [] } }) }));
vi.mock("../tasks/ResearchSheet", () => ({ ResearchSheet: () => null }));
vi.mock("./QuickCalculation", () => ({ QuickCalculation: () => <form><label>Molecular structure<input id="quick-structure" /></label><button type="button" onClick={state.calculate}>Calculate properties</button></form> }));
import { HomePage } from "./HomePage";
function mount(entry = "/") { return render(<MemoryRouter initialEntries={[entry]}><HomePage /></MemoryRouter>); }

describe("home research entry", () => {
  it("offers direct real destinations without starting research or inference", async () => {
    state.calculate.mockClear();
    const listener = vi.fn(); window.addEventListener("studio-agent-open", listener);
    mount();
    expect(screen.getByRole("heading", { name: "Your research" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Find papers" })).toHaveAttribute("href", "/library/research?focus=search");
    expect(screen.getByRole("link", { name: "New notebook" })).toHaveAttribute("href", "/notebooks?new=notebook");
    expect(screen.getByRole("link", { name: "Train model" })).toHaveAttribute("href", "/learning?tab=new");
    expect(screen.queryByLabelText("Molecular structure")).toBeNull();
    expect(state.calculate).not.toHaveBeenCalled();
    expect(listener).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Ask agent" }));
    expect(listener).toHaveBeenCalledTimes(1);
    expect(state.calculate).not.toHaveBeenCalled();
    window.removeEventListener("studio-agent-open", listener);
  });
  it("opens and focuses the molecule form while waiting for an explicit calculation", async () => {
    state.calculate.mockClear(); mount();
    await userEvent.click(screen.getByRole("button", { name: "Explore molecule" }));
    await waitFor(() => expect(screen.getByLabelText("Molecular structure")).toHaveFocus());
    expect(state.calculate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Calculate properties" }));
    expect(state.calculate).toHaveBeenCalledTimes(1);
  });
  it("opens an exact recent task and supports the finder's molecule shortcut", async () => {
    mount("/?focus=molecule");
    expect(screen.getByRole("link", { name: /Silk comparison/ })).toHaveAttribute("href", "/tasks/task-one/overview");
    await waitFor(() => expect(screen.getByLabelText("Molecular structure")).toHaveFocus());
  });
});
