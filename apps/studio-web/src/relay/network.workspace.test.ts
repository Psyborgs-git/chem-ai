import { afterEach, expect, it, vi } from "vitest";
import { workspaceRequest } from "./network";
afterEach(() => vi.unstubAllGlobals());
it("preserves HTTP status alongside the authenticated workspace error", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({ errors: [{ code: "NOT_FOUND", message: "Private chat not found" }] }) });
  vi.stubGlobal("fetch", fetch);
  await expect(workspaceRequest("/api/agent-workspace/threads/missing")).rejects.toMatchObject({ message: "Private chat not found", status: 404 });
  expect(fetch).toHaveBeenCalledWith("/api/agent-workspace/threads/missing", expect.objectContaining({ credentials: "same-origin" }));
});
