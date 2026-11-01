import userEvent from "@testing-library/user-event";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LocalLearningPage, metricEntries, modelsForTask } from "./LocalLearningPage";
const state = vi.hoisted(() => ({ post: vi.fn(), request: vi.fn(), refresh: vi.fn(), modelsRefresh: vi.fn(), modelRows: null as object[] | null, jobs: [] as object[] }));
vi.mock("../../relay/network", () => ({ workspaceRequest: state.request }));
const assistant = { id: "assistant-data", name: "Textile research", state: "frozen", rowCount: 40, dataKind: "literature", rights: "allowed", digest: "data-hash", report: { rowKinds: { assistant: 40 } }, partitions: { train: 32, development: 4, final: 4 } };
const molecular = { ...assistant, id: "molecular-data", name: "Polymer labels", dataKind: "computed", source: { kind: "external_computed", externalComputation: { property: "glass_transition", unit: "K", method: "Retained simulation method" } }, report: { rowKinds: { molecular: 40 } } };
const model = { id: "local-base", name: "Qwen research base", backend: "mlx", location: "/models/base", details: { state: "ready", license: "apache-2.0" } };
vi.mock("../workspace/useWorkspace", () => ({ post: state.post, messageOf: (error: Error) => error.message, useWorkspace: (path: string) => ({ data: path.endsWith("/capabilities") ? { backends: [{ backend: "mlx", available: true, missing: [] }], catalog: [], jobKinds: ["sft", "chemprop", "dpo"] } : path.endsWith("/datasets") ? [assistant, molecular] : path.endsWith("/models") ? state.modelRows ?? [model, { ...model, id: "downloading", details: { state: "downloading" } }, { ...model, id: "property-model", backend: "chemprop" }] : path.endsWith("/jobs") ? state.jobs : [], loading: false, error: null, refresh: path.endsWith("/models") ? state.modelsRefresh : state.refresh }) }));
afterEach(cleanup);
beforeEach(() => { state.jobs = []; state.modelRows = null; state.modelsRefresh.mockReset().mockResolvedValue(undefined); state.post.mockReset(); state.request.mockReset(); state.refresh.mockReset().mockResolvedValue(undefined); });
function mount() { return render(<MemoryRouter><LocalLearningPage /></MemoryRouter>); }
async function choose(label: string, option: string) { if (label === "Training or evaluation track") fireEvent.click(screen.getByText("More training options", { exact: true })); await userEvent.click(screen.getByRole("combobox", { name: label })); await userEvent.click(await screen.findByRole("option", { name: option })); }
function next() { fireEvent.click(screen.getByRole("button", { name: "Continue" })); }
describe("learning workbench", () => {
  it("opens the new-run shortcut without inference and starts a selected task immediately", () => {
    render(<MemoryRouter initialEntries={["/learning?tab=new"]}><LocalLearningPage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Choose a task" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /Train a property model/ }));
    expect(screen.getByRole("heading", { name: "Choose training data" })).toBeVisible();
    expect(state.post).not.toHaveBeenCalled();
  });
  it("shows practical run bounds before specialist settings", async () => {
    mount(); fireEvent.click(screen.getByRole("button", { name: "New run" })); next();
    await choose("Frozen dataset", "Textile research · 40 rows"); next();
    await choose("Base or trained model", "Qwen research base · mlx"); next();
    expect(screen.getByLabelText("Maximum steps")).toBeVisible();
    expect(screen.getByLabelText("Time limit · seconds")).toBeVisible();
    expect(screen.getByLabelText("Adapter rank")).not.toBeVisible();
    fireEvent.click(screen.getByText("Advanced settings", { exact: true }));
    expect(screen.getByLabelText("Adapter rank")).toBeVisible();
  });
  it("shows runs first and keeps result payloads behind details", () => {
    state.jobs = [{ id: "run", name: "Silk research adapter", kind: "sft", state: "completed", events: [{ loss: 2.1 }, { loss: 1.2 }], config: { secretInternalPath: "/output/adapters" }, result: { stepsCompleted: 50, metrics: { train_loss: 1.2 }, artifacts: [{ path: "evaluation.json", bytes: 100 }] } }];
    mount();
    expect(screen.getByRole("tab", { name: "Runs" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("img", { name: /Recorded loss/ })).toBeVisible();
    expect(screen.getByRole("link", { name: /evaluation.json/ })).toHaveAttribute("href", "/api/learning-workspace/jobs/run/artifacts/evaluation.json");
    expect(screen.getByText(/secretInternalPath/)).not.toBeVisible();
  });
  it("requires successful preflight before queueing a compatible configured run", async () => {
    state.post.mockImplementation((path: string) => Promise.resolve(path.endsWith("preflight") ? { ready: true, checks: [{ id: "data", status: "pass", message: "Independent partitions ready" }] } : { id: "job-new" }));
    mount(); fireEvent.click(screen.getByRole("button", { name: "New run" })); next();
    await userEvent.click(screen.getByRole("combobox", { name: "Frozen dataset" }));
    expect(screen.queryByRole("option", { name: /Polymer labels/ })).toBeNull();
    await userEvent.click(await screen.findByRole("option", { name: "Textile research · 40 rows" })); next();
    await userEvent.click(screen.getByRole("combobox", { name: "Base or trained model" }));
    expect(screen.queryByRole("option", { name: /downloading/ })).toBeNull();
    await userEvent.click(await screen.findByRole("option", { name: "Qwen research base · mlx" })); next();
    expect(screen.getByLabelText("Learning rate")).not.toBeVisible();
    fireEvent.click(screen.getByText("Advanced settings", { exact: true }));
    expect(screen.getByLabelText("Learning rate")).toHaveAttribute("max", "0.01");
    fireEvent.change(screen.getByLabelText("Seed"), { target: { value: "42" } });
    fireEvent.change(screen.getByLabelText("Sequence length"), { target: { value: "1024" } }); next();
    expect(screen.getByRole("button", { name: "Queue run" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Check readiness" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Queue run" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Queue run" }));
    await waitFor(() => expect(state.post).toHaveBeenCalledWith("/api/learning-workspace/jobs", expect.objectContaining({ kind: "sft", datasetId: "assistant-data", modelId: "local-base", config: expect.objectContaining({ seed: 42, maxTokens: 1024 }) })));
  });
  it("keeps failed preflight blocked and labels molecular training in epochs", async () => {
    state.post.mockResolvedValue({ ready: false, checks: [{ id: "rights", status: "fail", message: "Resolve training rights" }] });
    mount(); fireEvent.click(screen.getByRole("button", { name: "New run" })); await choose("Training or evaluation track", "SMILES property model"); next();
    await choose("Frozen dataset", "Polymer labels · 40 rows"); next(); next();
    expect(screen.getByLabelText("Maximum epochs")).toBeVisible();
    fireEvent.click(screen.getByText("Advanced settings", { exact: true }));
    expect(screen.queryByLabelText("Checkpoint every · epochs")).toBeNull();
    expect(screen.getByLabelText("Target property")).toHaveValue("glass_transition");
    expect(screen.getByLabelText("Target unit")).toHaveValue("K");
    expect(screen.getByLabelText("Measurement method")).toHaveAttribute("readonly");
    expect(screen.queryByLabelText("Learning rate")).toBeNull();
    expect(screen.getByText("Fixed schedule · 2 warm-up epochs")).toBeVisible(); next();
    fireEvent.click(screen.getByRole("button", { name: "Check readiness" }));
    await screen.findByText("Resolve training rights");
    expect(screen.getByRole("button", { name: "Queue run" })).toBeDisabled();
  });
  it("limits assistant preview controls to ready assistant models", async () => {
    mount(); await userEvent.click(screen.getByRole("tab", { name: "Models" }));
    const propertyRow = screen.getByText("Use in a prediction run").closest("article")!;
    expect(within(propertyRow).queryByRole("button", { name: "Preview" })).toBeNull();
    expect(modelsForTask([model, { ...model, backend: "reinvent" }], "dpo")).toEqual([]);
    expect(metricEntries({ metrics: { train_loss: 1.1 }, private: "not a metric" })).toEqual([["train_loss", 1.1]]);
  });
  it("refreshes models once when training completes so the candidate can be evaluated immediately", async () => {
    const running = { id: "new-training", name: "Research adapter", kind: "sft", state: "running", datasetId: "assistant-data", config: {}, result: {}, events: [] };
    state.jobs = [running];
    state.modelRows = [model];
    const view = mount();
    expect(screen.queryByRole("button", { name: "Evaluate candidate" })).toBeNull();
    state.modelsRefresh.mockImplementation(async () => { state.modelRows = [model, { ...model, id: "trained-candidate", name: "New adapter", details: { state: "ready", trainingJobId: "new-training" } }]; });
    state.jobs = [{ ...running, state: "completed" }];
    view.rerender(<MemoryRouter><LocalLearningPage /></MemoryRouter>);
    await waitFor(() => expect(state.modelsRefresh).toHaveBeenCalledTimes(1));
    view.rerender(<MemoryRouter><LocalLearningPage /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Evaluate candidate" })).toBeVisible();
    state.jobs = [{ ...running, state: "completed" }];
    view.rerender(<MemoryRouter><LocalLearningPage /></MemoryRouter>);
    expect(state.modelsRefresh).toHaveBeenCalledTimes(1);
  });

  it("shows the actual property unit and computed origin beside Chemprop metrics", () => {
    state.jobs = [{ id: "density-run", name: "Density property model", kind: "chemprop", state: "completed", datasetId: "molecular-data", config: { backend: "chemprop", target: "outdated fallback", unit: "1" }, result: { scope: { name: "density", unit: "g/cm3", method: "Retained simulation method" }, evaluation: { mae: 0.0445 } }, events: [] }];
    mount();
    expect(screen.getByLabelText("Property context")).toHaveTextContent("density · g/cm3 · Computed");
    expect(screen.getByLabelText("Property context")).not.toHaveTextContent("outdated fallback");
    expect(screen.getByText("0.0445")).toBeVisible();
  });

  it.each(["top", "result"])("uses authoritative %s elapsed time when events contain only the recent training tail", (source) => {
    state.jobs = [{ id: "long-run", name: "Completed 200-step adapter", kind: "sft", state: "completed", config: { maxSteps: 200 }, ...(source === "top" ? { elapsedSeconds: 370.15 } : {}), result: { elapsedSeconds: source === "result" ? 370.15 : 12 }, events: [{ event: "training_step", iteration: 100, at: 1000 }, { event: "training_step", iteration: 200, at: 1150 }] }];
    mount();
    expect(screen.getByText("6m 10s")).toBeVisible();
    expect(screen.queryByText("2m 30s")).toBeNull();
    expect(screen.getByText("Step 200 / 200")).toBeVisible();
  });

});
