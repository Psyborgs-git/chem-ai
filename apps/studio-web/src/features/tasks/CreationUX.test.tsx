import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ commit: vi.fn() }));
vi.mock("react-relay", () => ({ graphql: () => ({}), useMutation: () => [state.commit, false] }));
vi.mock("../registry/pickers", () => ({ FormulationRevisionPicker: () => <div>Baseline picker</div>, ReferenceProductPicker: () => <div>Reference picker</div> }));
import { ProjectCreateForm } from "./ProjectCreateForm";
import { TaskCreateForm } from "./TaskCreateForm";

describe("creation starts with user intent", () => {
  beforeEach(() => { state.commit.mockReset(); });

  it("creates a project from its name without requiring a technical identifier", () => {
    render(<MemoryRouter><ProjectCreateForm /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Create project" })).toBeDisabled();
    const name = screen.getByLabelText("project name");
    expect(name).toBeRequired();
    expect(screen.getByLabelText("project slug")).not.toBeRequired();
    expect(screen.getByLabelText("project slug")).not.toBeVisible();
    fireEvent.change(name, { target: { value: "Café research" } });
    fireEvent.submit(screen.getByRole("form", { name: "create project" }));
    expect(state.commit.mock.calls[0][0].variables.input).toEqual({ name: "Café research", slug: expect.stringMatching(/^cafe-research-[a-f0-9]{6}$/), description: undefined });
  });

  it("keeps the generated project identifier stable across a failed save and permits an explicit override", () => {
    state.commit.mockImplementation(({ onError }) => onError(new Error("offline")));
    render(<MemoryRouter><ProjectCreateForm /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("project name"), { target: { value: "My research" } });
    const form = screen.getByRole("form", { name: "create project" });
    fireEvent.submit(form); fireEvent.submit(form);
    expect(state.commit.mock.calls[0][0].variables.input.slug).toBe(state.commit.mock.calls[1][0].variables.input.slug);
    fireEvent.click(screen.getByText("Details"));
    fireEvent.change(screen.getByLabelText("project slug"), { target: { value: "chosen-identifier" } });
    fireEvent.submit(form);
    expect(state.commit.mock.calls[2][0].variables.input.slug).toBe("chosen-identifier");
  });

  it("creates an explicitly displayed molecule exploration draft from the title, without requiring a project", () => {
    render(<MemoryRouter><TaskCreateForm /></MemoryRouter>);
    expect(screen.getByRole("radio", { name: "Explore" })).toBeChecked();
    expect(screen.getByLabelText("What are you exploring?")).toHaveValue("molecule");
    expect(screen.queryByText("Baseline picker")).not.toBeInTheDocument();
    expect(screen.queryByText("Reference picker")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("task title"), { target: { value: "Inspect ethanol" } });
    fireEvent.submit(screen.getByRole("form", { name: "create task" }));
    expect(state.commit.mock.calls[0][0].variables.input).toEqual({ projectId: undefined, title: "Inspect ethanol", mode: "discover", objective: "Inspect ethanol", targetKind: "molecule", modeInputs: {} });
    expect(state.commit).toHaveBeenCalledTimes(1);
  });

  it("only asks for a baseline or reference when that intent is selected and preserves a more detailed user goal", () => {
    render(<MemoryRouter><TaskCreateForm projectId="project-1" /></MemoryRouter>);
    fireEvent.click(screen.getByRole("radio", { name: "Improve" }));
    expect(screen.getByText("Baseline picker")).toBeVisible();
    expect(screen.queryByText("Reference picker")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Match" }));
    expect(screen.getByText("Reference picker")).toBeVisible();
    expect(screen.queryByText("Baseline picker")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("task title"), { target: { value: "Compare a reference" } });
    fireEvent.click(screen.getByText("Details"));
    fireEvent.change(screen.getByLabelText("Research goal (optional)"), { target: { value: "Only compare performance under the stated conditions" } });
    fireEvent.submit(screen.getByRole("form", { name: "create task" }));
    expect(state.commit.mock.calls[0][0].variables.input.objective).toBe("Only compare performance under the stated conditions");
    expect(state.commit.mock.calls[0][0].variables.input.mode).toBe("match_reference");
    expect(state.commit.mock.calls[0][0].variables.input.modeInputs).toEqual({ matchScope: "functional" });
  });
});
