import { describe, expect, it } from "vitest";
import { activityRows, activitySummary, type ActivityMessage } from "./activity";
const message = (id: string, kind: string, call: string, content = "{}", tool = "create_notebook"): ActivityMessage => ({ id, kind, role: kind === "tool_result" ? "tool" : "assistant", content, refs: { tool, toolCallId: call } });
describe("agent activity", () => {
  it("pairs parallel calls and results by call ID without hiding conversation text", () => {
    const rows = activityRows([message("a", "tool_call", "one"), message("b", "tool_call", "two"), message("c", "tool_result", "two", '{"ok":true,"data":{"title":"Second notebook"}}'), message("d", "tool_result", "one", '{"ok":true,"data":{"title":"First notebook"}}'), { id: "answer", kind: "message", role: "assistant", content: "Saved both notebooks.", refs: {} }]);
    expect(rows).toHaveLength(3);
    expect(rows[0].type === "tool" && rows[0].result?.id).toBe("d");
    expect(rows[1].type === "tool" && activitySummary(rows[1]).detail).toBe("Second notebook");
    expect(rows[2].type).toBe("message");
  });
  it("does not merge a later run that reuses a completed call ID", () => {
    const rows = activityRows([message("a", "tool_call", "same"), message("b", "tool_result", "same"), message("c", "tool_call", "same"), message("d", "tool_result", "same")]);
    expect(rows).toHaveLength(2);
    expect(rows[1].type === "tool" && rows[1].result?.id).toBe("d");
  });
  it("makes failures visible and leaves pending work distinct from success", () => {
    const pending = activityRows([message("a", "tool_call", "one")])[0];
    const failure = activityRows([message("b", "tool_result", "two", '{"ok":false,"error":{"message":"No training rights"}}')])[0];
    expect(pending.type === "tool" && activitySummary(pending).detail).toBe("Working…");
    expect(failure.type === "tool" && activitySummary(failure)).toEqual(expect.objectContaining({ failed: true, detail: "No training rights" }));
  });
  it("labels documentation work as articles rather than scientific sources", () => {
    const row = activityRows([message("docs", "tool_result", "docs-call", '{"ok":true,"data":{"results":[{"title":"Getting started"}]}}', "search_studio_docs")])[0];
    expect(row.type === "tool" && activitySummary(row)).toEqual({ title: "Search documentation", detail: "1 article", failed: false });
    const wrapped = activityRows([message("wrapped", "tool_result", "wrapped-call", '{"ok":true,"data":{"ok":true,"untrusted":true,"data":{"results":[{"title":"Getting started"}]}}}', "search_studio_docs")])[0];
    expect(wrapped.type === "tool" && activitySummary(wrapped).detail).toBe("1 article");
  });
  it("shows a refused dispatcher call as a failure inside its transport envelope", () => {
    const row = activityRows([message("refused", "tool_result", "docs-call", '{"ok":true,"data":{"ok":false,"error":{"message":"Unknown documentation article"}}}', "read_studio_doc")])[0];
    expect(row.type === "tool" && activitySummary(row)).toEqual({ title: "Read documentation", detail: "Unknown documentation article", failed: true });
  });
});

it("collapses all tools in the same turn into one activity while preserving the final answer", async () => {
  const { transcriptRows } = await import("./activity");
  const rows = transcriptRows([{ id: "user", runId: "run-one", kind: "message", role: "user", content: "Research", refs: {} }, { ...message("call-a", "tool_call", "a"), runId: "run-one" }, { ...message("result-a", "tool_result", "a"), runId: "run-one" }, { ...message("call-b", "tool_call", "b"), runId: "run-one" }, { ...message("result-b", "tool_result", "b"), runId: "run-one" }, { id: "answer", runId: "run-one", kind: "message", role: "assistant", content: "Finished", refs: {} }]);
  expect(rows).toHaveLength(3);
  expect(rows[1].type === "activity" && rows[1].tools).toHaveLength(2);
  expect(rows[2].type === "message" && rows[2].message.content).toBe("Finished");
});
