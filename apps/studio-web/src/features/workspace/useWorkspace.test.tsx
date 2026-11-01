import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useWorkspace } from "./useWorkspace";

const state = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("../../relay/network", () => ({ workspaceRequest: state.request }));

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
beforeEach(() => { state.request.mockReset(); });

describe("workspace query refresh", () => {
  it("ignores a refresh captured for the previous conversation", async () => {
    state.request.mockImplementation(async (path: string) => ({ id: path.endsWith("/a") ? "a" : "b" }));
    const { result, rerender } = renderHook(({ path }) => useWorkspace<{ id: string }>(path), { initialProps: { path: "/api/agent-workspace/threads/a" } });
    await waitFor(() => expect(result.current.data?.id).toBe("a"));
    const previousRefresh = result.current.refresh;
    rerender({ path: "/api/agent-workspace/threads/b" });
    await waitFor(() => expect(result.current.data?.id).toBe("b"));
    state.request.mockClear();
    // A delayed mutation (for example Stop A) must not repopulate A while
    // the conversation selector and subsequent actions target B.
    await act(async () => { await previousRefresh(); });
    expect(state.request).not.toHaveBeenCalled();
    expect(result.current.data?.id).toBe("b");
  });

  it("keeps the new path loading when the previous request completes late", async () => {
    let resolveA!: (value: { id: string }) => void;
    let resolveB!: (value: { id: string }) => void;
    const first = new Promise<{ id: string }>((resolve) => { resolveA = resolve; });
    const second = new Promise<{ id: string }>((resolve) => { resolveB = resolve; });
    state.request.mockImplementation((path: string) => path.endsWith("/a") ? first : second);
    const { result, rerender } = renderHook(({ path }) => useWorkspace<{ id: string }>(path), { initialProps: { path: "/api/agent-workspace/threads/a" } });
    rerender({ path: "/api/agent-workspace/threads/b" });
    await act(async () => { resolveA({ id: "a" }); await first; });
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(true);
    await act(async () => { resolveB({ id: "b" }); await second; });
    expect(result.current.data?.id).toBe("b");
    expect(result.current.loading).toBe(false);
  });

  it("refreshes the library after a tool event without feeding back into agent polling", async () => {
    state.request.mockResolvedValue({ value: 1 });
    const { result, rerender } = renderHook(({ path }) => useWorkspace<{ value: number }>(path), { initialProps: { path: "/api/library" } });
    await waitFor(() => expect(result.current.data?.value).toBe(1));
    state.request.mockResolvedValue({ value: 2 });
    await act(async () => { window.dispatchEvent(new Event("studio-workspace-updated")); });
    expect(result.current.data?.value).toBe(2);
    expect(state.request).toHaveBeenCalledTimes(2);
    rerender({ path: "/api/agent-workspace/threads/b" });
    await waitFor(() => expect(state.request).toHaveBeenCalledTimes(3));
    state.request.mockClear();
    await act(async () => { window.dispatchEvent(new Event("studio-workspace-updated")); });
    expect(state.request).not.toHaveBeenCalled();
  });

  it("removes the workspace update listener when the consumer unmounts", async () => {
    state.request.mockResolvedValue({ value: 1 });
    const view = renderHook(() => useWorkspace("/api/library"));
    await waitFor(() => expect(view.result.current.loading).toBe(false));
    view.unmount();
    state.request.mockClear();
    act(() => { window.dispatchEvent(new Event("studio-workspace-updated")); });
    expect(state.request).not.toHaveBeenCalled();
  });
});
