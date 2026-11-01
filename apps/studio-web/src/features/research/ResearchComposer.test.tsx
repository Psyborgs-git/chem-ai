import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ commit: vi.fn() }));
vi.mock("react-relay", () => ({ graphql: () => ({}), useMutation: () => [state.commit, false] }));
import { ResearchComposer, type ResearchProvider } from "./ResearchComposer";
const remote: ResearchProvider = { id: "provider-1", revision: 3, name: "Saved remote", model: "configured-model", baseUrl: "https://models.example/v1", enabled: true };
function harness(providers: readonly ResearchProvider[] = [remote]) { return <MemoryRouter><ResearchComposer sessionId="session-1" providers={providers} /></MemoryRouter>; }
function question(value = "What evidence is still missing?") { fireEvent.change(screen.getByLabelText("ask the research agent"), { target: { value } }); }
function choose() { fireEvent.change(screen.getByLabelText("Research model"), { target: { value: "provider-1" } }); }
function consent() { fireEvent.click(screen.getByLabelText("Allow this provider to receive data for this turn")); }
function send() { fireEvent.click(screen.getByRole("button", { name: "send" })); }

describe("explicit provider selection and research request identity", () => {
  beforeEach(() => state.commit.mockReset());

  it("never selects a saved provider automatically, even when only one is available", () => {
    render(harness()); question();
    expect(screen.getByLabelText("Research model")).toHaveValue(""); send();
    expect(state.commit.mock.calls[0][0].variables.input).not.toHaveProperty("providerId");
    expect(state.commit.mock.calls[0][0].variables.input).not.toHaveProperty("allowProviderDataTransfer");
  });

  it("shows the destination and exact data disclosure and requires per-turn permission", () => {
    render(harness()); question(); choose();
    expect(screen.getByText("https://models.example/v1")).toBeVisible();
    expect(screen.getByText(/task ID, title, mode/)).toBeVisible();
    expect(screen.getByText(/usage may incur charges/)).toBeVisible();
    expect(screen.getByRole("button", { name: "send" })).toBeDisabled();
    consent(); send();
    expect(state.commit.mock.calls[0][0].variables.input).toMatchObject({ providerId: "provider-1", allowProviderDataTransfer: true, content: "What evidence is still missing?" });
    send(); expect(state.commit).toHaveBeenCalledTimes(1);
  });

  it("resets consent after a confirmed turn while keeping the provider choice explicit", async () => {
    render(harness()); question(); choose(); consent(); send();
    await act(async () => state.commit.mock.calls[0][0].onCompleted({ research: { turnRequest: { errors: [], finishedReason: "final" } } }));
    expect(screen.getByLabelText("Research model")).toHaveValue("provider-1");
    expect(screen.getByLabelText("Allow this provider to receive data for this turn")).not.toBeChecked();
    expect(screen.getByLabelText("ask the research agent")).toHaveValue("");
    question("Next question");
    expect(screen.getByRole("button", { name: "send" })).toBeDisabled();
  });

  it("retries an unconfirmed unchanged request with the same turn ID, then resets after editing", async () => {
    render(harness()); question(); choose(); consent(); send();
    const first = state.commit.mock.calls[0][0];
    await act(async () => first.onError(new Error("upstream echoed hidden-api-key")));
    expect(screen.queryByText(/hidden-api-key/)).not.toBeInTheDocument();
    send(); const second = state.commit.mock.calls[1][0];
    expect(second.variables.input).toEqual(first.variables.input);
    await act(async () => second.onError(new Error("offline")));
    question("A revised question"); send();
    expect(state.commit.mock.calls[2][0].variables.input.turnId).not.toBe(first.variables.input.turnId);
  });

  it("does not silently fall back when a selected provider becomes unavailable", () => {
    const view = render(harness()); question(); choose(); consent();
    view.rerender(harness([{ ...remote, enabled: false }]));
    expect(screen.getByRole("alert")).toHaveTextContent("no longer available");
    expect(screen.getByRole("button", { name: "send" })).toBeDisabled();
    send(); expect(state.commit).not.toHaveBeenCalled();
  });

  it("retains the question after a recorded unavailable turn but starts a new request after its confirmation", async () => {
    render(harness()); question(); choose(); consent(); send();
    const first = state.commit.mock.calls[0][0];
    await act(async () => first.onCompleted({ research: { turnRequest: { errors: [], finishedReason: "model_unavailable" } } }));
    expect(screen.getByLabelText("ask the research agent")).toHaveValue("What evidence is still missing?");
    expect(screen.getByText(/that creates a new turn/)).toBeVisible();
    expect(screen.getByLabelText("Allow this provider to receive data for this turn")).not.toBeChecked();
    consent(); send();
    expect(state.commit.mock.calls[1][0].variables.input.turnId).not.toBe(first.variables.input.turnId);
  });

  it("binds consent to the displayed provider revision and requires renewed permission after it changes", () => {
    const view = render(harness()); question(); choose(); consent();
    view.rerender(harness([{ ...remote, revision: 4, model: "changed-model", baseUrl: "https://changed.example/v1" }]));
    expect(screen.getByLabelText("Allow this provider to receive data for this turn")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "send" })).toBeDisabled();
    expect(screen.getByText("https://changed.example/v1")).toBeVisible();
    consent(); send();
    expect(state.commit.mock.calls[0][0].variables.input).toMatchObject({ providerId: "provider-1", providerRevision: 4 });
  });

  it("requests refreshed settings and clears consent when the server rejects a stale provider revision", async () => {
    const refresh = vi.fn();
    render(<MemoryRouter><ResearchComposer sessionId="session-1" providers={[remote]} onProvidersChanged={refresh} /></MemoryRouter>);
    question(); choose(); consent(); send();
    expect(state.commit.mock.calls[0][0].variables.input.providerRevision).toBe(3);
    await act(async () => state.commit.mock.calls[0][0].onCompleted({ research: { turnRequest: { errors: [{ code: "CONFLICT", fieldPath: "providerRevision" }], finishedReason: "error" } } }));
    expect(refresh).toHaveBeenCalledOnce();
    expect(screen.getByRole("alert")).toHaveTextContent("Review the refreshed endpoint and model");
    expect(screen.getByLabelText("Allow this provider to receive data for this turn")).not.toBeChecked();
  });
});
