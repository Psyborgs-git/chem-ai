import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const view = {
  run: { id: "run-1", kind: "simulation", status: "blocked", taskId: null, error: null },
  report: {
    id: "rep-1",
    runId: "run-1",
    evaluatedBy: "user-1",
    operation: "simulation",
    verdict: "infeasible",
    basis: "compatibility_check",
    sizes: { modelBytes: 4096 },
    envelope: { cpu_cores: 32, memory_bytes: 274877906944 },
    configurations: [
      {
        name: "approved",
        kind: "approved",
        qualityImpact: "none",
        requiresQualityApproval: false,
        compatible: true,
        basis: "compatibility_check",
        note: null,
        estimates: { memory_bytes: { low: 274877906944, high: 274877906944 } },
        uncertainty: {},
        groups: {
          compute: {
            verdict: "infeasible",
            failures: [
              {
                dimension: "memory_bytes",
                required: 274877906944,
                capacity: 17179869184,
                reserve: 2147483648,
                availableWhenIdle: 15032385536,
              },
            ],
            busy: [],
            missing: [],
          },
        },
        verdict: "infeasible",
        detail: "exceeds available capacity on: memory_bytes",
        fitsGroup: null,
        busyGroups: [],
      },
    ],
    uncertainty: { memory_bytes: "declared" },
    reasons: [
      {
        configuration: "approved",
        verdict: "infeasible",
        detail: "exceeds available capacity on: memory_bytes",
        groups: {},
      },
    ],
    missing: [],
    hardware: { os: "Linux", arch: "x86_64", ram_available_bytes: 8000000000, gpus: [], observed_at: "2026-10-06T00:00:00Z" },
    createdAt: "2026-10-06T00:00:01Z",
  },
  proposal: {
    id: "prop-1",
    runId: "run-1",
    feasibilityReportId: "rep-1",
    status: "proposed",
    approved: false,
    boundInputs: { runId: "run-1" },
    boundDigest: "ab".repeat(32),
    requiredCapability: "approve_export",
    sideEffects: "none",
    createdAt: "2026-10-06T00:00:02Z",
  },
  cloud: {
    status: "not_configured",
    provider: null,
    account: null,
    budget: null,
    egress: "deny",
    detail: "no cloud provider, account, or budget is configured",
  },
};

vi.mock("react-relay", () => ({
  graphql: () => ({}),
  useLazyLoadQuery: () => ({ runFallback: view }),
  useMutation: () => [vi.fn(), false],
}));

vi.mock("react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router")>();
  return {
    ...actual,
    Link: ({ to, children }: { to: string; children: React.ReactNode }) => (
      <a href={to}>{children}</a>
    ),
  };
});

import { FallbackPanel } from "./FallbackPanel";

describe("fallback decision surface", () => {
  it("shows the infeasible evidence and an unapproved proposal with no spend", () => {
    render(<FallbackPanel runId="run-1" />);
    const report = screen.getByLabelText("feasibility report");
    expect(report).toHaveAttribute("data-report-verdict", "infeasible");
    expect(screen.getByText("not_configured")).toBeInTheDocument();
    expect(screen.getByText("unapproved")).toBeInTheDocument();
    expect(screen.getByText(/needs 274877906944, 15032385536 available when idle/)).toBeInTheDocument();
    expect(screen.getByText(/no payload, recipient, transfer, or spend/)).toBeInTheDocument();
    expect(screen.getByText("approve_export")).toBeInTheDocument();
  });
});
