import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../../components/atoms/Badge";
import { Button } from "../../../components/atoms/Button";
import { EmptyState } from "../../../components/states/states";
import { FallbackRequestMutation, FallbackViewQuery } from "./operations";

import type { fallbackRunViewQuery } from "../../../__generated__/fallbackRunViewQuery.graphql";
import type { fallbackRequestMutation } from "../../../__generated__/fallbackRequestMutation.graphql";

// Local mirrors of the JSON evidence payloads (§20.1-20.2): every
// field the API observed or declared, rendered as-is — never assumed.
export type DimensionEstimate = { low: number; high: number };

export type GroupVerdict = {
  verdict: "fits" | "busy" | "infeasible";
  failures: ReadonlyArray<Record<string, unknown>>;
  busy: ReadonlyArray<Record<string, unknown>>;
  missing: ReadonlyArray<string>;
};

export type ConfigurationVerdict = {
  name: string;
  kind: string;
  qualityImpact: string;
  requiresQualityApproval: boolean;
  compatible: boolean;
  basis: string;
  note: string | null;
  estimates: Record<string, DimensionEstimate>;
  uncertainty: Record<string, string>;
  groups: Record<string, GroupVerdict>;
  verdict: "fits" | "busy" | "infeasible" | "excluded";
  detail: string;
  fitsGroup: string | null;
  busyGroups: ReadonlyArray<string>;
};

export type FeasibilityReport = {
  id: string;
  runId: string;
  evaluatedBy: string;
  operation: string;
  verdict: "feasible" | "infeasible";
  basis: string;
  sizes: Record<string, number>;
  envelope: Record<string, number>;
  configurations: ReadonlyArray<ConfigurationVerdict>;
  uncertainty: Record<string, string>;
  reasons: ReadonlyArray<Record<string, unknown>>;
  missing: ReadonlyArray<string>;
  hardware: Record<string, unknown> | null;
  createdAt: string | null;
};

export type ExportProposalView = {
  id: string;
  runId: string;
  feasibilityReportId: string;
  status: string;
  approved: boolean;
  boundInputs: Record<string, unknown>;
  boundDigest: string;
  requiredCapability: string;
  sideEffects: string;
  createdAt: string | null;
};

export type CloudCapability = {
  status: string;
  provider: string | null;
  account: string | null;
  budget: string | null;
  egress: string;
  detail: string;
};

export type FallbackView = {
  run: {
    id: string;
    kind: string;
    status: string;
    taskId: string | null;
    error: Record<string, unknown> | null;
  };
  report: FeasibilityReport | null;
  proposal: ExportProposalView | null;
  cloud: CloudCapability;
};

const DIM_LABELS: Record<string, string> = {
  cpu_cores: "cpu cores",
  memory_bytes: "memory (bytes)",
  gpu_devices: "gpu devices",
  storage_bytes: "storage (bytes)",
  wall_seconds: "wall seconds",
};

function verdictTone(verdict: string): "info" | "success" | "warning" | "danger" | "neutral" {
  switch (verdict) {
    case "feasible":
    case "fits":
      return "success";
    case "busy":
      return "info";
    case "infeasible":
      return "danger";
    case "excluded":
      return "neutral";
    default:
      return "neutral";
  }
}

function estimateText(est: DimensionEstimate): string {
  return est.low === est.high ? String(est.low) : `${est.low}…${est.high}`;
}

function CloudCard({ cloud }: { cloud: CloudCapability }) {
  return (
    <section aria-label="cloud capability" data-cloud-status={cloud.status}>
      <h2>cloud</h2>
      <p>
        <Badge tone={cloud.status === "not_configured" ? "neutral" : "warning"}>
          {cloud.status}
        </Badge>{" "}
        <span>egress: {cloud.egress}</span>
      </p>
      <p>{cloud.detail}</p>
    </section>
  );
}

function ProposalCard({ proposal }: { proposal: ExportProposalView }) {
  return (
    <section aria-label="export proposal" data-proposal-status={proposal.status}>
      <h2>export review proposal</h2>
      <p>
        <Badge tone="warning">{proposal.status}</Badge>{" "}
        <Badge tone={proposal.approved ? "success" : "neutral"}>
          {proposal.approved ? "approved" : "unapproved"}
        </Badge>
      </p>
      <table className="kv">
        <tbody>
          <tr>
            <th scope="row">required capability</th>
            <td>{proposal.requiredCapability}</td>
          </tr>
          <tr>
            <th scope="row">bound digest</th>
            <td>{proposal.boundDigest.slice(0, 16)}…</td>
          </tr>
          <tr>
            <th scope="row">side effects</th>
            <td>{proposal.sideEffects}</td>
          </tr>
        </tbody>
      </table>
      <p role="note">
        A proposal is a review item only — no payload, recipient, transfer, or
        spend exists. A human holding {proposal.requiredCapability} may approve
        it through the approvals ledger; nothing here submits anything.
      </p>
    </section>
  );
}

function ConfigurationTable({ configs }: { configs: ReadonlyArray<ConfigurationVerdict> }) {
  return (
    <table className="data">
      <thead>
        <tr>
          <th scope="col">configuration</th>
          <th scope="col">kind</th>
          <th scope="col">quality impact</th>
          <th scope="col">verdict</th>
          <th scope="col">estimates (upper bound)</th>
          <th scope="col">evidence</th>
        </tr>
      </thead>
      <tbody>
        {configs.map((c) => (
          <tr key={c.name} data-config={c.name} data-verdict={c.verdict}>
            <th scope="row">{c.name}</th>
            <td>{c.kind}</td>
            <td>
              {c.qualityImpact}
              {c.requiresQualityApproval ? " (needs approval)" : ""}
            </td>
            <td>
              <Badge tone={verdictTone(c.verdict)}>{c.verdict}</Badge>
              {!c.compatible ? " incompatible" : ""}
            </td>
            <td>
              {Object.entries(c.estimates)
                .filter(([, est]) => est.high > 0)
                .map(([dim, est]) => `${dim} ${estimateText(est)}`)
                .join(", ") || "declared zero"}
            </td>
            <td>
              {c.detail}
              {c.note ? ` — ${c.note}` : ""}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function GroupEvidence({ config }: { config: ConfigurationVerdict }) {
  const entries = Object.entries(config.groups);
  if (entries.length === 0) return null;
  return (
    <section aria-label={`group evidence for ${config.name}`}>
      <h4>{config.name}</h4>
      <ul>
        {entries.map(([name, g]) => (
          <li key={name} data-group={name} data-verdict={g.verdict}>
            <strong>{name}</strong>: {g.verdict}
            {g.failures.map((f, i) => (
              <div key={i}>
                {DIM_LABELS[String(f.dimension)] ?? String(f.dimension)}: needs{" "}
                {String(f.required)}, {String(f.availableWhenIdle)} available when idle
              </div>
            ))}
            {g.busy.map((b, i) => (
              <div key={i}>
                {DIM_LABELS[String(b.dimension)] ?? String(b.dimension)}: needs{" "}
                {String(b.required)}, {String(b.availableNow)} free now (reserved, transient)
              </div>
            ))}
            {g.missing.length > 0 && <div>unobserved: {g.missing.join(", ")}</div>}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ReportView({ report }: { report: FeasibilityReport }) {
  const sizeEntries = Object.entries(report.sizes);
  return (
    <section aria-label="feasibility report" data-report-verdict={report.verdict}>
      <h2>feasibility evidence</h2>
      <p>
        <Badge tone={verdictTone(report.verdict)}>{report.verdict}</Badge>{" "}
        <Badge tone="neutral">{report.basis}</Badge>{" "}
        <span>
          {report.operation} · evaluated {report.createdAt ?? "unknown"}
        </span>
      </p>
      {sizeEntries.length > 0 && (
        <table className="kv" aria-label="job sizes">
          <tbody>
            {sizeEntries.map(([k, v]) => (
              <tr key={k}>
                <th scope="row">{k}</th>
                <td>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3>configurations</h3>
      <ConfigurationTable configs={report.configurations} />
      {report.configurations.map((c) =>
        Object.keys(c.groups).length > 0 ? <GroupEvidence key={c.name} config={c} /> : null,
      )}
      {Object.keys(report.uncertainty).length > 0 && (
        <p role="note">
          declared uncertainty:{" "}
          {Object.entries(report.uncertainty)
            .map(([d, b]) => `${d}: ${b}`)
            .join(", ")}
        </p>
      )}
      {report.missing.length > 0 && (
        <p role="note">unobserved dimensions: {report.missing.join(", ")}</p>
      )}
      {report.hardware != null && (
        <p role="note">
          hardware observed: {String(report.hardware.os ?? "unknown")} /{" "}
          {String(report.hardware.arch ?? "unknown")} · RAM{" "}
          {report.hardware.ram_available_bytes != null
            ? String(report.hardware.ram_available_bytes)
            : "unobserved"}{" "}
          bytes free · GPUs {Array.isArray(report.hardware.gpus) ? report.hardware.gpus.length : "unobserved"} ·{" "}
          {String(report.hardware.observed_at ?? "")}
        </p>
      )}
    </section>
  );
}

export function FallbackPanel({ runId }: { runId: string }) {
  const data = useLazyLoadQuery<fallbackRunViewQuery>(FallbackViewQuery, { runId });
  const [commit, pending] = useMutation<fallbackRequestMutation>(FallbackRequestMutation);
  const view = data.runFallback as unknown as FallbackView;

  function evaluate() {
    commit({
      variables: { input: { runId } },
      onCompleted: () => {
        // The view query re-renders via refetch-on-nav or manual reload;
        // mutation returns the fresh decision directly.
      },
    });
  }

  const report = view.report;
  return (
    <div data-run-id={view.run.id}>
      <h1>fallback review</h1>
      <p>
        <Badge tone="neutral">{view.run.kind}</Badge>{" "}
        <Badge tone={view.run.status === "blocked" ? "warning" : "info"}>{view.run.status}</Badge>
      </p>
      <CloudCard cloud={view.cloud} />
      {report ? (
        <>
          <ReportView report={report} />
          {report.verdict === "feasible" ? (
            <p role="status" data-decision="local_feasible">
              Local execution is feasible — no export review is proposed and
              cloud is not authorized. Cost or speed preference is not local
              infeasibility.
            </p>
          ) : null}
        </>
      ) : (
        <EmptyState title="No feasibility evaluation yet." />
      )}
      {view.proposal ? <ProposalCard proposal={view.proposal} /> : null}
      <Button type="button" disabled={pending} onClick={evaluate} aria-label="evaluate feasibility">
        {report ? "re-evaluate feasibility" : "evaluate feasibility"}
      </Button>
    </div>
  );
}
