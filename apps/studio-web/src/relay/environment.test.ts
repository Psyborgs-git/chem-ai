import { RecordSource } from "relay-runtime";
import { describe, expect, it } from "vitest";

import { getRelayEnvironment, resetRelayEnvironment } from "./environment";

describe("single relay environment (AT-0104-3)", () => {
  it("returns the same instance across calls", () => {
    resetRelayEnvironment();
    expect(getRelayEnvironment()).toBe(getRelayEnvironment());
  });

  it("reset drops the scoped cache (logout/workspace change)", () => {
    const first = getRelayEnvironment();
    // seed a cached record, as a fetched query would
    first
      .getStore()
      .publish(
        new RecordSource({
          "test-1": { __id: "test-1", __typename: "Project" },
        }),
      );
    expect(first.getStore().getSource().get("test-1")).toBeDefined();
    resetRelayEnvironment();
    const second = getRelayEnvironment();
    expect(second).not.toBe(first);
    expect(second.getStore().getSource().get("test-1")).toBeUndefined();
  });
});
