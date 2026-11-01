import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProviderModelsPanel } from "./ProviderModelsPanel";

const state = vi.hoisted(() => ({
  post: vi.fn(), refresh: vi.fn(),
  providers: [{ id: "provider-1", revision: 1, name: "Local lab", enabled: true, local: true, baseUrl: "http://127.0.0.1:1234/v1", models: [{
    id: "model-1", modelId: "lab-model", label: "Lab model", roles: ["planner", "researcher"], enabled: true, supportsTools: true, apiStyle: "responses", inputPricePerMillionUsd: 0, outputPricePerMillionUsd: 0,
  }] }],
}));
vi.mock("../workspace/useWorkspace", () => ({
  post: state.post,
  messageOf: (error: unknown) => error instanceof Error ? error.message : "Failed",
  useWorkspace: () => ({ data: { providers: state.providers }, error: null, loading: false, refresh: state.refresh }),
}));
afterEach(cleanup);
beforeEach(() => { state.post.mockReset().mockResolvedValue({}); state.refresh.mockReset().mockResolvedValue(undefined); });

describe("provider model management", () => {
  it("adds another model using the existing provider and explicit capabilities", async () => {
    render(<ProviderModelsPanel canManage />);
    expect(state.post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Add model" }));
    fireEvent.change(screen.getByLabelText("Model ID"), { target: { value: "lab-extractor" } });
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Extractor" } });
    fireEvent.click(screen.getByLabelText("This model supports function tools"));
    fireEvent.change(screen.getByLabelText("Input price (USD / million tokens)"), { target: { value: "0" } });
    fireEvent.change(screen.getByLabelText("Output price (USD / million tokens)"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Save model" }));
    await waitFor(() => expect(state.post).toHaveBeenCalledWith("/api/agent-workspace/providers/provider-1/models", expect.objectContaining({
      modelId: "lab-extractor", label: "Extractor", supportsTools: true, apiStyle: "inherit",
      roles: ["planner", "researcher", "extractor", "reviewer"],
      inputPricePerMillionUsd: 0, outputPricePerMillionUsd: 0,
    })));
    expect(state.refresh).toHaveBeenCalled();
  });

  it("preserves model roles and pricing when disabling a model", async () => {
    render(<ProviderModelsPanel canManage />);
    fireEvent.click(screen.getByRole("button", { name: "Disable Lab model" }));
    await waitFor(() => expect(state.post).toHaveBeenCalledWith(expect.stringContaining("/provider-1/models"), expect.objectContaining({
      modelId: "lab-model", enabled: false, supportsTools: true, apiStyle: "responses",
      roles: ["planner", "researcher"], inputPricePerMillionUsd: 0,
    })));
  });

  it("discovers only on request and lets the user configure a reported ID", async () => {
    state.post.mockResolvedValueOnce({ models: [{ modelId: "chem-7b" }] });
    render(<ProviderModelsPanel canManage />);
    fireEvent.click(screen.getByRole("button", { name: "Discover models" }));
    await waitFor(() => expect(screen.getByRole("option", { name: "chem-7b" })).toBeTruthy());
    expect(state.post).toHaveBeenCalledWith("/api/agent-workspace/providers/provider-1/discover");
    fireEvent.click(screen.getByRole("button", { name: "Configure selected model" }));
    expect((screen.getByLabelText("Model ID") as HTMLInputElement).value).toBe("chem-7b");
    expect((screen.getByLabelText("This model supports function tools") as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText("Model API protocol") as HTMLSelectElement).value).toBe("inherit");
  });

  it("edits a model protocol without changing its model identity or credential", async () => {
    render(<ProviderModelsPanel canManage />);
    expect(screen.getByText("API: Responses API")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Edit Lab model" }));
    expect((screen.getByLabelText("Model API protocol") as HTMLSelectElement).value).toBe("responses");
    fireEvent.change(screen.getByLabelText("Model API protocol"), { target: { value: "chat_completions" } });
    fireEvent.click(screen.getByRole("button", { name: "Save model" }));
    await waitFor(() => expect(state.post).toHaveBeenCalledWith("/api/agent-workspace/providers/provider-1/models", expect.objectContaining({ modelId: "lab-model", apiStyle: "chat_completions", supportsTools: true })));
    expect(state.post.mock.calls[0][1]).not.toHaveProperty("apiKey");
  });

  it("shows configuration read-only to researchers without provider management", () => {
    render(<ProviderModelsPanel canManage={false} />);
    expect(screen.getByText("Lab model")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add model" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Discover models" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit Lab model" })).toBeNull();
  });
});
