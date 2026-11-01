import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ commit: vi.fn(), contextual: false }));
vi.mock("react-relay", () => ({ graphql: () => ({}), useMutation: () => [state.commit, false],
  useLazyLoadQuery: (_query: unknown, _variables: unknown, options: { fetchKey?: number }) => ({
    taskExecutions: [{ id: "execution-1", status: "in_progress", historical: false, planId: state.contextual ? "plan-1" : null, deviations: [], batches: state.contextual ? [{ id: "batch-1", label: "A", payload: null, samples: [{ id: "sample-1", label: "a1", kind: "aliquot", measurements: [] }] }] : [] }],
    taskPlans: { edges: state.contextual ? [{ node: { id: btoa("ExperimentPlan:plan-1"), title: "Known plan", status: "approved", payload: { method: "Frozen-plan method", contractRevisionId: "contract-old" } } }] : [] },
    taskContractRevisions: { edges: state.contextual ? [
      { node: { id: btoa("ContractRevision:contract-new"), revision: 2, status: "frozen", payload: { metrics: [{ id: "metric.mass", label: "New requirement", unit: "mg", operator: "gte", target_values: ["9"] }] } } },
      { node: { id: btoa("ContractRevision:contract-old"), revision: 1, status: "frozen", payload: { metrics: [{ id: "metric.mass", label: "Original mass criterion", unit: "g", operator: "gte", target_values: ["0"] }] } } },
    ] : [] },
    replicationSummary: { independentBatches: options.fetchKey ?? 0, observations: 0, byRepeatType: {} },
  }),
}));
import { MeasurementForm, ResultsPanel } from "./ResultsPanel";

describe("explicit measurement entry", () => {
  beforeEach(() => { state.commit.mockReset(); state.contextual = false; });
  it("requires an actual value and unit, preserving an intentional zero", () => {
    const changed = vi.fn();
    render(<MeasurementForm sampleId="sample-1" onChanged={changed} />);
    fireEvent.click(screen.getByText("record measurement"));
    fireEvent.change(screen.getByLabelText("method"), { target: { value: "Bench method" } });
    const record = screen.getByRole("button", { name: "record" });
    expect(record).toBeDisabled();
    expect(screen.getByLabelText("Measured value")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("Measured value"), { target: { value: "0" } });
    expect(record).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Measurement unit"), { target: { value: "dimensionless" } });
    fireEvent.click(record);
    expect(state.commit.mock.calls[0][0].variables.input.value).toEqual({ kind: "numeric", value: "0", unit: "dimensionless" });
  });
  it("records missingness as a reason instead of a zero measurement", () => {
    render(<MeasurementForm sampleId="sample-1" onChanged={vi.fn()} />);
    fireEvent.click(screen.getByText("record measurement"));
    fireEvent.change(screen.getByLabelText("method"), { target: { value: "Bench method" } });
    fireEvent.click(screen.getByText("Other result types and advanced options"));
    fireEvent.change(screen.getByLabelText("Result type"), { target: { value: "missing" } });
    fireEvent.change(screen.getByLabelText("Missing reason"), { target: { value: "instrument_failure" } });
    fireEvent.click(screen.getByRole("button", { name: "record" }));
    expect(state.commit.mock.calls[0][0].variables.input.value).toEqual({ kind: "missing", reason: "instrument_failure" });
  });
  it("carries the known method and criterion unit while leaving the actual reading blank", () => {
    render(<MeasurementForm sampleId="sample-1" defaultMethod="Approved bench method" metrics={[{ id: "metric.viscosity", label: "Viscosity", unit: "mPa·s" }]} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByText("record measurement"));
    expect(screen.getByRole("combobox", { name: "What did you measure?" })).toHaveValue("metric.viscosity");
    expect(screen.getByLabelText("Measurement unit")).toHaveValue("mPa·s");
    expect(screen.getByLabelText("Measured value")).toHaveValue("");
    expect(screen.getByRole("button", { name: "record" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Measured value"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "record" }));
    expect(state.commit.mock.calls[0][0].variables.input).toMatchObject({ method: "Approved bench method", metric: "metric.viscosity", value: { kind: "numeric", value: "0", unit: "mPa·s" } });
  });
  it("selects a named criterion without typing IDs and preserves an explicitly edited unit", () => {
    render(<MeasurementForm sampleId="sample-1" defaultMethod="Bench method" metrics={[{ id: "metric.a", label: "Criterion A", unit: "g" }, { id: "metric.b", label: "Criterion B", unit: "mg" }]} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByText("record measurement"));
    const selector = screen.getByRole("combobox", { name: "What did you measure?" });
    expect(selector).toHaveValue("");
    fireEvent.change(selector, { target: { value: "metric.a" } });
    expect(screen.getByLabelText("Measurement unit")).toHaveValue("g");
    fireEvent.change(selector, { target: { value: "metric.b" } });
    expect(screen.getByLabelText("Measurement unit")).toHaveValue("mg");
    fireEvent.change(screen.getByLabelText("Measurement unit"), { target: { value: "custom-unit" } });
    fireEvent.change(selector, { target: { value: "metric.a" } });
    expect(screen.getByLabelText("Measurement unit")).toHaveValue("custom-unit");
    fireEvent.change(selector, { target: { value: "" } });
    expect(selector).toHaveValue("");
  });
  it("refreshes replication counts immediately after adding a batch", () => {
    state.commit.mockImplementation(({ onCompleted }) => onCompleted({ lab: { measurements: { batchAdd: { errors: [] } } } }));
    render(<ResultsPanel taskId="task-1" />);
    expect(document.querySelector('[data-field="independent-batches"]')).toHaveTextContent("0");
    fireEvent.change(screen.getByLabelText("new batch label"), { target: { value: "A" } });
    fireEvent.click(screen.getByRole("button", { name: "add batch" }));
    expect(document.querySelector('[data-field="independent-batches"]')).toHaveTextContent("1");
  });
  it("uses the execution plan's bound frozen criteria rather than a newer task revision", () => {
    state.contextual = true;
    render(<ResultsPanel taskId="task-1" />);
    fireEvent.click(screen.getByText("record measurement"));
    expect(screen.getByRole("combobox", { name: "What did you measure?" })).toHaveDisplayValue("Original mass criterion (g)");
    expect(screen.queryByRole("option", { name: "New requirement (mg)" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Measurement unit")).toHaveValue("g");
    expect(screen.getByText("Target:").parentElement).toHaveTextContent("Target: ≥ 0 g");
    expect(screen.getByLabelText("Measured value")).toHaveValue("");
    expect(screen.getByText(/Frozen-plan method/)).toBeVisible();
  });
});
