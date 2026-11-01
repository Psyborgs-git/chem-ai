import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
const state = vi.hoisted(() => ({ commit: vi.fn() }));
vi.mock("react-relay", () => ({ graphql: () => ({}),
  useMutation: () => [state.commit, false],
  useLazyLoadQuery: () => ({ taskEvaluation: { candidates: [], metrics: [], hardGates: [] }, taskReassessmentStatus: {} }),
}));
import { CloseoutPanel } from "./CloseoutPanel";

describe("legal task transitions", () => {
  beforeEach(() => { state.commit.mockReset(); });
  it.each([["draft", "Start task", "active"], ["paused", "Resume task", "active"], ["active", "send to review", "awaiting_review"]])(
    "%s offers %s", (workflowState, label, toState) => {
      render(<CloseoutPanel taskId="task-1" workflowState={workflowState} />);
      fireEvent.click(screen.getByRole("button", { name: label }));
      expect(state.commit.mock.calls[0][0].variables.input).toEqual({ taskId: "task-1", toState });
    },
  );
  it("does not offer a transition from a cancelled task", () => {
    render(<CloseoutPanel taskId="task-1" workflowState="cancelled" />);
    expect(screen.queryByRole("button", { name: /Start task|Resume task|send to review/ })).not.toBeInTheDocument();
  });
});
