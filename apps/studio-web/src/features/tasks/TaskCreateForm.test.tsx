import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ commit: vi.fn(), pending: false }));
vi.mock("react-relay", () => ({
  graphql: () => ({}),
  useMutation: () => [state.commit, state.pending],
}));
vi.mock("../registry/pickers", () => ({
  FormulationRevisionPicker: () => null,
  ReferenceProductPicker: () => null,
}));
import { TaskCreateForm } from "./TaskCreateForm";

describe("task creation", () => {
  beforeEach(() => { state.commit.mockReset(); state.pending = false; });
  it("submits once when Enter/click submits again before Relay updates", () => {
    render(<MemoryRouter><TaskCreateForm projectId="project-1" /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("task title"), { target: { value: "Ethanol" } });
    const form = screen.getByRole("form", { name: "create task" });
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(state.commit).toHaveBeenCalledTimes(1);
  });
  it("preserves edits and permits retry after a failed request", () => {
    state.commit.mockImplementationOnce(({ onError }) => onError(new Error("offline")));
    render(<MemoryRouter><TaskCreateForm projectId="project-1" /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("task title"), { target: { value: "Retain my work" } });
    fireEvent.submit(screen.getByRole("form", { name: "create task" }));
    expect(screen.getByLabelText("task title")).toHaveValue("Retain my work");
    expect(screen.getByRole("alert")).toHaveTextContent("offline");
    fireEvent.submit(screen.getByRole("form", { name: "create task" }));
    expect(state.commit).toHaveBeenCalledTimes(2);
  });
  it("announces a pending save and disables submission", () => {
    state.pending = true;
    render(<MemoryRouter><TaskCreateForm projectId="project-1" /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Creating task…" })).toBeDisabled();
    expect(screen.getByRole("form")).toHaveAttribute("aria-busy", "true");
  });
});
