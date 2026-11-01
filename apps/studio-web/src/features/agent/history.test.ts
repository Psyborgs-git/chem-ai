import { describe, expect, it } from "vitest";
import { chatTitle, historyGroups } from "./history";
describe("chat history", () => {
  it("orders recent sessions and groups them by date", () => {
    const groups = historyGroups([{ id: "older", title: "Old", updatedAt: "2026-10-01T10:00:00Z" }, { id: "today", title: "Current", updatedAt: "2026-11-01T10:00:00Z" }, { id: "yesterday", title: "Yesterday", updatedAt: "2026-10-31T10:00:00Z" }], "", new Date("2026-11-01T12:00:00Z"));
    expect(groups.map((group) => group.label)).toEqual(["Today", "Yesterday", "Older"]);
    expect(chatTitle("  A\n  long title  ")).toBe("A long title");
  });
  it("trusts server message search even when neither title nor preview contains the query", () => {
    expect(historyGroups([{ id: "one", title: "Different title", lastMessagePreview: "Later answer" }], "buried message", new Date(), true)[0].threads[0].id).toBe("one");
    expect(historyGroups([{ id: "one", title: "Different title" }], "missing", new Date(), false)).toEqual([]);
  });
  it("includes midnight in yesterday's calendar group", () => {
    const now = new Date(2026, 10, 1, 12), midnight = new Date(2026, 9, 31);
    expect(historyGroups([{ id: "midnight", title: "Saved", updatedAt: midnight.toISOString() }], "", now)[0].label).toBe("Yesterday");
  });
});
