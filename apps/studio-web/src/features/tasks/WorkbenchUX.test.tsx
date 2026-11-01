import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ commit: vi.fn(), queryOptions: vi.fn(), emptyCriteria: false }));
vi.mock("react-relay", () => ({ graphql: () => ({}), useMutation: () => [state.commit, false], useLazyLoadQuery: (_query: unknown, _variables: unknown, options?: { fetchKey?: number; fetchPolicy?: string }) => {
  state.queryOptions(options);
  return {
  node: { id: "task-1", title: "Inspect a molecule", objective: "Inspect its structural descriptors", mode: "discover", targetKind: "molecule", workflowState: "draft", evaluationCycle: 1, unresolvedInputs: [], project: { id: "project-1", name: "My project" } },
  taskContractRevisions: { edges: state.emptyCriteria && !options?.fetchKey ? [] : [{ node: { revision: 1, status: "frozen", payload: { metrics: [{ id: "metric.index", label: "Recorded index", target_values: ["0"], operator: "gte", unit: "dimensionless" }] } } }] }, taskCandidateRevisions: { edges: [] }, taskPlans: { edges: [] }, taskQuestions: [], taskReassessmentStatus: {},
}; }, useFragment: () => ({}), usePaginationFragment: () => ({}) }));
vi.mock("./ContractEditor", () => ({ ContractEditor: ({ onSaved }: { onSaved?: () => void }) => <div>Criteria editor<button onClick={onSaved}>Acknowledge saved criteria</button></div> }));
vi.mock("../research/ResearchPanel", () => ({ ResearchPanel: () => <div>Research memory</div> }));
import { TaskWorkspace } from "./TaskWorkspace";

function harness() {
  return <MemoryRouter initialEntries={["/tasks/task-1/overview"]}><Routes><Route path="/tasks/:taskId/:group" element={<TaskWorkspace taskId="task-1" />} /></Routes></MemoryRouter>;
}

describe("task workbench", () => {
  beforeEach(() => { state.commit.mockReset(); state.queryOptions.mockClear(); state.emptyCriteria = false; });

  it("keeps six primary destinations while disclosing every existing advanced tool", () => {
    render(harness());
    const primary = screen.getByRole("navigation", { name: "task sections" });
    expect(within(primary).getAllByRole("link")).toHaveLength(6);
    expect(within(primary).getByRole("link", { name: "Sources" })).toHaveAttribute("href", "/tasks/task-1/evidence?view=claims");
    expect(within(primary).getByRole("link", { name: "Review" })).toHaveAttribute("href", "/tasks/task-1/decisions?view=closeout");
    expect(within(primary).getByRole("link", { name: "Experiments" })).toHaveAttribute("href", "/tasks/task-1/experiments?view=calculations");
    expect(screen.getByRole("link", { name: "Datasets" })).not.toBeVisible();
    fireEvent.click(screen.getByText("Tools"));
    const tools = screen.getByRole("navigation", { name: "task tools" });
    expect(within(tools).getAllByRole("link")).toHaveLength(7);
    expect(within(tools).getByRole("link", { name: "Run history" })).toHaveAttribute("href", "/tasks/task-1/advanced?view=runs");
  });

  it("starts a draft directly from the header in one activation, without requesting an approval or closure", () => {
    render(harness());
    const start = screen.getByRole("button", { name: "Start task" });
    fireEvent.click(start);
    expect(state.commit).toHaveBeenCalledTimes(1);
    expect(state.commit.mock.calls[0][0].variables).toEqual({ input: { taskId: "task-1", toState: "active" } });
    fireEvent.click(start);
    expect(state.commit).toHaveBeenCalledTimes(1);
  });

  it("keeps goal and next step visible while detailed metadata stays collapsed", () => {
    render(harness());
    expect(screen.getByRole("heading", { name: "Inspect a molecule" })).toBeVisible();
    expect(screen.getByText("Inspect its structural descriptors")).toBeVisible();
    expect(screen.getByText("Add a candidate")).toBeVisible();
    expect(screen.getByText("Success criteria:")).not.toBeVisible();
    fireEvent.click(screen.getByText("Task details"));
    expect(screen.getByText("Success criteria:")).toBeVisible();
    expect(screen.getByRole("list", { name: "Research path" }).querySelector('[aria-current="step"]')).toHaveTextContent("Candidates");
  });

  it("refreshes the header and overview after an acknowledged criteria save without a reload", () => {
    state.emptyCriteria = true;
    render(harness());
    expect(screen.getByRole("list", { name: "Research path" })).toHaveTextContent("Define success");
    fireEvent.click(screen.getByRole("button", { name: "Define success criteria" }));
    fireEvent.click(screen.getByRole("button", { name: "Acknowledge saved criteria" }));
    expect(state.queryOptions).toHaveBeenLastCalledWith({ fetchKey: 1, fetchPolicy: "network-only" });
    expect(screen.getByRole("list", { name: "Research path" })).toHaveTextContent("Criteria frozen");
    fireEvent.click(screen.getByRole("button", { name: "Back to overview" }));
    expect(screen.getByText("Recorded index")).toBeVisible();
    expect(screen.getByText("≥ 0 dimensionless")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Define success criteria" })).not.toBeInTheDocument();
  });
});
