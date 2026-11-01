import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
vi.mock("./ContractEditor", () => ({ ContractEditor: () => <div>Criteria editor</div> }));
import { TaskOverview } from "./TaskOverview";

describe("intentional criteria authoring", () => {
  it("starts with a clear research checkpoint and opens authoring in one activation", () => {
    render(<MemoryRouter><TaskOverview taskId="task-1" workflowState="draft" contract={null} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "What would count as success?" })).toBeVisible();
    expect(screen.queryByText("Criteria editor")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Define success criteria" }));
    expect(screen.getByText("Criteria editor")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Back to overview" }));
    expect(screen.queryByText("Criteria editor")).not.toBeInTheDocument();
  });

  it("opens the editor directly for the header's criteria link", () => {
    render(<MemoryRouter initialEntries={["/tasks/task-1/overview?edit=criteria"]}><TaskOverview taskId="task-1" workflowState="draft" contract={null} /></MemoryRouter>);
    expect(screen.getByText("Criteria editor")).toBeVisible();
  });

  it("previews the actual stored criteria and conditions, retaining an intentional zero", () => {
    render(<MemoryRouter><TaskOverview taskId="task-1" workflowState="active" contract={{ revision: 2, status: "frozen", payload: { metrics: [{ id: "metric.index", label: "Synthetic index", operator: "gte", target_values: ["0"], unit: "dimensionless", conditions: "Recorded conditions" }], hard_constraints: [{ text: "A hard constraint" }] } }} /></MemoryRouter>);
    expect(screen.getByText("Synthetic index")).toBeVisible();
    expect(screen.getByText("≥ 0 dimensionless")).toBeVisible();
    expect(screen.getByText("Recorded conditions")).toBeVisible();
    expect(screen.queryByText("Criteria editor")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit criteria" }));
    expect(screen.getByText("Criteria editor")).toBeVisible();
  });
});
