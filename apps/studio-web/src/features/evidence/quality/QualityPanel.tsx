import { Suspense, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../../components/atoms/Badge";
import { Button } from "../../../components/atoms/Button";
import { TextField } from "../../../components/atoms/TextField";
import { EmptyState, LoadingState } from "../../../components/states/states";
import {
  QualityReportQuery,
  SourceRevokeMutation,
} from "./operations";

import type { qualityQualityReportQuery } from "../../../__generated__/qualityQualityReportQuery.graphql";
import type { qualitySourceRevokeMutation } from "../../../__generated__/qualitySourceRevokeMutation.graphql";

type Report = {
  received?: number;
  parsed?: number;
  quarantined?: number;
  failed?: number;
  records_proposed?: number;
  records_accepted?: number;
  records_rejected?: number;
  duplicates?: number;
  missing_units?: number;
  ambiguous_percent?: number;
  rights_unknown_artifacts?: number;
  training_excluded?: number;
  flags?: Record<string, number>;
  coverage?: {
    byProductFamily?: Record<string, number>;
    byMetric?: Record<string, number>;
    byMethod?: Record<string, number>;
    byEvidenceType?: Record<string, number>;
  };
  outcomes?: {
    byCategory?: Record<string, { count: number; kinds: Record<string, number>; labels: string[] }>;
    byKind?: Record<string, number>;
  };
};

function Matrix({ title, cells }: { title: string; cells?: Record<string, number> }) {
  const entries = Object.entries(cells ?? {});
  return (
    <div>
      <h4>{title}</h4>
      {entries.length === 0 ? (
        <small>no data</small>
      ) : (
        <ul>
          {entries.map(([k, v]) => (
            <li key={k}>
              {k}: <strong>{v}</strong>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** §9.3 data-quality report: counts, flag taxonomy, a coverage
 * matrix by family/metric/method/evidence-type, and outcome
 * categories with original labels — deliberately no single
 * "quality score". */
function Report({ report }: { report: Report }) {
  const counts: Array<[string, number | undefined]> = [
    ["received", report.received],
    ["parsed", report.parsed],
    ["quarantined", report.quarantined],
    ["failed", report.failed],
    ["records proposed", report.records_proposed],
    ["records accepted", report.records_accepted],
    ["records rejected", report.records_rejected],
    ["superseded duplicates", report.duplicates],
    ["missing units", report.missing_units],
    ["ambiguous percent", report.ambiguous_percent],
    ["rights unknown", report.rights_unknown_artifacts],
    ["training excluded", report.training_excluded],
  ];
  return (
    <div>
      <h4>counts</h4>
      <ul aria-label="import counts">
        {counts
          .filter(([, v]) => v !== undefined)
          .map(([k, v]) => (
            <li key={k}>
              {k}: <strong>{v}</strong>
            </li>
          ))}
      </ul>

      <h4>flag taxonomy</h4>
      {Object.keys(report.flags ?? {}).length === 0 ? (
        <EmptyState title="No flags recorded." />
      ) : (
        <ul>
          {Object.entries(report.flags ?? {}).map(([f, n]) => (
            <li key={f}>
              {f}: <strong>{n}</strong>
            </li>
          ))}
        </ul>
      )}

      <h4>coverage matrix</h4>
      <Matrix title="by product family" cells={report.coverage?.byProductFamily} />
      <Matrix title="by metric" cells={report.coverage?.byMetric} />
      <Matrix title="by method" cells={report.coverage?.byMethod} />
      <Matrix title="by evidence type" cells={report.coverage?.byEvidenceType} />

      <h4>outcome categories</h4>
      {Object.keys(report.outcomes?.byCategory ?? {}).length === 0 ? (
        <EmptyState title="No outcomes recorded yet." />
      ) : (
        <ul>
          {Object.entries(report.outcomes?.byCategory ?? {}).map(([cat, bucket]) => (
            <li key={cat}>
              <Badge tone="info">{cat}</Badge> <strong>{bucket.count}</strong> —{" "}
              {bucket.labels.join("; ")}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function QualityInner() {
  const [fetchKey, setFetchKey] = useState(0);
  const data = useLazyLoadQuery<qualityQualityReportQuery>(QualityReportQuery, {}, {
    fetchKey,
    fetchPolicy: "network-only",
  });
  const [revoke, revoking] = useMutation<qualitySourceRevokeMutation>(SourceRevokeMutation);
  const [artifactId, setArtifactId] = useState("");
  const [reason, setReason] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [impact, setImpact] = useState<Record<string, unknown> | null>(null);

  return (
    <div>
      <Report report={data.dataQualityReport as Report} />

      <h4>revoke a source</h4>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setFeedback(null);
          revoke({
            variables: { input: { artifactId, reason } },
            onCompleted: (r) => {
              const res = r.imports.sourceRevoke;
              if (res.errors.length) {
                setFeedback(`not revoked: ${res.errors[0].message}`);
                setImpact(null);
              } else {
                setFeedback(`revoked — revocation ${res.revocationId}`);
                setImpact(res.report as Record<string, unknown>);
                setFetchKey((k) => k + 1);
              }
            },
            onError: (e) => setFeedback(`not revoked: ${e.message}`),
          });
        }}
      >
        <TextField
          label="artifact id"
          value={artifactId}
          onChange={(e) => setArtifactId(e.target.value)}
        />
        <TextField
          label="revocation reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <Button type="submit" disabled={revoking}>
          revoke source
        </Button>
      </form>
      {feedback && <p role="status">{feedback}</p>}
      {impact && (
        <div role="note" aria-label="revocation impact">
          <h4>impact</h4>
          <ul>
            <li>chunks revoked: {String(impact.chunksRevoked)}</li>
            <li>claims superseded: {(impact.claimsSuperseded as string[])?.length ?? 0}</li>
            <li>
              derived artifacts flagged:{" "}
              {(impact.affectedDerivedIds as string[])?.length ?? 0}
            </li>
            <li>model releases affected: {(impact.affectedModelReleaseIds as string[])?.length ?? 0}</li>
            <li>unlearning guarantee: {String(impact.unlearningGuarantee)}</li>
          </ul>
        </div>
      )}
    </div>
  );
}

export function QualityPanel() {
  return (
    <Suspense fallback={<LoadingState label="loading quality report…" />}>
      <QualityInner />
    </Suspense>
  );
}
