import { Suspense, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../../components/atoms/Badge";
import { Button } from "../../../components/atoms/Button";
import { TextField } from "../../../components/atoms/TextField";
import { EmptyState, LoadingState } from "../../../components/states/states";
import {
  DatasetPrepareRunMutation,
  DatasetSnapshotBuildMutation,
  DatasetSnapshotDriftQuery,
  DatasetSnapshotFreezeMutation,
  DatasetSnapshotsQuery,
} from "./operations";

import type { learningDatasetsQuery } from "../../../__generated__/learningDatasetsQuery.graphql";
import type { learningDatasetDriftQuery } from "../../../__generated__/learningDatasetDriftQuery.graphql";
import type { learningDatasetBuildMutation } from "../../../__generated__/learningDatasetBuildMutation.graphql";
import type { learningDatasetFreezeMutation } from "../../../__generated__/learningDatasetFreezeMutation.graphql";
import type { learningDatasetPrepareMutation } from "../../../__generated__/learningDatasetPrepareMutation.graphql";

type Entry = {
  recordId?: string;
  recordKind?: string;
  sourceClass?: string;
  rightsTraining?: string;
  labelKind?: string;
  metric?: string | null;
  semantics?: Record<string, unknown>;
  excluded?: boolean;
  exclusionReason?: string | null;
};
type Manifest = { entries?: Entry[] };
type DriftReport = { drift?: boolean; changed?: string[]; missing?: string[] };
type PrepareReport = {
  ok?: boolean;
  reason?: string;
  entryIds?: string[];
};

const PURPOSES = [
  "property_prediction",
  "extraction_correction",
  "assistant_sft",
  "preference_pairs",
  "rl_tasks",
] as const;

const RIGHTS_TONE: Record<string, "success" | "danger" | "warning" | "neutral"> = {
  owned: "success",
  allowed: "success",
  unknown: "warning",
  denied: "danger",
};

function DriftResult({ snapshotId }: { snapshotId: string }) {
  const data = useLazyLoadQuery<learningDatasetDriftQuery>(
    DatasetSnapshotDriftQuery,
    { snapshotId },
    { fetchPolicy: "network-only" },
  );
  const drift = (data.datasetSnapshotDrift ?? {}) as DriftReport;
  return drift.drift ? (
    <Badge tone="danger">
      drift detected — {drift.changed?.length ?? 0} changed,{" "}
      {drift.missing?.length ?? 0} missing; snapshot unchanged
    </Badge>
  ) : (
    <Badge tone="success">no drift — sources unchanged</Badge>
  );
}

function DriftCheck({ snapshotId }: { snapshotId: string }) {
  const [check, setCheck] = useState(false);
  return (
    <span>
      <Button variant="secondary" onClick={() => setCheck(true)}>
        check drift
      </Button>
      {check && (
        <Suspense fallback={<LoadingState label="checking…" />}>
          <DriftResult snapshotId={snapshotId} />
        </Suspense>
      )}
    </span>
  );
}

function SnapshotCard({
  snap,
  onChanged,
}: {
  snap: NonNullable<learningDatasetsQuery["response"]["datasetSnapshots"][number]>;
  onChanged: () => void;
}) {
  const [freeze, freezing] = useMutation<learningDatasetFreezeMutation>(
    DatasetSnapshotFreezeMutation,
  );
  const [prepare, preparing] = useMutation<learningDatasetPrepareMutation>(
    DatasetPrepareRunMutation,
  );
  const [message, setMessage] = useState<string | null>(null);
  const entries = ((snap.manifest as Manifest) ?? {}).entries ?? [];
  const excluded = entries.filter((e) => e.excluded);

  const doFreeze = () =>
    freeze({
      variables: { input: { snapshotId: snap.id } },
      onCompleted: (r) => {
        const err = r.learning.snapshotFreeze.errors[0];
        if (err) {
          const ids =
            (err.safeDetails as { recordIds?: string[] } | null)?.recordIds ?? [];
          setMessage(
            `${err.code}: ${err.message}${ids.length ? ` — records: ${ids.join(", ")}` : ""}`,
          );
        } else {
          setMessage(null);
          onChanged();
        }
      },
    });

  const doPrepare = () =>
    prepare({
      variables: { input: { snapshotId: snap.id } },
      onCompleted: (r) => {
        const err = r.learning.snapshotPrepareRun.errors[0];
        if (err) {
          setMessage(`${err.code}: ${err.message}`);
          return;
        }
        const rep = r.learning.snapshotPrepareRun.report as PrepareReport | null;
        setMessage(
          rep?.ok
            ? `run prepared — ${rep.entryIds?.length ?? 0} eligible records at digest ${snap.digest.slice(0, 12)}…`
            : `preparation blocked: ${rep?.reason ?? "unknown"} — snapshot stays immutable`,
        );
      },
    });

  return (
    <article>
      <header>
        <strong>{snap.name}</strong> <Badge tone="info">{snap.purpose}</Badge>{" "}
        <Badge tone={snap.state === "frozen" ? "success" : "neutral"}>
          {snap.state}
        </Badge>{" "}
        <Badge tone="neutral">digest {snap.digest.slice(0, 12)}…</Badge>
        {snap.frozenAt && (
          <Badge tone="neutral">
            frozen {new Date(snap.frozenAt).toLocaleString()}
          </Badge>
        )}
      </header>
      <p>
        {entries.length} records · {excluded.length} excluded · fixture-only —
        not scientific validation
      </p>
      {entries.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>record</th>
              <th>kind</th>
              <th>source class</th>
              <th>label</th>
              <th>training rights</th>
              <th>semantics</th>
              <th>status</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.recordId}>
                <td>
                  <code>{e.recordId?.slice(0, 8)}…</code>
                </td>
                <td>{e.recordKind}</td>
                <td>
                  <Badge tone="info">{e.sourceClass}</Badge>
                </td>
                <td>{e.labelKind}</td>
                <td>
                  <Badge tone={RIGHTS_TONE[e.rightsTraining ?? ""] ?? "neutral"}>
                    {e.rightsTraining}
                  </Badge>
                </td>
                <td>
                  <code>{JSON.stringify(e.semantics ?? {})}</code>
                </td>
                <td>
                  {e.excluded ? (
                    <Badge tone="warning">excluded: {e.exclusionReason}</Badge>
                  ) : (
                    <Badge tone="success">included</Badge>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div role="group" aria-label="snapshot actions">
        {snap.state === "draft" && (
          <Button variant="primary" onClick={doFreeze} disabled={freezing}>
            {freezing ? "freezing…" : "freeze snapshot"}
          </Button>
        )}
        {snap.state === "frozen" && (
          <>
            <DriftCheck snapshotId={snap.id} />
            <Button variant="secondary" onClick={doPrepare} disabled={preparing}>
              {preparing ? "checking…" : "prepare run"}
            </Button>
          </>
        )}
      </div>
      {message && <p role="status">{message}</p>}
    </article>
  );
}

function SnapshotList({
  taskId,
  onChanged,
}: {
  taskId: string | null;
  onChanged: () => void;
}) {
  const data = useLazyLoadQuery<learningDatasetsQuery>(
    DatasetSnapshotsQuery,
    { taskId },
    { fetchPolicy: "network-only" },
  );
  if (data.datasetSnapshots.length === 0) {
    return <EmptyState title="No dataset snapshots yet." />;
  }
  return (
    <>
      {data.datasetSnapshots.map((s) => (
        <SnapshotCard key={s.id} snap={s} onChanged={onChanged} />
      ))}
    </>
  );
}

/** Dataset snapshots panel (§17.2, CS-0601). */
export function DatasetsPanel({ taskId }: { taskId: string | null }) {
  const [build, building] = useMutation<learningDatasetBuildMutation>(
    DatasetSnapshotBuildMutation,
  );
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState<string>(PURPOSES[0]);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const doBuild = () =>
    build({
      variables: { input: { purpose, name, taskId: taskId ?? null } },
      onCompleted: (r) => {
        const err = r.learning.snapshotBuild.errors[0];
        setError(err ? `${err.code}: ${err.message}` : null);
        if (!err) {
          setName("");
          setRefreshKey((k) => k + 1);
        }
      },
    });

  return (
    <div>
      <p>
        dataset snapshots are immutable manifests: record ids, hashes, source
        classes, rights and exclusion semantics. Freezing is a governance
        action; records with unresolved training rights block the freeze.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          doBuild();
        }}
      >
        <TextField
          label="snapshot name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <label>
          purpose{" "}
          <select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
            {PURPOSES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <Button variant="primary" type="submit" disabled={building || !name}>
          {building ? "building…" : "build snapshot"}
        </Button>
      </form>
      {error && (
        <p role="alert">
          <Badge tone="danger">{error}</Badge>
        </p>
      )}
      <Suspense fallback={<LoadingState label="loading datasets…" />}>
        <SnapshotList
          key={refreshKey}
          taskId={taskId}
          onChanged={() => setRefreshKey((k) => k + 1)}
        />
      </Suspense>
    </div>
  );
}
