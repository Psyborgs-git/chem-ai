import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";

vi.mock("react-relay", () => ({
  graphql: () => ({}),
  useFragment: () => ({ id: "task-fixture", optimizationCampaigns: [] }),
  useMutation: () => [vi.fn(), false],
}));

import { CampaignSummary, OptimizationPanel, type CampaignManifest } from "./OptimizationPanel";
import type { OptimizationPanel_task$key } from "../../__generated__/OptimizationPanel_task.graphql";

describe("optimization scientific status boundary", () => {
  it("shows software smoke and fixture status separately without invented acquisition", () => {
    const manifest: CampaignManifest = {
      scientificStatus: "fixture_only", capabilityStatus: "engine_smoke_passed",
      definition: { seed: 17, target: { name: "synthetic", unit: "dimensionless", method: "fixture" } },
      state: { engine_version: "0.15.0", adapter_version: "baybe-adapter/v1", request_index: 1,
        experiments: [], history: [{ status: "suggested", recommender: "RandomRecommender", acquisition: null, rejected: {} }] },
    };
    render(<CampaignSummary manifest={manifest} />);
    expect(screen.getByText("fixture_only")).toBeInTheDocument();
    expect(screen.getByText("engine_smoke_passed")).toBeInTheDocument();
    expect(screen.getByText(/no acquisition or uncertainty reported/)).toBeInTheDocument();
    expect(screen.queryByText(/experimentally_supported/)).not.toBeInTheDocument();
  });

  it("rejects invalid JSON and does not invent an empty-campaign measurement", async () => {
    const user = userEvent.setup();
    render(<OptimizationPanel taskRef={{} as OptimizationPanel_task$key} />);
    expect(screen.getByText(/No frozen campaigns/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Campaign definition JSON"), "not JSON");
    await user.click(screen.getByRole("button", { name: "Freeze campaign definition" }));
    // Two status regions now legitimately exist (inline form error +
    // EmptyState live region); assert the rejection text itself.
    expect(screen.getByText(/No parameters or results are invented/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Link reviewed observation" })).not.toBeInTheDocument();
  });
});
