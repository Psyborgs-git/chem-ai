import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const view = {
  proposal: {
    id: "prop-1",
    gid: "RXhwb3J0UHJvcG9zYWw6cHJvcC0x",
    runId: "run-1",
    status: "proposed",
    requiredCapability: "approve_export",
    boundDigest: "ab".repeat(32),
  },
  payload: {
    id: "pay-1",
    gid: "RXhwb3J0UGF5bG9hZDpwYXktMQ==",
    transformationVersion: "export-transform/v1",
    purpose: "property_prediction",
    classification: "confidential",
    sourceClassification: "confidential",
    classificationReview: null,
    digest: "cd".repeat(32),
    recordCount: 2,
    byteSize: 512,
    fields: ["records.conditions", "records.metric", "records.value"],
    document: {
      version: "export-payload/v1",
      transformationVersion: "export-transform/v1",
      purpose: "property_prediction",
      records: [
        {
          ref: "r-0001",
          kind: "measurement",
          fields: {
            metric: "m-0001",
            method: "bench",
            valueType: "numeric",
            value: { kind: "numeric", value: "4.2", unit: "dimensionless" },
            conditions: { actual: { temperature: 296 } },
          },
        },
        {
          ref: "r-0002",
          kind: "claim",
          fields: {
            sourceClass: "document_claim",
            labelKind: "claimed_value",
            statement: { claim: "contact jdoe@acme-lab.example for the deck" },
          },
        },
      ],
      notes: "transformed review payload — names aliased only; NOT anonymous or safe",
    },
    createdAt: "2026-10-06T00:00:03Z",
  },
  redaction: {
    version: "redaction-report/v1",
    removedFields: { measurement: ["id", "sample"], claim: ["id", "artifact"] },
    removedKeys: [
      { ref: "r-0001", path: "value.recorded_by", key: "recorded_by", reason: "metadata_key" },
    ],
    excludedEntries: [
      { recordId: "9f8e7d6c-1234-4000-8000-000000000001", recordKind: "claim", reason: "export_rights_unresolved" },
    ],
    mergedDuplicates: 0,
    aliasedIdentifiers: { count: 3, kinds: ["material", "metric"], localOnly: true, note: "the alias map stays in the local vault" },
  },
  residual: {
    version: "residual-risk/v1",
    verdict: "residual_disclosure",
    anonymous: false,
    safe: false,
    certified: false,
    categories: [
      { kind: "outcomes", count: 1, detail: "measured/predicted values remain exposed", findings: [{ ref: "r-0001", metric: "m-0001", valueType: "numeric" }] },
      { kind: "process_windows", count: 1, findings: [{ ref: "r-0001", path: "conditions.actual", keys: ["temperature"] }] },
      { kind: "free_text", count: 1, findings: [{ ref: "r-0002", fields: ["subject", "statement"] }] },
      { kind: "metadata", count: 2, detail: "record count, ordering, refs remain" },
    ],
    flags: [
      { ref: "r-0002", path: "statement.claim", pattern: "email", severity: "high" },
    ],
    flaggedRecords: ["r-0002"],
    advisory: "Masking is not confidentiality.",
  },
  manifest: {
    version: "export-manifest/v1",
    transformationVersion: "export-transform/v1",
    proposalId: "prop-1",
    proposalBoundDigest: "ab".repeat(32),
    snapshot: { id: "snap-1", digest: "ef".repeat(32), purpose: "property_prediction" },
    payload: { digest: "cd".repeat(32), recordCount: 2, byteSize: 512, fields: [] },
    reports: { redactionDigest: "11".repeat(32), residualDigest: "22".repeat(32) },
    classification: "confidential",
    recipient: { provider: null, account: null, region: null },
    environment: { containerDigest: null, runtime: { python: "3.12", transform: "export-transform/v1" } },
    permittedJob: { operation: "large dft batch", runKind: "simulation", runId: "run-1" },
    limits: { maxRecords: 2000, maxBytes: 4194304 },
    retention: { expectation: null, deletionExpectation: null },
    expiry: null,
    approver: null,
    egress: "deny",
  },
  alias: { count: 3, kinds: ["material", "metric"], localOnly: true },
  approval: { state: "none" },
  snapshots: [
    { id: "snap-1", name: "prop-snap", purpose: "property_prediction", state: "frozen", digest: "ef".repeat(32), taskId: null, taskMatch: false },
  ],
  cloud: {
    status: "not_configured",
    provider: null,
    account: null,
    budget: null,
    egress: "deny",
    detail: "no cloud provider, account, or budget is configured",
  },
  capabilities: { canReview: true, canApprove: true },
  egress: "deny",
};

vi.mock("react-relay", () => ({
  graphql: () => ({}),
  useLazyLoadQuery: () => ({ exportReview: view }),
  useMutation: () => [vi.fn(), false],
}));

import { ExportReviewPanel } from "./ExportReviewPanel";

describe("export disclosure review", () => {
  it("shows the exact payload, honest residual risk and the bound manifest — never anonymous/safe", () => {
    render(<ExportReviewPanel proposalId="RXhwb3J0UHJvcG9zYWw6cHJvcC0x" />);
    // §20.3 trade-off language is honest (banner + residual advisory).
    expect(screen.getAllByText(/Masking is not confidentiality/).length).toBeGreaterThan(0);
    // AT-1002-1: the payload is never labelled anonymous or safe.
    const residual = screen.getByLabelText("residual risk");
    expect(residual).toHaveAttribute("data-verdict", "residual_disclosure");
    expect(screen.getByText("anonymous: false")).toBeInTheDocument();
    expect(screen.getByText("safe: false")).toBeInTheDocument();
    // Residual categories disclose what still leaks.
    expect(screen.getByText("process_windows")).toBeInTheDocument();
    expect(screen.getByText("outcomes")).toBeInTheDocument();
    // AT-1002-2: flagged content stays visible and reviewable.
    expect(screen.getByText("flagged content")).toBeInTheDocument();
    expect(screen.getByText("email")).toBeInTheDocument();
    expect(screen.getByText(/flagged records remain reviewable: r-0002/)).toBeInTheDocument();
    // Exact payload preview + classification.
    expect(screen.getByTestId("payload-document")).toHaveTextContent("export-payload/v1");
    expect(screen.getByLabelText("transformed payload")).toHaveAttribute(
      "data-classification",
      "confidential",
    );
    // Manifest binds egress=deny and explains digest invalidation.
    const manifest = screen.getByLabelText("export manifest");
    expect(manifest).toHaveAttribute("data-egress", "deny");
    expect(screen.getByText(/invalidates|fresh approval/i)).toBeInTheDocument();
    // Redaction report shows the local-only alias map note.
    expect(screen.getByTestId("alias-local")).toHaveTextContent("LOCAL-only");
    // Approval surface exists (state 'none') with approve control.
    expect(screen.getByLabelText("export approval")).toHaveAttribute("data-approval-state", "none");
    expect(screen.getByLabelText("approve export payload")).toBeInTheDocument();
  });
});
