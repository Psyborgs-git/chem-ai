/** Extraction review (CS-0302, §9.2): side-by-side source/proposed
 * view — locator + original text on the left, parser payload +
 * ambiguity flags on the right. Nothing is accepted automatically;
 * every accept/reject/promote is an explicit reviewer action. */
import { Suspense, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import {
  Badge,
  Button,
  EmptyState,
  LoadingState,
  SourceCitation,
} from "../../components";
import type { importsBatchesQuery } from "../../__generated__/importsBatchesQuery.graphql";
import type { importsRecordsQuery } from "../../__generated__/importsRecordsQuery.graphql";
import type { importsArtifactImportMutation } from "../../__generated__/importsArtifactImportMutation.graphql";
import type { importsRecordReviewMutation } from "../../__generated__/importsRecordReviewMutation.graphql";
import type { importsRecordPromoteMutation } from "../../__generated__/importsRecordPromoteMutation.graphql";
import {
  ArtifactImportMutation,
  ImportBatchesQuery,
  ImportRecordsQuery,
  RecordPromoteMutation,
  RecordReviewMutation,
} from "./operations";

function locatorText(locator: unknown): string {
  if (locator && typeof locator === "object") {
    const l = locator as Record<string, unknown>;
    if (l.sheet && l.cell) return `${String(l.sheet)}!${String(l.cell)}`;
    if (l.page) return `page ${String(l.page)}`;
    if (l.jsonpath) return String(l.jsonpath);
    if (l.row !== undefined && l.col !== undefined)
      return `row ${String(l.row)}, col ${String(l.col)}`;
    if (l.paragraph !== undefined) return `paragraph ${String(l.paragraph)}`;
    return JSON.stringify(locator);
  }
  return "—";
}

const FLAG_LABELS: Record<string, string> = {
  percent_literal_ambiguous: "percent literal — verify basis",
  percent_format_ambiguous: "percent format — verify basis",
  missing_cached_value: "no cached value",
  untrusted_formula: "untrusted formula (not evaluated)",
  cached_formula_result: "cached formula result",
  decimal_separator_ambiguous: "decimal separator ambiguous",
  locale_date_ambiguous: "locale date ambiguous",
  unit_unresolved: "unit unresolved",
};

function ImportTrigger({ onDone }: { onDone: () => void }) {
  const [artifactId, setArtifactId] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [commit, inFlight] =
    useMutation<importsArtifactImportMutation>(ArtifactImportMutation);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        commit({
          variables: { input: { artifactId } },
          onCompleted: (res) => {
            const errs = res.imports.artifactImport.errors;
            if (errs.length > 0) {
              setMessage(errs.map((x) => x.message).join("; "));
            } else {
              const b = res.imports.artifactImport.batch;
              setMessage(
                b
                  ? `batch ${b.status} · ${b.recordCount} records${
                      res.imports.artifactImport.deduplicated
                        ? " · deduplicated"
                        : ""
                    }`
                  : "no batch returned",
              );
              onDone();
            }
          },
          onError: (err) => setMessage(err.message),
        });
      }}
    >
      <label>
        artifact id{" "}
        <input
          value={artifactId}
          onChange={(e) => setArtifactId(e.target.value)}
          required
        />
      </label>
      <Button type="submit" disabled={inFlight}>
        run quarantined import
      </Button>
      {message && <p role="status">{message}</p>}
    </form>
  );
}

function RecordRow({
  record,
}: {
  record: importsRecordsQuery["response"]["importRecords"]["edges"][number]["node"];
}) {
  const [review, reviewInFlight] =
    useMutation<importsRecordReviewMutation>(RecordReviewMutation);
  const [promote, promoteInFlight] =
    useMutation<importsRecordPromoteMutation>(RecordPromoteMutation);
  const [claimId, setClaimId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busy = reviewInFlight || promoteInFlight;

  return (
    <tr data-record-id={record.id} data-status={record.status}>
      <td>
        {/* AT-0302-3: the citation is the exact source locator */}
        <SourceCitation
          sourceId={record.id}
          title={locatorText(record.locator)}
          kind="import"
        />
      </td>
      <td>
        <code>{record.originalText}</code>
      </td>
      <td>
        <code>{record.payload ? JSON.stringify(record.payload) : "—"}</code>
      </td>
      <td>
        {record.flags.length === 0
          ? "—"
          : record.flags.map((f) => (
              <Badge key={f} tone="warning">
                {FLAG_LABELS[f] ?? f}
              </Badge>
            ))}
      </td>
      <td>
        <Badge
          tone={
            record.status === "accepted"
              ? "success"
              : record.status === "rejected"
                ? "danger"
                : "neutral"
          }
        >
          {record.status}
        </Badge>
      </td>
      <td>
        {record.status === "proposed" && (
          <>
            <Button
              disabled={busy}
              onClick={() =>
                review({
                  variables: {
                    input: { recordId: record.id, decision: "accepted" },
                  },
                  onError: (e) => setError(e.message),
                })
              }
            >
              accept
            </Button>{" "}
            <Button
              disabled={busy}
              onClick={() =>
                review({
                  variables: {
                    input: { recordId: record.id, decision: "rejected" },
                  },
                  onError: (e) => setError(e.message),
                })
              }
            >
              reject
            </Button>{" "}
            <Button
              disabled={busy}
              onClick={() =>
                promote({
                  variables: {
                    input: {
                      recordId: record.id,
                      subject: { source: "import", locator: record.locator },
                      statement: {
                        original: record.originalText,
                        payload: record.payload,
                      },
                    },
                  },
                  onCompleted: (res) => {
                    const c = res.imports.recordPromote.claim;
                    setClaimId(c ? c.id : "error");
                  },
                  onError: (e) => setError(e.message),
                })
              }
            >
              promote to claim
            </Button>
          </>
        )}
        {claimId && (
          <p role="status">
            proposed claim created (status: proposed — review in Evidence)
          </p>
        )}
        {error && <p role="alert">{error}</p>}
      </td>
    </tr>
  );
}

function RecordsTable({ batchId }: { batchId: string }) {
  const data = useLazyLoadQuery<importsRecordsQuery>(ImportRecordsQuery, {
    batchId,
  });
  const records = data.importRecords.edges.map((e) => e.node);
  if (records.length === 0) {
    return <EmptyState title="No extracted records in this batch." />;
  }
  return (
    <table className="cs-table">
      <thead>
        <tr>
          <th>source locator</th>
          <th>original text</th>
          <th>proposed value</th>
          <th>ambiguity</th>
          <th>status</th>
          <th>actions</th>
        </tr>
      </thead>
      <tbody>
        {records.map((r) => (
          <RecordRow key={r.id} record={r} />
        ))}
      </tbody>
    </table>
  );
}

function BatchList() {
  const data = useLazyLoadQuery<importsBatchesQuery>(ImportBatchesQuery, {});
  const batches = data.importBatches.edges.map((e) => e.node);
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <div>
      {batches.length === 0 ? (
        <EmptyState title="No import batches yet." />
      ) : (
        <ul>
          {batches.map((b) => (
            <li key={b.id}>
              <button
                type="button"
                onClick={() => setSelected(b.id)}
                aria-pressed={selected === b.id}
              >
                {b.originalName} · rev {b.sourceRevision} · {b.status} ·{" "}
                {b.recordCount} records
              </button>
              {(b.findings as { code?: string }[]).map((f, i) => (
                <Badge key={i} tone="warning">
                  {f.code}
                </Badge>
              ))}
            </li>
          ))}
        </ul>
      )}
      {selected && <RecordsTable batchId={selected} />}
    </div>
  );
}

export function ImportReview() {
  const [reloadKey, setReloadKey] = useState(0);
  return (
    <div>
      <h1>Extraction review</h1>
      <p>
        Imported fields are proposals — ambiguity stays visible and
        nothing is accepted automatically.
      </p>
      <ImportTrigger onDone={() => setReloadKey((k) => k + 1)} />
      <Suspense fallback={<LoadingState label="loading batches…" />}>
        <BatchList key={reloadKey} />
      </Suspense>
    </div>
  );
}
