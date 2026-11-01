import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

type MutationOptions = {
  variables: { input: { taskId: string; smiles: string; idempotencyKey: string } };
  onCompleted: (value: unknown) => void;
  onError: (error: Error) => void;
};

const { commit } = vi.hoisted(() => ({ commit: vi.fn<(options: MutationOptions) => void>() }));
vi.mock("react-relay", () => ({ graphql: () => ({}), useMutation: () => [commit, false] }));
vi.mock("./RunsPanel", () => ({ RunsPanel: () => null }));

import { CalculationForm } from "./CalculationPanel";
import { RunResult } from "./RunResult";
import { RunCancelControl, canRequestCancellation } from "./RunCancelControl";

const capability = { status: "available", detail: "RDKit 2026.03.6 on this machine" };
const result = {
  id: "run-ethanol",
  kind: "rdkit_descriptors",
  status: "succeeded",
  inputSummary: { smiles: "CCO", inputDigest: "sha256:test" },
  resultSummary: {
    structure: { canonical_smiles: "CCO", formula: "C2H6O", inchi_key: "LFQSCWFLJHTTHZ-UHFFFAOYSA-N" },
    descriptors: { mw: 46.069, hbd: 1, hba: 1, num_rings: 0 },
    engine: { id: "rdkit", version: "2026.03.6" },
    adapter_version: "rdkit-adapter/v1",
    method: "rdkit-descriptors/v1",
    evidence_type: "descriptor",
  },
};

function renderForm(props: { capability?: typeof capability; readOnlyReason?: string } = {}) {
  return render(<MemoryRouter><CalculationForm taskId="task-1" capability={props.capability ?? capability} readOnlyReason={props.readOnlyReason} /></MemoryRouter>);
}

describe("local calculation submission", () => {
  beforeEach(() => commit.mockReset());

  it("starts blank and guards repeated submission while the real request is pending", () => {
    renderForm();
    expect(screen.getByLabelText("SMILES structure")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Calculate properties" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("SMILES structure"), { target: { value: " CCO " } });
    const form = screen.getByRole("form", { name: "Molecular calculation" });
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(commit).toHaveBeenCalledTimes(1);
    expect(commit.mock.calls[0][0].variables.input).toMatchObject({ taskId: "task-1", smiles: "CCO" });
    expect(screen.getByRole("button", { name: "Calculating locally…" })).toBeDisabled();
  });

  it("retries an uncertain transport response with the original idempotency key", () => {
    renderForm();
    fireEvent.change(screen.getByLabelText("SMILES structure"), { target: { value: "CCO" } });
    const form = screen.getByRole("form", { name: "Molecular calculation" });
    fireEvent.submit(form);
    const first = commit.mock.calls[0][0];
    act(() => first.onError(new Error("connection lost")));
    expect(screen.getByRole("alert")).toHaveTextContent("Retry checks the same request");
    fireEvent.submit(form);
    expect(commit.mock.calls[1][0].variables.input.idempotencyKey).toBe(first.variables.input.idempotencyKey);
  });

  it("changes the request identity when the input changes after an uncertain response", () => {
    renderForm();
    const input = screen.getByLabelText("SMILES structure");
    fireEvent.change(input, { target: { value: "CCO" } });
    const form = screen.getByRole("form", { name: "Molecular calculation" });
    fireEvent.submit(form);
    const first = commit.mock.calls[0][0];
    act(() => first.onError(new Error("connection lost")));
    fireEvent.change(input, { target: { value: "O" } });
    fireEvent.submit(form);
    expect(commit.mock.calls[1][0].variables.input.idempotencyKey).not.toBe(first.variables.input.idempotencyKey);
  });

  it("shows the saved result only after the server confirms it", () => {
    renderForm();
    fireEvent.click(screen.getByRole("button", { name: "Use ethanol example" }));
    expect(screen.queryByText("C2H6O")).not.toBeInTheDocument();
    fireEvent.submit(screen.getByRole("form", { name: "Molecular calculation" }));
    act(() => commit.mock.calls[0][0].onCompleted({ runs: { describeStructure: { run: result, errors: [] } } }));
    expect(screen.getByText("C2H6O")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open saved result" })).toHaveAttribute("href", "/runs/run-ethanol");
  });

  it("preserves typed engine rejection and never renders a successful descriptor result", () => {
    renderForm();
    fireEvent.change(screen.getByLabelText("SMILES structure"), { target: { value: "invalid" } });
    fireEvent.submit(screen.getByRole("form", { name: "Molecular calculation" }));
    act(() => commit.mock.calls[0][0].onCompleted({ runs: { describeStructure: { run: { id: "run-bad", kind: "rdkit_descriptors", status: "failed", error: { code: "PARSE_FAILED", message: "Cannot parse the structure" } }, errors: [] } } }));
    expect(screen.getByRole("alert")).toHaveTextContent("PARSE_FAILED");
    expect(screen.queryByText("Molecular weight")).not.toBeInTheDocument();
    expect(screen.queryByText("computed", { exact: true })).not.toBeInTheDocument();
  });

  it("shows an unavailable engine and prevents the request", () => {
    renderForm({ capability: { status: "unavailable", detail: "RDKit is not installed" } });
    fireEvent.click(screen.getByRole("button", { name: "Use ethanol example" }));
    fireEvent.submit(screen.getByRole("form", { name: "Molecular calculation" }));
    expect(commit).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Calculate properties" })).toBeDisabled();
    expect(screen.getByRole("note")).toHaveTextContent("RDKit is not installed");
  });
});

describe("persisted calculation result", () => {
  it("shows the actual identity, all descriptor values including zero, and engine provenance", () => {
    render(<RunResult run={result} />);
    expect(screen.getByText("LFQSCWFLJHTTHZ-UHFFFAOYSA-N")).toBeInTheDocument();
    expect(screen.getByText("rdkit 2026.03.6")).toBeInTheDocument();
    expect(screen.getByRole("row", { name: "Rings 0 Dimensionless" })).toBeInTheDocument();
    expect(screen.getByText(/not laboratory measurements/)).toBeInTheDocument();
    expect(screen.getByLabelText("Calculation input")).toHaveTextContent("CCO");
  });

  it("does not show descriptor output from failed runs even when partial JSON is present", () => {
    render(<RunResult run={{ ...result, status: "failed" }} />);
    expect(screen.queryByLabelText("Computed descriptors")).not.toBeInTheDocument();
    expect(screen.getByText("No completed calculation result is available.")).toBeInTheDocument();
  });

  it("makes blocked admission reasons and unobserved capacity visible without opening raw JSON", () => {
    render(<RunResult run={{ id: "blocked-run", kind: "rdkit_descriptors", status: "blocked", error: { code: "blocked", message: "insufficient_local_resources", detail: { reasons: [{ dimension: "memory_bytes", required: 2147483648, available: 1073741824 }], missing: ["gpu_devices"] } } }} />);
    const requirements = screen.getByRole("region", { name: "Local resource requirements" });
    expect(requirements).toHaveTextContent("Memory · requires 2 GiB · 1 GiB available");
    expect(requirements).toHaveTextContent("Not observed on this device: GPU devices");
  });
});

describe("authoritative cancellation controls", () => {
  beforeEach(() => commit.mockReset());

  it("offers cancellation only in states accepted by the service", () => {
    for (const status of ["requested", "awaiting_approval", "queued", "running"]) expect(canRequestCancellation(status)).toBe(true);
    for (const status of ["blocked", "cancel_requested", "succeeded", "failed", "cancelled", "interrupted"]) expect(canRequestCancellation(status)).toBe(false);
    render(<RunCancelControl run={{ id: "blocked", kind: "rdkit_descriptors", status: "blocked" }} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("requests cancellation once and refreshes only after the server acknowledges it", () => {
    const onChanged = vi.fn();
    render(<RunCancelControl run={{ id: "active-run", kind: "rdkit_descriptors", status: "running" }} onChanged={onChanged} />);
    const cancel = screen.getByRole("button", { name: "cancel rdkit_descriptors run" });
    fireEvent.click(cancel);
    fireEvent.click(cancel);
    expect(commit).toHaveBeenCalledTimes(1);
    expect(onChanged).not.toHaveBeenCalled();
    act(() => commit.mock.calls[0][0].onCompleted({ runs: { requestCancel: { run: { id: "active-run", status: "cancel_requested" }, errors: [] } } }));
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("keeps cancel_requested distinct from a completed cancellation", () => {
    render(<RunCancelControl run={{ id: "pending-run", kind: "rdkit_descriptors", status: "cancel_requested" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("Waiting for the worker to confirm");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
