import { Suspense, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../../components/atoms/Badge";
import { Button } from "../../../components/atoms/Button";
import { TextField } from "../../../components/atoms/TextField";
import { EmptyState, LoadingState } from "../../../components/states/states";
import {
  TrainingRunApproveMutation,
  TrainingRunCancelMutation,
  TrainingRunCreateMutation,
  TrainingRunExecuteMutation,
  TrainingRunQueueMutation,
  TrainingRunResumeMutation,
  TrainingRunSubmitMutation,
  TrainingRunTransitionMutation,
  TrainingRunsQuery,
  TrainingSnapshotsQuery,
} from "./operations";

import type { learningTrainingRunsQuery } from "../../../__generated__/learningTrainingRunsQuery.graphql";
import type { learningTrainingSnapshotsQuery } from "../../../__generated__/learningTrainingSnapshotsQuery.graphql";
import type { learningTrainingRunCreateMutation } from "../../../__generated__/learningTrainingRunCreateMutation.graphql";
import type { learningTrainingRunSubmitMutation } from "../../../__generated__/learningTrainingRunSubmitMutation.graphql";
import type { learningTrainingRunApproveMutation } from "../../../__generated__/learningTrainingRunApproveMutation.graphql";
import type { learningTrainingRunQueueMutation } from "../../../__generated__/learningTrainingRunQueueMutation.graphql";
import type { learningTrainingRunExecuteMutation } from "../../../__generated__/learningTrainingRunExecuteMutation.graphql";
import type { learningTrainingRunCancelMutation } from "../../../__generated__/learningTrainingRunCancelMutation.graphql";
import type { learningTrainingRunResumeMutation } from "../../../__generated__/learningTrainingRunResumeMutation.graphql";
import type { learningTrainingRunTransitionMutation } from "../../../__generated__/learningTrainingRunTransitionMutation.graphql";

type TrainingRun =
  learningTrainingRunsQuery["response"]["trainingRuns"][number];

type Manifest = {
  exampleCount?: number;
  partitions?: Record<string, number>;
  exclusions?: { exampleId?: string; reason?: string; detail?: string | null }[];
  excludedCount?: number;
  scientificStatus?: string;
};
type Telemetry = {
  stepsCompleted?: number;
  trainExamples?: number;
  evalExamples?: number;
  finalTrainLoss?: number | null;
  finalEvalLoss?: number | null;
  tail?: { event?: string; step?: number; loss?: number; evalLoss?: number }[];
};
type Checkpoint = { step?: number; sha256?: string };
type Resume = {
  fromStep?: number;
  checkpoint?: { step?: number; sha256?: string };
  sourceRunId?: string;
  sourceAttemptId?: string;
  resumedAt?: string;
};
type Capability = Record<string, unknown>;
type RunError = { code?: string; message?: string; detail?: { problems?: Record<string, unknown> } };

const STATE_TONE: Record<string, "success" | "danger" | "warning" | "info" | "neutral"> = {
  completed: "success",
  candidate_release: "info",
  promoted: "info",
  rejected: "danger",
  failed: "danger",
  blocked: "danger",
  cancelled: "warning",
  awaiting_approval: "warning",
  queued: "info",
  running: "info",
  evaluating: "info",
};

const next = {
  dataset_validated: "submit",
  awaiting_approval: "approve + queue",
  queued: "execute",
  cancelled: "resume",
  failed: "resume",
  completed: "evaluating",
  evaluating: "candidate_release",
} as Record<string, string>;

function useRunActions(run: TrainingRun, onChanged: () => void) {
  const [submit, submitting] = useMutation<learningTrainingRunSubmitMutation>(
    TrainingRunSubmitMutation,
  );
  const [approve, approving] = useMutation<learningTrainingRunApproveMutation>(
    TrainingRunApproveMutation,
  );
  const [queue, queuing] = useMutation<learningTrainingRunQueueMutation>(
    TrainingRunQueueMutation,
  );
  const [execute, executing] = useMutation<learningTrainingRunExecuteMutation>(
    TrainingRunExecuteMutation,
  );
  const [cancel, cancelling] = useMutation<learningTrainingRunCancelMutation>(
    TrainingRunCancelMutation,
  );
  const [resume, resuming] = useMutation<learningTrainingRunResumeMutation>(
    TrainingRunResumeMutation,
  );
  const [transition, transitioning] =
    useMutation<learningTrainingRunTransitionMutation>(
      TrainingRunTransitionMutation,
    );
  const [message, setMessage] = useState<string | null>(null);
  const id = { trainingRunId: run.id };

  const report = (
    errors: readonly { code: string; message: string }[] | null | undefined,
    ok: string,
  ) => {
    const err = errors?.[0];
    setMessage(err ? `${err.code}: ${err.message}` : ok);
    if (!err) onChanged();
  };

  return {
    message,
    busy:
      submitting || approving || queuing || executing || cancelling || resuming || transitioning,
    actions: {
      submit: () =>
        submit({
          variables: { input: id },
          onCompleted: (r) =>
            report(r.learning.trainingRunSubmit.errors, "submitted for approval"),
        }),
      approve: () =>
        approve({
          variables: { input: { ...id, decision: "approved" } },
          onCompleted: (r) =>
            report(r.learning.trainingRunApprove.errors, "approval bound to this spec + dataset"),
        }),
      reject: () =>
        approve({
          variables: { input: { ...id, decision: "rejected" } },
          onCompleted: (r) =>
            report(r.learning.trainingRunApprove.errors, "run rejected"),
        }),
      queue: () =>
        queue({
          variables: { input: id },
          onCompleted: (r) =>
            report(r.learning.trainingRunQueue.errors, "queued — eligibility gate passed"),
        }),
      execute: () =>
        execute({
          variables: { input: { ...id, attemptId: run.attemptId ?? "" } },
          onCompleted: (r) =>
            report(r.learning.trainingRunExecute.errors, "execution finished"),
        }),
      cancel: () =>
        cancel({
          variables: { input: id },
          onCompleted: (r) =>
            report(r.learning.trainingRunCancel.errors, "cancelled"),
        }),
      resume: () =>
        resume({
          variables: { input: id },
          onCompleted: (r) =>
            report(r.learning.trainingRunResume.errors, "resumed from latest checkpoint"),
        }),
      transition: (to: string) =>
        transition({
          variables: { input: { ...id, toState: to } },
          onCompleted: (r) =>
            report(r.learning.trainingRunTransition.errors, `moved to ${to}`),
        }),
    },
  };
}

function RunCard({ run, onChanged }: { run: TrainingRun; onChanged: () => void }) {
  const { actions, busy, message } = useRunActions(run, onChanged);
  const manifest = (run.datasetManifest ?? {}) as Manifest;
  const telemetry = (run.telemetry ?? {}) as Telemetry;
  const capability = (run.capability ?? {}) as Capability;
  const checkpoints = (run.checkpoints ?? []) as Checkpoint[];
  const resumeFrom = run.resumeFrom as Resume | null;
  const error = run.error as RunError | null;
  const problems = error?.detail?.problems;

  return (
    <article>
      <header>
        <strong>{run.name}</strong>{" "}
        <Badge tone={STATE_TONE[run.state] ?? "neutral"}>{run.state}</Badge>{" "}
        <Badge tone="neutral">spec {(run.specDigest ?? "").slice(0, 12)}…</Badge>{" "}
        <Badge tone="neutral">
          dataset {(run.datasetDigest ?? "").slice(0, 12)}…
        </Badge>
      </header>

      <p>
        {(capability["baseModel"] as string) ?? "base model unknown"} ·{" "}
        engine {(capability["engineCapability"] as string) ?? "unknown"} · data{" "}
        {(capability["dataStatus"] as string) ?? "unknown"} ·{" "}
        {(capability["scientificStatus"] as string) ?? "not_validated"}
      </p>

      {manifest.exampleCount != null && (
        <p>
          dataset: {manifest.exampleCount} examples · partitions{" "}
          {Object.entries(manifest.partitions ?? {})
            .map(([k, v]) => `${k}:${v}`)
            .join(" ")}
          {" · "}
          {manifest.excludedCount ?? 0} exclusions recorded
        </p>
      )}
      {(manifest.exclusions?.length ?? 0) > 0 && (
        <details>
          <summary>exclusions ({manifest.exclusions?.length})</summary>
          <ul>
            {manifest.exclusions!.map((e, i) => (
              <li key={i}>
                <Badge tone="warning">{e.reason}</Badge>{" "}
                <code>{(e.exampleId ?? "").slice(0, 10)}…</code> {e.detail ?? ""}
              </li>
            ))}
          </ul>
        </details>
      )}

      {telemetry.stepsCompleted != null && (
        <p>
          telemetry: {telemetry.stepsCompleted} steps ·{" "}
          {telemetry.trainExamples ?? 0} train / {telemetry.evalExamples ?? 0} eval
          examples · train loss {telemetry.finalTrainLoss ?? "?"} · eval loss{" "}
          {telemetry.finalEvalLoss ?? "?"}
          {telemetry.tail?.length ? (
            <>
              {" "}
              · last:{" "}
              <code>{JSON.stringify(telemetry.tail[telemetry.tail.length - 1])}</code>
            </>
          ) : null}
        </p>
      )}
      {checkpoints.length > 0 && (
        <p>
          checkpoints:{" "}
          {checkpoints.map((c) => `step ${c.step ?? "?"} (${(c.sha256 ?? "").slice(0, 8)}…)`).join(", ")}
        </p>
      )}
      {resumeFrom && (
        <p>
          <Badge tone="info">
            resumed from step {resumeFrom.fromStep ?? "?"} · checkpoint{" "}
            {(resumeFrom.checkpoint?.sha256 ?? "").slice(0, 8)}… · source run{" "}
            {(resumeFrom.sourceRunId ?? "").slice(0, 8)}…
          </Badge>
        </p>
      )}
      {error && (
        <p role="alert">
          <Badge tone="danger">
            {error.code}: {error.message}
          </Badge>
          {problems && <code> {JSON.stringify(problems)}</code>}
        </p>
      )}

      <div role="group" aria-label="run actions">
        {run.state === "dataset_validated" && (
          <Button variant="primary" onClick={actions.submit} disabled={busy}>
            submit for approval
          </Button>
        )}
        {run.state === "awaiting_approval" && (
          <>
            <Button variant="primary" onClick={actions.approve} disabled={busy}>
              approve
            </Button>
            <Button variant="secondary" onClick={actions.reject} disabled={busy}>
              reject
            </Button>
            <Button variant="secondary" onClick={actions.queue} disabled={busy}>
              queue
            </Button>
          </>
        )}
        {run.state === "queued" && (
          <>
            <Button
              variant="primary"
              onClick={actions.execute}
              disabled={busy || !run.attemptId}
            >
              execute
            </Button>
            <Button variant="secondary" onClick={actions.cancel} disabled={busy}>
              cancel
            </Button>
          </>
        )}
        {run.state === "running" && (
          <Button variant="secondary" onClick={actions.cancel} disabled={busy}>
            cancel
          </Button>
        )}
        {(run.state === "cancelled" || run.state === "failed") && (
          <Button variant="primary" onClick={actions.resume} disabled={busy}>
            resume from checkpoint
          </Button>
        )}
        {run.state === "completed" && (
          <Button
            variant="secondary"
            onClick={() => actions.transition("evaluating")}
            disabled={busy}
          >
            mark evaluating
          </Button>
        )}
        {run.state === "evaluating" && (
          <>
            <Button
              variant="secondary"
              onClick={() => actions.transition("candidate_release")}
              disabled={busy}
            >
              mark candidate_release
            </Button>
            <Button
              variant="secondary"
              onClick={() => actions.transition("rejected")}
              disabled={busy}
            >
              reject
            </Button>
          </>
        )}
        {run.state === "candidate_release" && (
          <Button
            variant="secondary"
            onClick={() => actions.transition("rejected")}
            disabled={busy}
          >
            reject
          </Button>
        )}
        {next[run.state] && (
          <Badge tone="neutral">next: {next[run.state]}</Badge>
        )}
      </div>
      {message && <p role="status">{message}</p>}
    </article>
  );
}

function SnapshotPicker({
  taskId,
  onPick,
}: {
  taskId: string | null;
  onPick: (id: string) => void;
}) {
  const data = useLazyLoadQuery<learningTrainingSnapshotsQuery>(
    TrainingSnapshotsQuery,
    { taskId },
    { fetchPolicy: "network-only" },
  );
  const frozen = data.datasetSnapshots.filter(
    (s) => s.state === "frozen" && s.purpose === "assistant_sft",
  );
  if (frozen.length === 0) {
    return (
      <p role="note">
        no frozen assistant_sft snapshot — build + freeze one in the datasets
        section first.
      </p>
    );
  }
  return (
    <label>
      frozen snapshot{" "}
      <select defaultValue="" onChange={(e) => onPick(e.target.value)} required>
        <option value="" disabled>
          pick one…
        </option>
        {frozen.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name} — {s.digest.slice(0, 12)}…
          </option>
        ))}
      </select>
    </label>
  );
}

function RunList({
  taskId,
  onChanged,
}: {
  taskId: string | null;
  onChanged: () => void;
}) {
  const data = useLazyLoadQuery<learningTrainingRunsQuery>(
    TrainingRunsQuery,
    { taskId },
    { fetchPolicy: "network-only" },
  );
  if (data.trainingRuns.length === 0) {
    return <EmptyState title="No training runs yet." />;
  }
  return (
    <>
      {data.trainingRuns.map((r) => (
        <RunCard key={r.id} run={r} onChanged={onChanged} />
      ))}
    </>
  );
}

/** Training runs panel (§17.5, CS-0801): lifecycle, manifest review,
 * telemetry — honest capability labels throughout; `completed` means
 * artifacts exist, never deployable. */
export function TrainingPanel({ taskId }: { taskId: string | null }) {
  const [create, creating] = useMutation<learningTrainingRunCreateMutation>(
    TrainingRunCreateMutation,
  );
  const [name, setName] = useState("");
  const [snapshotId, setSnapshotId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const doCreate = () =>
    create({
      variables: {
        input: { snapshotId, name, taskId: taskId ?? null },
      },
      onCompleted: (r) => {
        const err = r.learning.trainingRunCreate.errors[0];
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
        local SFT runs train a pico-GPT fixture base with LoRA inside an
        isolated container — dataset manifests, approvals, eligibility gates
        and resume provenance are first-class. fixture-only data is never
        scientific validation; <code>completed</code> artifacts exist but are
        not deployable — promotion stays gated behind CS-0803 evaluation.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          doCreate();
        }}
      >
        <TextField
          label="run name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <Suspense fallback={<LoadingState label="loading snapshots…" />}>
          <SnapshotPicker taskId={taskId} onPick={setSnapshotId} />
        </Suspense>
        <Button
          variant="primary"
          type="submit"
          disabled={creating || !name || !snapshotId}
        >
          {creating ? "validating…" : "create training run"}
        </Button>
      </form>
      {error && (
        <p role="alert">
          <Badge tone="danger">{error}</Badge>
        </p>
      )}
      <Suspense fallback={<LoadingState label="loading training runs…" />}>
        <RunList
          key={refreshKey}
          taskId={taskId}
          onChanged={() => setRefreshKey((k) => k + 1)}
        />
      </Suspense>
    </div>
  );
}
