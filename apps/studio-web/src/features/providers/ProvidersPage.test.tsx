import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

const state = vi.hoisted(() => ({ commit: vi.fn(), canManage: true, cleanupPending: false }));
vi.mock("react-relay", () => ({ graphql: () => ({}), useMutation: () => [state.commit, false], useLazyLoadQuery: () => ({ canManageInferenceProviders: state.canManage, inferenceCredentialCleanupPending: state.cleanupPending, inferenceProviders: [{ id: "provider-1", revision: 2, name: "Saved connection", kind: "openai_compatible", baseUrl: "http://127.0.0.1:9999/v1", model: "test-model", apiStyle: "chat_completions", enabled: true, supportsTools: true, hasApiKey: true, lastTestStatus: "untested", lastTestAt: null, createdAt: "2026-11-01T00:00:00Z", updatedAt: "2026-11-01T00:00:00Z", lastTestDetail: "untrusted-api-key-echo" }] }) }));
vi.mock("../../components/layout/CreateSheet", () => ({ CreateSheet: ({ open, title, children }: { open: boolean; title: string; children: ReactNode }) => open ? <section role="dialog" aria-label={title}>{children}</section> : null }));
vi.mock("./ProviderModelsPanel", () => ({ ProviderModelsPanel: () => null }));
import { ProvidersPage } from "./ProvidersPage";

describe("saved provider management", () => {
  beforeEach(() => { state.commit.mockReset(); state.canManage = true; state.cleanupPending = false; });

  it("shows redacted connection metadata without rendering arbitrary endpoint error details", () => {
    render(<ProvidersPage />);
    const card = screen.getByRole("article", { name: "Saved connection" });
    expect(within(card).getByText("Key stored securely")).toBeVisible();
    expect(within(card).getByText("Not tested")).toBeVisible();
    expect(screen.queryByText(/untrusted-api-key-echo/)).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue(/api-key/)).not.toBeInTheDocument();
  });

  it("allows readers to view metadata while hiding management controls", () => {
    state.canManage = false; render(<ProvidersPage />);
    expect(screen.getByRole("article", { name: "Saved connection" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Add provider" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Test connection" })).not.toBeInTheDocument();
  });

  it("tests saved settings by ID only and reports the limited scope of a real connection check", async () => {
    render(<ProvidersPage />);
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
    const request = state.commit.mock.calls[0][0];
    expect(Object.keys(request.variables.input).sort()).toEqual(["clientMutationId", "id"]);
    expect(request.variables.input.id).toBe("provider-1");
    await act(async () => request.onCompleted({ providers: { test: { status: "reachable", detail: "untrusted-api-key-echo", errors: [] } } }));
    expect(screen.getByText(/No research context was sent/)).toBeVisible();
    expect(screen.queryByText(/untrusted-api-key-echo/)).not.toBeInTheDocument();
  });

  it("requires explicit remove confirmation and reports retired-key cleanup truthfully", async () => {
    render(<ProvidersPage />);
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(state.commit).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole("dialog", { name: "Remove provider?" })).getByRole("button", { name: "Remove provider" }));
    expect(state.commit.mock.calls[0][0].variables.input).toMatchObject({ id: "provider-1", expectedRevision: 2 });
    await act(async () => state.commit.mock.calls[0][0].onCompleted({ providers: { delete: { deleted: true, credentialCleanupPending: true, errors: [] } } }));
    expect(screen.getByRole("alert")).toHaveTextContent("Unlock your macOS keychain, then choose Retry key cleanup");
  });

  it("offers an explicit retired-credential cleanup retry and never implies unlocking alone completes it", async () => {
    state.cleanupPending = true; render(<ProvidersPage />);
    expect(screen.getByText(/Unlocking alone does not complete cleanup/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry key cleanup" }));
    expect(state.commit).toHaveBeenCalledTimes(1);
    state.cleanupPending = false;
    await act(async () => state.commit.mock.calls[0][0].onCompleted({ providers: { cleanupCredentials: { pending: false, errors: [] } } }));
    expect(screen.queryByRole("button", { name: "Retry key cleanup" })).not.toBeInTheDocument();
    expect(screen.getByText("Retired API keys removed from secure storage.")).toBeVisible();
  });
});
