import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ commit: vi.fn() }));
vi.mock("react-relay", () => ({
  graphql: () => ({}),
  useMutation: () => [state.commit, false],
  useLazyLoadQuery: () => ({ taskContractRevisions: { edges: [{ node: {
    id: "contract-draft-1", revision: 1, status: "draft", contentHash: "recorded-hash", createdAt: "2026-10-29T00:00:00Z",
    payload: { metrics: [{ id: "metric.index", label: "Recorded index", operator: "gte", target_values: ["0"], unit: "dimensionless", required: true, required_evidence: ["lab_measurement"] }], hard_constraints: [] },
  } }] } }),
}));
import { ContractEditor } from "./ContractEditor";

describe("criteria summary refresh acknowledgement", () => {
  beforeEach(() => state.commit.mockReset());

  it.each(["draft", "freeze"] as const)("refreshes surrounding task context only after a successful %s acknowledgement", async (operation) => {
    const saved = vi.fn();
    render(<ContractEditor taskId={`success-${operation}`} workflowState="draft" onSaved={saved} />);
    fireEvent.click(screen.getByRole("button", { name: operation === "draft" ? "save draft" : "freeze contract" }));
    expect(state.commit).toHaveBeenCalledTimes(1);
    expect(saved).not.toHaveBeenCalled();
    const response = operation === "draft"
      ? { contractDraftCreate: { errors: [], contractRevision: { id: "contract-draft-1" } } }
      : { contractFreeze: { errors: [] } };
    await act(async () => state.commit.mock.calls[0][0].onCompleted(response));
    expect(saved).toHaveBeenCalledTimes(1);
  });

  it.each(["draft", "freeze"] as const)("keeps task context unchanged when the server refuses a %s", async (operation) => {
    const saved = vi.fn();
    render(<ContractEditor taskId={`refused-${operation}`} workflowState="draft" onSaved={saved} />);
    fireEvent.click(screen.getByRole("button", { name: operation === "draft" ? "save draft" : "freeze contract" }));
    const result = { errors: [{ code: "INVALID_INPUT", message: "Recorded criterion requires review" }] };
    await act(async () => state.commit.mock.calls[0][0].onCompleted(operation === "draft" ? { contractDraftCreate: result } : { contractFreeze: result }));
    expect(saved).not.toHaveBeenCalled();
    expect(screen.getByText(/Recorded criterion requires review/)).toBeVisible();
  });
});
