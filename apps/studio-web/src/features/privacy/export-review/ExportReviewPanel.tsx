import { useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../../components/atoms/Badge";
import { Button } from "../../../components/atoms/Button";
import { TextField } from "../../../components/atoms/TextField";
import { EmptyState } from "../../../components/states/states";
import {
  ExportDecideMutation,
  ExportPrepareMutation,
  ExportReviewQuery,
  ExportSetClassificationMutation,
} from "./operations";

import type { exportReviewQuery } from "../../../__generated__/exportReviewQuery.graphql";
import type { exportPrepareMutation } from "../../../__generated__/exportPrepareMutation.graphql";
import type { exportDecideMutation } from "../../../__generated__/exportDecideMutation.graphql";
import type { exportSetClassificationMutation } from "../../../__generated__/exportSetClassificationMutation.graphql";

// Local mirrors of the JSON review view (§20.2-20.3, CS-1002): every
// field the API produced is rendered as-is — a scanner flags risk; it
// can never certify the payload anonymous or safe.
export type PayloadRecord = {
  ref: string;
  kind: string;
  fields: Record<string, unknown>;
};

export type PayloadDocument = {
  version: string;
  transformationVersion: string;
  purpose: string;
  records: ReadonlyArray<PayloadRecord>;
  notes: string;
};

export type PayloadView = {
  id: string;
  gid: string;
  transformationVersion: string;
  purpose: string;
  classification: string;
  sourceClassification: string;
  classificationReview: {
    from: string;
    to: string;
    rationale: string;
    reviewedBy: string;
    at: string;
  } | null;
  digest: string;
  recordCount: number;
  byteSize: number;
  fields: ReadonlyArray<string>;
  document: PayloadDocument;
  createdAt: string | null;
};

export type RemovedKey = {
  ref: string | null;
  path: string;
  key: string | null;
  reason: string;
};

export type ExcludedEntry = {
  recordId: string;
  recordKind: string;
  reason: string | null;
};

export type RedactionReport = {
  version: string;
  removedFields: Record<string, ReadonlyArray<string>>;
  removedKeys: ReadonlyArray<RemovedKey>;
  excludedEntries: ReadonlyArray<ExcludedEntry>;
  mergedDuplicates: number;
  aliasedIdentifiers: { count: number; kinds: ReadonlyArray<string>; localOnly: boolean; note: string };
};

export type ResidualFinding = {
  ref?: string;
  path?: string;
  keys?: ReadonlyArray<string>;
  fields?: ReadonlyArray<string>;
  metric?: string;
  valueType?: string;
  detail?: string;
};

export type ResidualCategory = {
  kind: string;
  count: number;
  detail?: string;
  findings?: ReadonlyArray<ResidualFinding>;
};

export type RiskFlag = {
  ref: string;
  path: string;
  pattern: string;
  severity: string;
};

export type ResidualReport = {
  version: string;
  verdict: string;
  anonymous: boolean;
  safe: boolean;
  certified: boolean;
  categories: ReadonlyArray<ResidualCategory>;
  flags: ReadonlyArray<RiskFlag>;
  flaggedRecords: ReadonlyArray<string>;
  advisory: string;
};

export type ExportManifest = {
  version: string;
  transformationVersion: string;
  proposalId: string;
  proposalBoundDigest: string;
  snapshot: { id: string; digest: string; purpose: string };
  payload: {
    digest: string;
    recordCount: number;
    byteSize: number;
    fields: ReadonlyArray<string>;
  };
  reports: { redactionDigest: string; residualDigest: string };
  classification: string;
  recipient: { provider: string | null; account: string | null; region: string | null };
  environment: { containerDigest: string | null; runtime: Record<string, string> };
  permittedJob: { operation: string; runKind: string; runId: string };
  limits: { maxRecords: number; maxBytes: number };
  retention: { expectation: string | null; deletionExpectation: string | null };
  expiry: string | null;
  approver: string | null;
  egress: string;
};

export type SnapshotOption = {
  id: string;
  name: string;
  purpose: string;
  state: string;
  digest: string;
  taskId: string | null;
  taskMatch: boolean;
};

export type ApprovalState = {
  state: string;
  decision?: string;
  decidedBy?: string;
  boundDigest?: string;
  expiresAt?: string | null;
  rationale?: string | null;
  detail?: string;
};

export type ExportReviewView = {
  proposal: {
    id: string;
    gid: string;
    runId: string;
    status: string;
    requiredCapability: string;
    boundDigest: string;
  };
  payload: PayloadView | null;
  redaction: RedactionReport | null;
  residual: ResidualReport | null;
  manifest: ExportManifest | null;
  alias: { count: number; kinds: ReadonlyArray<string>; localOnly: boolean } | null;
  approval: ApprovalState;
  snapshots: ReadonlyArray<SnapshotOption>;
  cloud: {
    status: string;
    provider: string | null;
    account: string | null;
    budget: string | null;
    egress: string;
    detail: string;
  };
  capabilities: { canReview: boolean; canApprove: boolean };
  egress: string;
};

function approvalTone(state: string): "info" | "success" | "warning" | "danger" | "neutral" {
  switch (state) {
    case "approved":
      return "success";
    case "rejected":
    case "revoked":
      return "danger";
    case "stale":
    case "expired":
      return "warning";
    default:
      return "neutral";
  }
}

function severityTone(severity: string): "warning" | "danger" | "neutral" {
  return severity === "high" ? "danger" : severity === "medium" ? "warning" : "neutral";
}

/** §20.3 trade-off language, surfaced honestly: masking names is not
 * confidentiality and the scanner's flags are a floor, not a ceiling. */
function TradeoffBanner() {
  return (
    <section aria-label="disclosure advisory" data-kind="advisory">
      <p role="note">
        Masking is not confidentiality. Aliasing direct names does not make a
        payload anonymous or safe: ratios, structures, process windows,
        outcomes, free text and metadata remain exposed. The residual-risk
        report is a flagged-risk floor — a scanner can never certify that all
        trade secrets are removed. Approval binds the exact payload and
        transformation version; any change requires a fresh review.
      </p>
    </section>
  );
}

function ProposalCard({ proposal }: { proposal: ExportReviewView["proposal"] }) {
  return (
    <section aria-label="export proposal" data-proposal-status={proposal.status}>
      <h2>export proposal</h2>
      <p>
        <Badge tone={proposal.status === "approved" ? "success" : "warning"}>
          {proposal.status}
        </Badge>{" "}
        <Badge tone="neutral">{proposal.requiredCapability}</Badge>
      </p>
      <table className="kv">
        <tbody>
          <tr>
            <th scope="row">run</th>
            <td>{proposal.runId}</td>
          </tr>
          <tr>
            <th scope="row">proposal bound digest</th>
            <td>{proposal.boundDigest.slice(0, 16)}…</td>
          </tr>
        </tbody>
      </table>
    </section>
  );
}

function PayloadCard({ payload }: { payload: PayloadView }) {
  return (
    <section aria-label="transformed payload" data-classification={payload.classification}>
      <h2>exact payload</h2>
      <p>
        <Badge tone="neutral">{payload.transformationVersion}</Badge>{" "}
        <Badge tone={payload.classification === "internal" ? "info" : "warning"}>
          {payload.classification}
        </Badge>{" "}
        <span>
          {payload.recordCount} records · {payload.byteSize} bytes · digest{" "}
          {payload.digest.slice(0, 16)}…
        </span>
      </p>
      {payload.classificationReview ? (
        <p role="note">
          classification reviewed: {payload.classificationReview.from} →{" "}
          {payload.classificationReview.to} — {payload.classificationReview.rationale}
        </p>
      ) : (
        <p role="note">classification preserved from source: {payload.sourceClassification}</p>
      )}
      <details>
        <summary>payload fields ({payload.fields.length})</summary>
        <ul>
          {payload.fields.map((f) => (
            <li key={f}>
              <code>{f}</code>
            </li>
          ))}
        </ul>
      </details>
      <pre data-testid="payload-document">{JSON.stringify(payload.document, null, 2)}</pre>
    </section>
  );
}

function ResidualCard({ residual }: { residual: ResidualReport }) {
  return (
    <section aria-label="residual risk" data-verdict={residual.verdict}>
      <h2>residual risk</h2>
      <p>
        <Badge tone="danger">{residual.verdict}</Badge>{" "}
        <Badge tone="neutral">anonymous: {String(residual.anonymous)}</Badge>{" "}
        <Badge tone="neutral">safe: {String(residual.safe)}</Badge>
      </p>
      <p role="note">{residual.advisory}</p>
      {residual.categories.length > 0 ? (
        <table className="data">
          <thead>
            <tr>
              <th scope="col">exposure</th>
              <th scope="col">count</th>
              <th scope="col">detail</th>
            </tr>
          </thead>
          <tbody>
            {residual.categories.map((c) => (
              <tr key={c.kind} data-category={c.kind}>
                <th scope="row">{c.kind}</th>
                <td>{c.count}</td>
                <td>
                  {c.detail ??
                    c.findings
                      ?.slice(0, 4)
                      .map((f) => `${f.ref ?? ""}${f.path ? ` ${f.path}` : ""}`.trim())
                      .join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {residual.flags.length > 0 ? (
        <>
          <h3>flagged content</h3>
          <table className="data">
            <thead>
              <tr>
                <th scope="col">record</th>
                <th scope="col">path</th>
                <th scope="col">pattern</th>
                <th scope="col">severity</th>
              </tr>
            </thead>
            <tbody>
              {residual.flags.map((f, i) => (
                <tr key={i} data-flag={f.pattern}>
                  <td>{f.ref}</td>
                  <td>
                    <code>{f.path}</code>
                  </td>
                  <td>{f.pattern}</td>
                  <td>
                    <Badge tone={severityTone(f.severity)}>{f.severity}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {residual.flaggedRecords.length > 0 ? (
            <p role="note">flagged records remain reviewable: {residual.flaggedRecords.join(", ")}</p>
          ) : null}
        </>
      ) : (
        <p role="note">no suspicious-content flags — this is not a safety certification.</p>
      )}
    </section>
  );
}

function RedactionCard({ redaction }: { redaction: RedactionReport }) {
  return (
    <section aria-label="redaction report">
      <h2>redaction report</h2>
      <table className="kv">
        <tbody>
          {Object.entries(redaction.removedFields).map(([kind, fields]) => (
            <tr key={kind}>
              <th scope="row">{kind} removed fields</th>
              <td>{fields.join(", ")}</td>
            </tr>
          ))}
          <tr>
            <th scope="row">merged duplicates</th>
            <td>{redaction.mergedDuplicates}</td>
          </tr>
          <tr>
            <th scope="row">aliased identifiers</th>
            <td>
              {redaction.aliasedIdentifiers.count} (
              {redaction.aliasedIdentifiers.kinds.join(", ") || "none"})
            </td>
          </tr>
        </tbody>
      </table>
      <p role="note">{redaction.aliasedIdentifiers.note}</p>
      {redaction.removedKeys.length > 0 ? (
        <table className="data">
          <thead>
            <tr>
              <th scope="col">record</th>
              <th scope="col">removed key</th>
              <th scope="col">reason</th>
            </tr>
          </thead>
          <tbody>
            {redaction.removedKeys.map((k, i) => (
              <tr key={i}>
                <td>{k.ref}</td>
                <td>
                  <code>{k.path}</code>
                </td>
                <td>{k.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {redaction.excludedEntries.length > 0 ? (
        <table className="data">
          <thead>
            <tr>
              <th scope="col">record</th>
              <th scope="col">kind</th>
              <th scope="col">excluded because</th>
            </tr>
          </thead>
          <tbody>
            {redaction.excludedEntries.map((e, i) => (
              <tr key={i}>
                <td>
                  <code>{e.recordId.slice(0, 8)}…</code>
                </td>
                <td>{e.recordKind}</td>
                <td>{e.reason ?? "unknown"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </section>
  );
}

function ManifestCard({ manifest }: { manifest: ExportManifest }) {
  return (
    <section aria-label="export manifest" data-egress={manifest.egress}>
      <h2>manifest — bound by approval digest</h2>
      <table className="kv">
        <tbody>
          <tr>
            <th scope="row">transformation version</th>
            <td>{manifest.transformationVersion}</td>
          </tr>
          <tr>
            <th scope="row">snapshot</th>
            <td>
              {manifest.snapshot.purpose} · {manifest.snapshot.digest.slice(0, 16)}…
            </td>
          </tr>
          <tr>
            <th scope="row">payload digest</th>
            <td>{manifest.payload.digest.slice(0, 16)}…</td>
          </tr>
          <tr>
            <th scope="row">recipient</th>
            <td>
              {manifest.recipient.provider ?? "undeclared"} /{" "}
              {manifest.recipient.account ?? "—"} / {manifest.recipient.region ?? "—"}
            </td>
          </tr>
          <tr>
            <th scope="row">permitted job</th>
            <td>
              {manifest.permittedJob.operation} ({manifest.permittedJob.runKind})
            </td>
          </tr>
          <tr>
            <th scope="row">limits</th>
            <td>
              ≤{manifest.limits.maxRecords} records · ≤{manifest.limits.maxBytes} bytes
            </td>
          </tr>
          <tr>
            <th scope="row">retention</th>
            <td>
              {manifest.retention.expectation ?? "undeclared"} · deletion:{" "}
              {manifest.retention.deletionExpectation ?? "undeclared"}
            </td>
          </tr>
          <tr>
            <th scope="row">expiry</th>
            <td>{manifest.expiry ?? "none"}</td>
          </tr>
          <tr>
            <th scope="row">environment</th>
            <td>
              container: {manifest.environment.containerDigest ?? "none configured"} · runtime{" "}
              {manifest.environment.runtime.transform}
            </td>
          </tr>
          <tr>
            <th scope="row">egress</th>
            <td>{manifest.egress}</td>
          </tr>
          <tr>
            <th scope="row">approver</th>
            <td>{manifest.approver ?? "none yet"}</td>
          </tr>
        </tbody>
      </table>
      <p role="note">
        An approval binds this exact manifest's bound digest. Changing the
        payload, transformation version, recipient, job, limits, or expiry
        invalidates any prior approval.
      </p>
    </section>
  );
}

function PrepareForm({
  view,
  onDone,
}: {
  view: ExportReviewView;
  onDone: (v: ExportReviewView, errors: ReadonlyArray<string>) => void;
}) {
  const [commit, pending] = useMutation<exportPrepareMutation>(ExportPrepareMutation);
  const [snapshotId, setSnapshotId] = useState(
    () => view.snapshots.find((s) => s.taskMatch)?.id ?? view.snapshots[0]?.id ?? "",
  );
  const [recipient, setRecipient] = useState("");
  const [account, setAccount] = useState("");
  const [region, setRegion] = useState("");
  const [expiry, setExpiry] = useState("");
  const [retention, setRetention] = useState("");
  const [deletion, setDeletion] = useState("");

  function submit() {
    if (!snapshotId) return;
    commit({
      variables: {
        input: {
          proposalId: view.proposal.gid,
          snapshotId,
          recipient: recipient || null,
          account: account || null,
          region: region || null,
          expiresAt: expiry || null,
          retentionExpectation: retention || null,
          deletionExpectation: deletion || null,
        },
      },
      onCompleted: (response) => {
        const result = response.exports?.prepare;
        if (!result) return;
        if (result.errors && result.errors.length > 0) {
          onDone(view, result.errors.map((e) => e?.message ?? "unknown error"));
          return;
        }
        onDone(result.view as unknown as ExportReviewView, []);
      },
      onError: (error) => onDone(view, [error.message]),
    });
  }

  return (
    <section aria-label="prepare payload">
      <h2>prepare minimal transformed payload</h2>
      {view.snapshots.length === 0 ? (
        <EmptyState title="No frozen dataset snapshots — freeze one before preparing an export payload." />
      ) : (
        <>
          <div className="cs-field">
            <label className="cs-field__label" htmlFor="export-snapshot">
              frozen snapshot
            </label>
            <select
              id="export-snapshot"
              className="cs-input"
              value={snapshotId}
              onChange={(e) => setSnapshotId(e.target.value)}
            >
              {view.snapshots.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} — {s.purpose}
                  {s.taskMatch ? " (this run's task)" : ""}
                </option>
              ))}
            </select>
          </div>
          <TextField
            label="recipient (declared label — not a credential)"
            value={recipient}
            onChange={(e) => setRecipient(e.target.value)}
          />
          <TextField
            label="account"
            value={account}
            onChange={(e) => setAccount(e.target.value)}
          />
          <TextField
            label="region"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
          />
          <TextField
            label="manifest expiry (ISO datetime, optional)"
            value={expiry}
            onChange={(e) => setExpiry(e.target.value)}
          />
          <TextField
            label="retention expectation"
            value={retention}
            onChange={(e) => setRetention(e.target.value)}
          />
          <TextField
            label="deletion expectation"
            value={deletion}
            onChange={(e) => setDeletion(e.target.value)}
          />
          <Button
            type="button"
            disabled={pending || !snapshotId}
            onClick={submit}
            aria-label="prepare export payload"
          >
            Review exact payload and residual risk
          </Button>
        </>
      )}
    </section>
  );
}

function ApprovalCard({
  view,
  onDone,
}: {
  view: ExportReviewView;
  onDone: (v: ExportReviewView, errors: ReadonlyArray<string>) => void;
}) {
  const [commitDecide, deciding] = useMutation<exportDecideMutation>(ExportDecideMutation);
  const [commitClass, classifying] = useMutation<exportSetClassificationMutation>(
    ExportSetClassificationMutation,
  );
  const [rationale, setRationale] = useState("");
  const [nextClass, setNextClass] = useState("");
  const approval = view.approval;
  const payload = view.payload;

  function decide(decision: "approved" | "rejected") {
    if (!payload) return;
    commitDecide({
      variables: {
        input: {
          payloadId: payload.gid,
          decision,
          rationale: rationale || null,
        },
      },
      onCompleted: (response) => {
        const result = response.exports?.decide;
        if (!result) return;
        if (result.errors && result.errors.length > 0) {
          onDone(view, result.errors.map((e) => e?.message ?? "unknown error"));
          return;
        }
        onDone(result.view as unknown as ExportReviewView, []);
      },
      onError: (error) => onDone(view, [error.message]),
    });
  }

  function reclassify() {
    if (!payload || !nextClass) return;
    commitClass({
      variables: {
        input: {
          payloadId: payload.gid,
          classification: nextClass,
          rationale: rationale || null,
        },
      },
      onCompleted: (response) => {
        const result = response.exports?.setClassification;
        if (!result) return;
        if (result.errors && result.errors.length > 0) {
          onDone(view, result.errors.map((e) => e?.message ?? "unknown error"));
          return;
        }
        onDone(result.view as unknown as ExportReviewView, []);
      },
      onError: (error) => onDone(view, [error.message]),
    });
  }

  return (
    <section aria-label="export approval" data-approval-state={approval.state}>
      <h2>approval</h2>
      <p>
        <Badge tone={approvalTone(approval.state)}>{approval.state}</Badge>{" "}
        {approval.expiresAt ? <span>expires {approval.expiresAt}</span> : null}
      </p>
      {approval.rationale ? <p role="note">rationale: {approval.rationale}</p> : null}
      {approval.state === "stale" ? (
        <p role="note">
          The bound inputs changed since the last approval — a fresh approval is
          required for this exact payload + transformation digest.
        </p>
      ) : null}
      {view.capabilities.canApprove && payload ? (
        <>
          <TextField
            label="rationale"
            hint="recorded on the approval/review; required for a classification change"
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
          />
          <Button
            type="button"
            disabled={deciding || approval.state === "approved"}
            onClick={() => decide("approved")}
            aria-label="approve export payload"
          >
            approve this exact payload
          </Button>{" "}
          <Button
            type="button"
            disabled={deciding || approval.state === "rejected"}
            onClick={() => decide("rejected")}
            aria-label="reject export payload"
          >
            reject
          </Button>
        </>
      ) : (
        <p role="note">
          Only a human holding {view.proposal.requiredCapability} may approve —
          agents can never hold it. Nothing transfers regardless.
        </p>
      )}
      {payload && view.capabilities.canReview && approval.state !== "approved" ? (
        <div className="cs-field">
          <label className="cs-field__label" htmlFor="export-reclassify">
            reviewed classification change
          </label>
          <select
            id="export-reclassify"
            className="cs-input"
            value={nextClass}
            onChange={(e) => setNextClass(e.target.value)}
          >
            <option value="">keep {payload.classification}</option>
            {["internal", "confidential", "restricted"]
              .filter((c) => c !== payload.classification)
              .map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
          </select>
          <Button
            type="button"
            disabled={classifying || !nextClass}
            onClick={reclassify}
            aria-label="record classification review"
          >
            record reviewed classification
          </Button>
        </div>
      ) : null}
    </section>
  );
}

export function ExportReviewPanel({ proposalId }: { proposalId: string }) {
  const data = useLazyLoadQuery<exportReviewQuery>(ExportReviewQuery, { proposalId });
  const [override, setOverride] = useState<ExportReviewView | null>(null);
  const [actionErrors, setActionErrors] = useState<ReadonlyArray<string>>([]);
  const queryView = data.exportReview as unknown as ExportReviewView;
  const view = override ?? queryView;

  function onDone(next: ExportReviewView, errors: ReadonlyArray<string>) {
    setActionErrors(errors);
    if (errors.length === 0) setOverride(next);
  }

  return (
    <div data-proposal-id={view.proposal.id}>
      <h1>export payload review</h1>
      {actionErrors.length > 0 ? <p role="alert">{actionErrors.join("; ")}</p> : null}
      <TradeoffBanner />
      <ProposalCard proposal={view.proposal} />
      <section aria-label="cloud capability" data-cloud-status={view.cloud.status}>
        <h2>cloud</h2>
        <p>
          <Badge tone={view.cloud.status === "not_configured" ? "neutral" : "warning"}>
            {view.cloud.status}
          </Badge>{" "}
          <span>egress: {view.egress}</span>
        </p>
        <p>{view.cloud.detail}</p>
      </section>
      {view.payload ? (
        <>
          <PayloadCard payload={view.payload} />
          {view.residual ? <ResidualCard residual={view.residual} /> : null}
          {view.redaction ? <RedactionCard redaction={view.redaction} /> : null}
          {view.manifest ? <ManifestCard manifest={view.manifest} /> : null}
        </>
      ) : (
        <EmptyState title="No transformed payload yet — prepare one for review below." />
      )}
      {view.capabilities.canReview ? (
        <>
          <PrepareForm view={view} onDone={onDone} />
          <ApprovalCard view={view} onDone={onDone} />
        </>
      ) : null}
      {view.alias ? (
        <p role="note" data-testid="alias-local">
          {view.alias.count} identifiers aliased via a LOCAL-only map (
          {view.alias.kinds.join(", ") || "none"}) — the map stays in the vault
          and never enters the payload.
        </p>
      ) : null}
    </div>
  );
}
