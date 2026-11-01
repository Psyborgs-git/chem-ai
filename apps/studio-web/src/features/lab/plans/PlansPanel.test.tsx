import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ commit: vi.fn(), hasCandidate: true, hasContract: true }));
vi.mock("react-relay", () => ({
  graphql: () => ({}), useMutation: () => [state.commit, false],
  useLazyLoadQuery: () => ({
    taskCandidateRevisions: { edges: state.hasCandidate ? [{ node: { id: btoa("CandidateRevision:candidate-1"), revision: 1, entityKind: "formulation", status: "accepted_for_research", hypothesis: "Lower-solvent candidate" } }] : [] },
    taskContractRevisions: { edges: state.hasContract ? [{ node: { id: btoa("ContractRevision:contract-1"), revision: 1, status: "frozen" } }] : [] },
  }),
}));

import { PlanCreateForm } from "./PlansPanel";

function mount() {
  return render(<MemoryRouter><PlanCreateForm taskId="task-1" onCreated={vi.fn()} /></MemoryRouter>);
}

describe("context-first experiment planning", () => {
  beforeEach(() => { state.commit.mockReset(); state.hasCandidate = true; state.hasContract = true; });

  it("carries sole authoritative choices by name and only requires the test method", async () => {
    mount();
    await waitFor(() => expect(screen.getByRole("button", { name: "Change candidate" })).toBeVisible());
    expect(document.querySelector(".cs-lab-binding__summary")).toHaveTextContent("Lower-solvent candidate");
    expect(document.querySelector(".cs-lab-plan-options")).not.toHaveAttribute("open");
    const save = screen.getByRole("button", { name: "Save draft plan" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Test method"), { target: { value: "Bench verification" } });
    fireEvent.click(save);
    expect(state.commit.mock.calls[0][0].variables.input).toMatchObject({ taskId: "task-1", title: "Bench verification experiment", payload: { candidateRevisionId: "candidate-1", contractRevisionId: "contract-1", method: "Bench verification" } });
    expect(state.commit.mock.calls[0][0].variables.input.payload).not.toHaveProperty("approvalId");
  });

  it("respects an explicit candidate clear instead of silently reselecting it", async () => {
    mount();
    await waitFor(() => expect(screen.getByRole("button", { name: "Change candidate" })).toBeVisible());
    fireEvent.change(screen.getByLabelText("Test method"), { target: { value: "Bench verification" } });
    fireEvent.click(screen.getByRole("button", { name: "Change candidate" }));
    expect(screen.getByRole("button", { name: "Save draft plan" })).toBeEnabled();
    expect(screen.getByRole("button", { name: /formulation candidate rev 1/ })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /formulation candidate rev 1/ }));
    expect(screen.getByRole("button", { name: "Save draft plan" })).toBeEnabled();
  });

  it("saves a candidate-bound draft without inventing missing success criteria", async () => {
    state.hasContract = false;
    mount();
    await waitFor(() => expect(screen.getByRole("button", { name: "Change candidate" })).toBeVisible());
    expect(screen.getByText(/No success criteria selected\. You can save a draft now/)).toBeVisible();
    fireEvent.change(screen.getByLabelText("Test method"), { target: { value: "Manual triplicate drawdown" } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft plan" }));
    const input = state.commit.mock.calls[0][0].variables.input;
    expect(input.payload).toMatchObject({ candidateRevisionId: "candidate-1", method: "Manual triplicate drawdown" });
    expect(input.payload).not.toHaveProperty("contractRevisionId");
    expect(input.payload).not.toHaveProperty("approvalId");
  });

  it("allows an unbound draft while keeping both missing bindings explicit", () => {
    state.hasCandidate = false;
    state.hasContract = false;
    mount();
    expect(screen.getByText(/No candidate or success criteria selected/)).toBeVisible();
    const save = screen.getByRole("button", { name: "Save draft plan" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Test method"), { target: { value: "Initial test outline" } });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    const payload = state.commit.mock.calls[0][0].variables.input.payload;
    expect(payload.method).toBe("Initial test outline");
    expect(payload).not.toHaveProperty("candidateRevisionId");
    expect(payload).not.toHaveProperty("contractRevisionId");
  });

  it("caps an automatic plan name at 300 characters without truncating the actual method", async () => {
    mount();
    await waitFor(() => expect(screen.getByRole("button", { name: "Change candidate" })).toBeVisible());
    const method = "Long method description. ".repeat(30);
    fireEvent.change(screen.getByLabelText("Test method"), { target: { value: method } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft plan" }));
    const input = state.commit.mock.calls[0][0].variables.input;
    expect(Array.from(input.title)).toHaveLength(300);
    expect(input.title).toMatch(/ experiment$/);
    expect(input.payload.method).toBe(method);
  });

  it("keeps displayed bindings correct for a second plan after saving the first", async () => {
    state.commit.mockImplementation(({ onCompleted }) => onCompleted({ lab: { planCreate: { errors: [] } } }));
    mount();
    await waitFor(() => expect(screen.getByRole("button", { name: "Change success criteria" })).toBeVisible());
    fireEvent.change(screen.getByLabelText("Test method"), { target: { value: "First test" } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft plan" }));
    fireEvent.change(screen.getByLabelText("Test method"), { target: { value: "Second test" } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft plan" }));
    expect(state.commit.mock.calls[1][0].variables.input.payload).toMatchObject({ candidateRevisionId: "candidate-1", contractRevisionId: "contract-1", method: "Second test" });
  });
});
