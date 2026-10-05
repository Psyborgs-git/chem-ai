import { Suspense, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../../components/atoms/Badge";
import { Button } from "../../../components/atoms/Button";
import { TextField } from "../../../components/atoms/TextField";
import { EmptyState, LoadingState } from "../../../components/states/states";
import {
  ModelReleaseApproveMutation,
  ModelReleaseConvertMutation,
  ModelReleasePromoteMutation,
  ModelReleaseRegisterMutation,
  ModelReleaseRollbackMutation,
  ModelReleasesQuery,
  ModelReleaseValidateMutation,
  ModelTrainingRunsQuery,
  ServingPointerQuery,
  SessionModelBindMutation,
  SessionModelPinsQuery,
} from "./operations";

import type { learningModelReleasesQuery } from "../../../__generated__/learningModelReleasesQuery.graphql";
import type { learningModelReleaseApproveMutation } from "../../../__generated__/learningModelReleaseApproveMutation.graphql";
import type { learningModelReleaseConvertMutation } from "../../../__generated__/learningModelReleaseConvertMutation.graphql";
import type { learningModelReleasePromoteMutation } from "../../../__generated__/learningModelReleasePromoteMutation.graphql";
import type { learningModelReleaseRegisterMutation } from "../../../__generated__/learningModelReleaseRegisterMutation.graphql";
import type { learningModelReleaseRollbackMutation } from "../../../__generated__/learningModelReleaseRollbackMutation.graphql";
import type { learningModelReleaseValidateMutation } from "../../../__generated__/learningModelReleaseValidateMutation.graphql";
import type { learningModelTrainingRunsQuery } from "../../../__generated__/learningModelTrainingRunsQuery.graphql";
import type { learningServingPointerQuery } from "../../../__generated__/learningServingPointerQuery.graphql";
import type { learningSessionModelBindMutation } from "../../../__generated__/learningSessionModelBindMutation.graphql";
import type { learningSessionModelPinsQuery } from "../../../__generated__/learningSessionModelPinsQuery.graphql";

type Release = learningModelReleasesQuery["response"]["modelReleases"][number];
type Validation = {
  status?: string;
  mode?: string;
  load_verified?: boolean;
  checks?: { name?: string; ok?: boolean; detail?: string }[];
};
type Capability = Record<string, unknown>;

const STATE_TONE: Record<string, "success" | "danger" | "warning" | "info" | "neutral"> = {
  promoted: "success",
  validated: "info",
  registered: "warning",
  superseded: "neutral",
  rejected: "danger",
  revoked: "danger",
};

function PointerCard({
  notice,
  setNotice,
  onChanged,
}: {
  notice: string | null;
  setNotice: (m: string) => void;
  onChanged: () => void;
}) {
  const data = useLazyLoadQuery<learningServingPointerQuery>(
    ServingPointerQuery,
    {},
    { fetchPolicy: "network-only" },
  );
  const [rollback, busy] = useMutation<learningModelReleaseRollbackMutation>(
    ModelReleaseRollbackMutation,
  );
  const pointer = data.servingPointer;
  return (
    <article aria-label="serving pointer">
      <header>
        <strong>serving pointer</strong>{" "}
        {pointer?.releaseId ? (
          <Badge tone="success">serving {String(pointer.releaseId).slice(-8)}</Badge>
        ) : (
          <Badge tone="warning">nothing served</Badge>
        )}{" "}
        {pointer && <Badge tone="neutral">revision {pointer.revision}</Badge>}{" "}
        {pointer?.reason && <Badge tone="info">{pointer.reason}</Badge>}
      </header>
      <div role="group" aria-label="pointer actions">
        <Button
          variant="secondary"
          disabled={busy || !pointer?.releaseId}
          onClick={() =>
            rollback({
              variables: { input: {} },
              onCompleted: (r) => {
                const err = r.learning.modelReleaseRollback.errors[0];
                setNotice(err ? `${err.code}: ${err.message}` : "rolled back to known-good release");
                if (!err) onChanged();
              },
            })
          }
        >
          rollback to previous release
        </Button>
      </div>
      {notice && <p role="status">{notice}</p>}
    </article>
  );
}

function useReleaseActions(
  release: Release,
  setNotice: (m: string) => void,
  onChanged: () => void,
) {
  const [validate, validating] = useMutation<learningModelReleaseValidateMutation>(
    ModelReleaseValidateMutation,
  );
  const [convert, converting] = useMutation<learningModelReleaseConvertMutation>(
    ModelReleaseConvertMutation,
  );
  const [approve, approving] = useMutation<learningModelReleaseApproveMutation>(
    ModelReleaseApproveMutation,
  );
  const [promote, promoting] = useMutation<learningModelReleasePromoteMutation>(
    ModelReleasePromoteMutation,
  );
  const id = { modelReleaseId: release.id };
  const report = (
    errors: readonly { code: string; message: string }[] | null | undefined,
    ok: string,
  ) => {
    const err = errors?.[0];
    setNotice(err ? `${err.code}: ${err.message}` : ok);
    if (!err) onChanged();
  };
  return {
    busy: validating || converting || approving || promoting,
    actions: {
      validate: () =>
        validate({
          variables: { input: id },
          onCompleted: (r) =>
            report(r.learning.modelReleaseValidate.errors, "validation re-run recorded"),
        }),
      convert: () =>
        convert({
          variables: { input: id },
          onCompleted: (r) =>
            report(r.learning.modelReleaseConvert.errors, "serving bundle derived + parity-checked"),
        }),
      approve: () =>
        approve({
          variables: { input: id },
          onCompleted: (r) =>
            report(r.learning.modelReleaseApprove.errors, "release approval granted"),
        }),
      promote: () =>
        promote({
          variables: { input: id },
          onCompleted: (r) =>
            report(r.learning.modelReleasePromote.errors, "pointer moved atomically"),
        }),
    },
  };
}

function ReleaseCard({
  release,
  notice,
  setNotice,
  onChanged,
}: {
  release: Release;
  notice: string | null;
  setNotice: (m: string) => void;
  onChanged: () => void;
}) {
  const { actions, busy } = useReleaseActions(release, setNotice, onChanged);
  const capability = (release.capability ?? {}) as Capability;
  const validation = (release.validation ?? {}) as Validation;
  const conversions = (release.conversions ?? []) as {
    format?: string;
    checksum?: string;
    parity?: { ok?: boolean; mode?: string };
  }[];
  const failedChecks = (validation.checks ?? []).filter((c) => c.ok === false);
  return (
    <article>
      <header>
        <strong>{release.name}</strong>{" "}
        <Badge tone={STATE_TONE[release.state] ?? "neutral"}>{release.state}</Badge>{" "}
        <Badge tone="neutral">{release.servingFormat}</Badge>{" "}
        {release.trainingRunId && (
          <Badge tone="info">run {(release.trainingRunId ?? "").slice(0, 8)}…</Badge>
        )}
      </header>
      <p>
        base <code>{release.baseModelId}</code> ({release.architecture},{" "}
        {release.baseSha256.slice(0, 12)}…) · tokenizer {release.tokenizerKind} (
        {release.tokenizerSha256.slice(0, 12)}…) · adapter {release.adapterMethod} (
        {release.adapterSha256.slice(0, 12)}…)
      </p>
      <p>
        {(capability["baseModel"] as string) ?? "base model unknown"} · engine{" "}
        {(capability["engineCapability"] as string) ?? "unknown"} · data{" "}
        {(capability["dataStatus"] as string) ?? "unknown"} ·{" "}
        {(capability["scientificStatus"] as string) ?? "not_validated"} ·{" "}
        {(capability["confidentiality"] as string) ?? "vault-scoped"}
      </p>
      {validation.status && (
        <p>
          validation:{" "}
          <Badge tone={validation.status === "compatible" ? "success" : "danger"}>
            {validation.status}
          </Badge>{" "}
          <Badge tone="neutral">mode {validation.mode}</Badge>{" "}
          {validation.load_verified ? (
            <Badge tone="success">load verified</Badge>
          ) : (
            <Badge tone="warning">load not verified</Badge>
          )}
          {failedChecks.length > 0 && (
            <code> failed: {failedChecks.map((c) => c.name).join(", ")}</code>
          )}
        </p>
      )}
      {conversions.length > 0 && (
        <p>
          conversions:{" "}
          {conversions.map((c, i) => (
            <Badge key={i} tone={c.parity?.ok ? "success" : "warning"}>
              {c.format} {(c.checksum ?? "").slice(0, 8)}… parity{" "}
              {c.parity?.ok ? "ok" : "unverified"}
            </Badge>
          ))}
        </p>
      )}
      <div role="group" aria-label="release actions">
        <Button variant="secondary" onClick={actions.validate} disabled={busy}>
          re-validate
        </Button>
        <Button variant="secondary" onClick={actions.convert} disabled={busy}>
          derive serving bundle
        </Button>
        <Button variant="secondary" onClick={actions.approve} disabled={busy}>
          grant release approval
        </Button>
        {(release.state === "validated" || release.state === "superseded") && (
          <Button variant="primary" onClick={actions.promote} disabled={busy}>
            promote to serving
          </Button>
        )}
      </div>
      {notice && <p role="status">{notice}</p>}
    </article>
  );
}

function PinList({
  taskId,
  notice,
  setNotice,
}: {
  taskId: string | null;
  notice: string | null;
  setNotice: (m: string) => void;
}) {
  const data = useLazyLoadQuery<learningSessionModelPinsQuery>(
    SessionModelPinsQuery,
    { taskId },
    { fetchPolicy: "network-only" },
  );
  const [bind, binding] = useMutation<learningSessionModelBindMutation>(
    SessionModelBindMutation,
  );
  const pins = data.sessionModelPins;
  return (
    <div>
      <p role="note">
        sessions pin the release they began with — pointer moves never
        re-anchor an open session (AT-0802-2). a serving request validates
        compatibility first; a mismatched adapter/base pair is rejected.
      </p>
      {pins.length === 0 ? (
        <p role="note">no sessions recorded for this task yet.</p>
      ) : (
        <ul>
          {pins.map((p) => (
            <li key={p.sessionId}>
              session <code>{String(p.sessionId).slice(-8)}</code>{" "}
              {p.releaseId ? (
                <Badge tone="info">pinned {String(p.releaseId).slice(-8)}</Badge>
              ) : (
                <Badge tone="warning">unpinned at start</Badge>
              )}{" "}
              <Button
                variant="secondary"
                disabled={binding}
                onClick={() =>
                  bind({
                    variables: { input: { sessionId: p.sessionId } },
                    onCompleted: (r) => {
                      const res = r.learning.sessionModelBind;
                      const err = res.errors[0];
                      setNotice(
                        err
                          ? `${String(p.sessionId).slice(-8)}: ${err.code}: ${err.message}`
                          : `${String(p.sessionId).slice(-8)}: bound to ${res.modelRelease?.name}`,
                      );
                    },
                  })
                }
              >
                serving bind
              </Button>
            </li>
          ))}
        </ul>
      )}
      {notice && <p role="status">{notice}</p>}
    </div>
  );
}

function ReleaseList({
  taskId,
  notices,
  setNotice,
  onChanged,
}: {
  taskId: string | null;
  notices: Record<string, string>;
  setNotice: (key: string, m: string) => void;
  onChanged: () => void;
}) {
  const data = useLazyLoadQuery<learningModelReleasesQuery>(
    ModelReleasesQuery,
    { taskId },
    { fetchPolicy: "network-only" },
  );
  if (data.modelReleases.length === 0) {
    return <EmptyState title="No model releases registered yet." />;
  }
  return (
    <>
      {data.modelReleases.map((r) => (
        <ReleaseCard
          key={r.id}
          release={r}
          notice={notices[r.id] ?? null}
          setNotice={(m) => setNotice(r.id, m)}
          onChanged={onChanged}
        />
      ))}
    </>
  );
}

function RunPicker({
  taskId,
  onPick,
}: {
  taskId: string | null;
  onPick: (id: string) => void;
}) {
  const data = useLazyLoadQuery<learningModelTrainingRunsQuery>(
    ModelTrainingRunsQuery,
    { taskId },
    { fetchPolicy: "network-only" },
  );
  const registrable = data.trainingRuns.filter(
    (r) => !["draft", "blocked", "failed", "cancelled"].includes(r.state),
  );
  if (registrable.length === 0) {
    return (
      <p role="note">
        no training run with persisted artifacts — complete a run in the
        training section first.
      </p>
    );
  }
  return (
    <label>
      training run{" "}
      <select defaultValue="" onChange={(e) => onPick(e.target.value)} required>
        <option value="" disabled>
          pick one…
        </option>
        {registrable.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name} — {r.state}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Model registry panel (§17.5/§18.4, CS-0802): registry list, the
 * atomic serving pointer, per-session pins — honest capability labels;
 * fixture-only data is never scientific validation. */
export function ModelsPanel({ taskId }: { taskId: string | null }) {
  const [register, registering] = useMutation<learningModelReleaseRegisterMutation>(
    ModelReleaseRegisterMutation,
  );
  const [name, setName] = useState("");
  const [runId, setRunId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [notices, setNotices] = useState<Record<string, string>>({});
  const setNotice = (key: string, m: string) =>
    setNotices((n) => ({ ...n, [key]: m }));

  const doRegister = () =>
    register({
      variables: { input: { trainingRunId: runId, name, taskId: taskId ?? null } },
      onCompleted: (r) => {
        const err = r.learning.modelReleaseRegister.errors[0];
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
        registered releases carry full lineage — dataset snapshot →
        training run → adapter → release — plus the adapter's recorded
        base binding. compatibility is structural and enforced on every
        serving request; a mismatched pair is rejected, not warned.
        fixture-only data is never scientific validation.
      </p>
      <Suspense fallback={<LoadingState label="loading serving pointer…" />}>
        <PointerCard
          key={`p${refreshKey}`}
          notice={notices["pointer"] ?? null}
          setNotice={(m) => setNotice("pointer", m)}
          onChanged={() => setRefreshKey((k) => k + 1)}
        />
      </Suspense>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          doRegister();
        }}
      >
        <TextField
          label="release name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <Suspense fallback={<LoadingState label="loading training runs…" />}>
          <RunPicker taskId={taskId} onPick={setRunId} />
        </Suspense>
        <Button
          variant="primary"
          type="submit"
          disabled={registering || !name || !runId}
        >
          {registering ? "registering…" : "register release"}
        </Button>
      </form>
      {error && (
        <p role="alert">
          <Badge tone="danger">{error}</Badge>
        </p>
      )}
      <Suspense fallback={<LoadingState label="loading model releases…" />}>
        <ReleaseList
          key={refreshKey}
          taskId={taskId}
          notices={notices}
          setNotice={setNotice}
          onChanged={() => setRefreshKey((k) => k + 1)}
        />
      </Suspense>
      <h4>session pins</h4>
      <Suspense fallback={<LoadingState label="loading session pins…" />}>
        <PinList
          key={`s${refreshKey}`}
          taskId={taskId}
          notice={notices["pins"] ?? null}
          setNotice={(m) => setNotice("pins", m)}
        />
      </Suspense>
    </div>
  );
}
