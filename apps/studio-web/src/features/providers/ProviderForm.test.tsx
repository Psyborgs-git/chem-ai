import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";

const state = vi.hoisted(() => ({ commit: vi.fn() }));
vi.mock("react-relay", () => ({ graphql: () => ({}), useMutation: () => [state.commit, false] }));
import { ProviderForm, type InferenceProvider } from "./ProviderForm";

const provider: InferenceProvider = { id: "provider-1", revision: 3, name: "Research model", kind: "openai", baseUrl: "https://api.openai.com/v1", model: "configured-model", apiStyle: "chat_completions", enabled: true, supportsTools: true, hasApiKey: true, lastTestStatus: "untested", lastTestAt: null, createdAt: "2026-11-01T00:00:00Z", updatedAt: "2026-11-01T00:00:00Z" };
const mount = (existing: InferenceProvider | undefined = provider, onSaved = vi.fn()) => render(<ProviderForm provider={existing} onSaved={onSaved} onCancel={vi.fn()} />);
const save = () => fireEvent.click(screen.getByRole("button", { name: "Save provider" }));

describe("provider credentials and intentional saves", () => {
  beforeEach(() => state.commit.mockReset());

  it("shows key presence without ever repopulating an existing key, and blank edit retains it", () => {
    mount();
    expect(screen.getByLabelText("Replacement API key")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("Replacement API key")).toHaveValue("");
    expect(screen.getByLabelText("Replacement API key")).toHaveAttribute("autocomplete", "new-password");
    save();
    const input = state.commit.mock.calls[0][0].variables.input;
    expect(input).toMatchObject({ id: "provider-1", expectedRevision: 3, clearApiKey: false });
    expect(input).not.toHaveProperty("apiKey");
    save();
    expect(state.commit).toHaveBeenCalledTimes(1);
  });

  it("preserves an existing Responses protocol and lets the owner change it without replacing the key", async () => {
    mount({ ...provider, apiStyle: "responses" });
    expect(screen.getByRole("combobox", { name: "Provider API protocol" })).toHaveTextContent("Responses API");
    await userEvent.click(screen.getByRole("combobox", { name: "Provider API protocol" }));
    await userEvent.click(await screen.findByRole("option", { name: "Chat Completions" }));
    save();
    expect(state.commit.mock.calls[0][0].variables.input).toMatchObject({ apiStyle: "chat_completions", baseUrl: provider.baseUrl, clearApiKey: false });
    expect(state.commit.mock.calls[0][0].variables.input).not.toHaveProperty("apiKey");
  });

  it("defaults a new OpenAI connection to Responses without sending a request until saved", () => {
    render(<ProviderForm onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole("combobox", { name: "Provider API protocol" })).toHaveTextContent("Responses API");
    expect(state.commit).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Provider name"), { target: { value: "OpenAI research" } });
    fireEvent.change(screen.getByLabelText("Model ID"), { target: { value: "configured-model" } });
    save();
    expect(state.commit.mock.calls[0][0].variables.input).toMatchObject({ kind: "openai", apiStyle: "responses" });
    expect(state.commit.mock.calls[0][0].variables.input).not.toHaveProperty("apiKey");
  });

  it("requires replacing or removing a saved credential when the destination changes", () => {
    mount();
    fireEvent.change(screen.getByLabelText("API endpoint"), { target: { value: "https://api.openai.com/other-prefix" } });
    expect(screen.getByRole("button", { name: "Save provider" })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("destination changed");
    fireEvent.change(screen.getByLabelText("Replacement API key"), { target: { value: "new-secret-for-new-destination" } });
    save();
    expect(state.commit.mock.calls[0][0].variables.input).toMatchObject({ baseUrl: "https://api.openai.com/other-prefix", apiKey: "new-secret-for-new-destination", clearApiKey: false });
  });

  it("removes a key only after the explicit removal checkbox is selected", () => {
    mount();
    fireEvent.click(screen.getByLabelText("Remove saved API key"));
    expect(screen.getByLabelText("Replacement API key")).toHaveValue("");
    expect(screen.getByLabelText("Replacement API key")).toBeDisabled();
    save();
    expect(state.commit.mock.calls[0][0].variables.input).toMatchObject({ clearApiKey: true });
    expect(state.commit.mock.calls[0][0].variables.input).not.toHaveProperty("apiKey");
  });

  it("can save a local compatible endpoint with no real key and without enabling it", async () => {
    render(<ProviderForm onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Provider name"), { target: { value: "Local test model" } });
    await userEvent.click(screen.getByRole("combobox", { name: "Provider type" }));
    await userEvent.click(await screen.findByRole("option", { name: "OpenAI-compatible endpoint" }));
    fireEvent.change(screen.getByLabelText("API endpoint"), { target: { value: "http://127.0.0.1:9999/v1" } });
    fireEvent.change(screen.getByLabelText("Model ID"), { target: { value: "local-test-model" } });
    save();
    expect(state.commit.mock.calls[0][0].variables.input).toMatchObject({ kind: "openai_compatible", baseUrl: "http://127.0.0.1:9999/v1", enabled: false, apiStyle: "chat_completions" });
    expect(state.commit.mock.calls[0][0].variables.input).not.toHaveProperty("apiKey");
  });

  it("reuses the request identity after an uncertain network failure and resets it after an edit", async () => {
    mount(); save();
    const first = state.commit.mock.calls[0][0];
    await act(async () => first.onError(new Error("upstream echoed confidential-secret")));
    expect(screen.queryByText(/confidential-secret/)).not.toBeInTheDocument();
    save();
    const second = state.commit.mock.calls[1][0];
    expect(second.variables.input.clientMutationId).toBe(first.variables.input.clientMutationId);
    await act(async () => second.onError(new Error("offline")));
    fireEvent.change(screen.getByLabelText("Model ID"), { target: { value: "another-model" } });
    save();
    expect(state.commit.mock.calls[2][0].variables.input.clientMutationId).not.toBe(first.variables.input.clientMutationId);
  });

  it("clears entered keys only after an acknowledged successful save", async () => {
    const saved = vi.fn(); mount(provider, saved);
    fireEvent.change(screen.getByLabelText("Replacement API key"), { target: { value: "ephemeral-new-key" } });
    save();
    expect(saved).not.toHaveBeenCalled();
    await act(async () => state.commit.mock.calls[0][0].onCompleted({ providers: { save: { provider, errors: [] } } }));
    expect(saved).toHaveBeenCalledOnce();
    expect(screen.getByLabelText("Replacement API key")).toHaveValue("");
  });

  it("rejects remote plain HTTP and credentials in URLs before submission", () => {
    mount();
    fireEvent.change(screen.getByLabelText("API endpoint"), { target: { value: "http://remote.example/v1" } });
    expect(screen.getByRole("button", { name: "Save provider" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("API endpoint"), { target: { value: "https://key:secret@remote.example/v1?api_key=secret" } });
    expect(screen.getByRole("button", { name: "Save provider" })).toBeDisabled();
    expect(state.commit).not.toHaveBeenCalled();
  });
});
