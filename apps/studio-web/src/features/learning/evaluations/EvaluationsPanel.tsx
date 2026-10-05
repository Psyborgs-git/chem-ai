import { Suspense, useState } from "react";
import { useLazyLoadQuery, useMutation } from "react-relay";

import { Badge } from "../../../components/atoms/Badge";
import { Button } from "../../../components/atoms/Button";
import { TextField } from "../../../components/atoms/TextField";
import { EmptyState, LoadingState } from "../../../components/states/states";
import {
  EvaluationReleasesQuery,
  EvaluationRunStartMutation,
  EvaluationRunsQuery,
  EvaluationSuiteCreateMutation,
  EvaluationSuiteFreezeMutation,
  EvaluationSuiteLabelsMutation,
  EvaluationSuitesQuery,
  PromotionApproveMutation,
  PromotionDecideMutation,
  PromotionDecisionQuery,
  PromotionPromoteMutation,
} from "./operations";

import type { learningEvaluationReleasesQuery } from "../../../__generated__/learningEvaluationReleasesQuery.graphql";
import type { learningEvaluationRunsQuery } from "../../../__generated__/learningEvaluationRunsQuery.graphql";
import type { learningEvaluationRunStartMutation } from "../../../__generated__/learningEvaluationRunStartMutation.graphql";
import type { learningEvaluationSuiteCreateMutation } from "../../../__generated__/learningEvaluationSuiteCreateMutation.graphql";
import type { learningEvaluationSuiteFreezeMutation } from "../../../__generated__/learningEvaluationSuiteFreezeMutation.graphql";
import type { learningEvaluationSuiteLabelsMutation } from "../../../__generated__/learningEvaluationSuiteLabelsMutation.graphql";
import type { learningEvaluationSuitesQuery } from "../../../__generated__/learningEvaluationSuitesQuery.graphql";
import type { learningPromotionApproveMutation } from "../../../__generated__/learningPromotionApproveMutation.graphql";
import type { learningPromotionDecideMutation } from "../../../__generated__/learningPromotionDecideMutation.graphql";
import type { learningPromotionDecisionQuery } from "../../../__generated__/learningPromotionDecisionQuery.graphql";
import type { learningPromotionPromoteMutation } from "../../../__generated__/learningPromotionPromoteMutation.graphql";

type Suite = learningEvaluationSuitesQuery["response"]["evaluationSuites"][number];
type EvalRun = learningEvaluationRunsQuery["response"]["evaluationRuns"][number];
type Release = learningEvaluationReleasesQuery["response"]["modelReleases"][number];
type Blocker = { kind?: string; severity?: string; detail?: string };
type MetricRow = {
  metric?: string;
  baseline?: number | null;
  candidate?: number | null;
  delta?: number | null;
  evaluated?: number;
};
type Comparison = {
  verdict?: string;
  aggregate?: { baseline?: number | null; candidate?: number | null; delta?: number | null };
  metrics?: MetricRow[];
  denominators?: {
    expected?: Record<string, number>;
    evaluated?: Record<string, number>;
    small_sample?: boolean;
  };
  subgroups?: { subgroup?: string; evaluated?: number; baseline?: number | null; candidate?: number | null; small_sample?: boolean }[];
  thresholds?: { metric?: string; direction?: string; value?: number | null; observed?: number | null; status?: string }[];
  safety_regression?: { new_failures?: string[]; candidate_failures?: string[] };
  tool_diff?: { pinned?: string[]; missingNow?: string[]; addedNow?: string[] };
};

const VERDICT_TONE: Record<string, "success" | "danger" | "warning" | "info" | "neutral"> = {
  improved: "success",
  regressed: "danger",
  flat: "warning",
  incomplete: "neutral",
};

const fmt = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : Number(v).toFixed(3);

function ComparisonTable({ comparison }: { comparison: Comparison }) {
  const denom = comparison.denominators ?? {};
  return (
    <div>
      <p>
        verdict{" "}
        <Badge tone={VERDICT_TONE[comparison.verdict ?? ""] ?? "neutral"}>
          {comparison.verdict ?? "unknown"}
        </Badge>{" "}
        candidate {fmt(comparison.aggregate?.candidate)} vs baseline{" "}
        {fmt(comparison.aggregate?.baseline)} (Δ {fmt(comparison.aggregate?.delta)}){" "}
        {denom.small_sample ? <Badge tone="warning">small sample</Badge> : null}
      </p>
      <table>
        <thead>
          <tr>
            <th>metric</th>
            <th>baseline</th>
            <th>candidate</th>
            <th>Δ</th>
            <th>n</th>
          </tr>
        </thead>
        <tbody>
          {(comparison.metrics ?? []).map((m) => (
            <tr key={m.metric}>
              <td>{m.metric}</td>
              <td>{fmt(m.baseline)}</td>
              <td>{fmt(m.candidate)}</td>
              <td>{fmt(m.delta)}</td>
              <td>{m.evaluated ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p role="note">
        denominators — expected {denom.expected?.candidate ?? 0}, evaluated{" "}
        {denom.evaluated?.candidate ?? 0}
        {(comparison.subgroups ?? []).length > 0 && (
          <>
            {" "}
            · subgroups:{" "}
            {(comparison.subgroups ?? []).map((s) => (
              <Badge key={s.subgroup} tone={s.small_sample ? "warning" : "neutral"}>
                {s.subgroup}: {fmt(s.candidate)} vs {fmt(s.baseline)} (n={s.evaluated})
              </Badge>
            ))}
          </>
        )}
      </p>
      {(comparison.thresholds ?? []).length > 0 && (
        <p>
          thresholds:{" "}
          {(comparison.thresholds ?? []).map((t) => (
            <Badge
              key={t.metric}
              tone={
                t.status === "pass" ? "success" : t.status === "fail" ? "danger" : "warning"
              }
            >
              {t.metric} {t.status}
              {t.value === null || t.value === undefined ? " (unknown)" : ""}
            </Badge>
          ))}
        </p>
      )}
      {((comparison.safety_regression?.new_failures ?? []).length > 0 ||
        (comparison.safety_regression?.candidate_failures ?? []).length > 0) && (
        <p>
          safety/privacy:{" "}
          {(comparison.safety_regression?.new_failures ?? []).map((f) => (
            <Badge key={f} tone="danger">
              new failure {f}
            </Badge>
          ))}
          {(comparison.safety_regression?.candidate_failures ?? [])
            .filter((f) => !(comparison.safety_regression?.new_failures ?? []).includes(f))
            .map((f) => (
              <Badge key={f} tone="warning">
                candidate failure {f}
              </Badge>
            ))}
        </p>
      )}
    </div>
  );
}

function BlockerList({ blockers }: { blockers: readonly Blocker[] }) {
  if (blockers.length === 0) {
    return <p role="note">no blockers recorded.</p>;
  }
  return (
    <ul>
      {blockers.map((b, i) => (
        <li key={i}>
          <Badge tone={b.severity === "hard" ? "danger" : "warning"}>
            {b.severity ?? "?"} {b.kind}
          </Badge>{" "}
          {b.detail}
        </li>
      ))}
    </ul>
  );
}

function RunCard({ run }: { run: EvalRun }) {
  const comparison = (run.comparison ?? {}) as Comparison;
  const contamination = (run.contamination ?? {}) as {
    contaminated?: boolean;
    findings?: string[];
    checked?: boolean;
  };
  const capability = (run.capability ?? {}) as Record<string, unknown>;
  return (
    <article>
      <header>
        <strong>run {String(run.id).slice(-8)}</strong>{" "}
        <Badge tone={run.state === "completed" ? "success" : run.state === "failed" ? "danger" : "info"}>
          {run.state}
        </Badge>{" "}
        <Badge tone="neutral">release {run.modelReleaseId.slice(0, 8)}…</Badge>{" "}
        {run.baselineReleaseId && (
          <Badge tone="neutral">vs release {run.baselineReleaseId.slice(0, 8)}…</Badge>
        )}{" "}
        <Badge tone="info">suite {run.suiteDigest.slice(0, 10)}…</Badge>
      </header>
      <p role="note">
        data {(capability["dataStatus"] as string) ?? "fixture_only"} ·{" "}
        {(capability["scientificStatus"] as string) ?? "not_validated"} · labels{" "}
        {(capability["labelAccess"] as string) ?? "service principal only"}
      </p>
      {run.error && (
        <p role="alert">
          <Badge tone="danger">{JSON.stringify(run.error)}</Badge>
        </p>
      )}
      {run.state === "completed" && <ComparisonTable comparison={comparison} />}
      {contamination.checked && (
        <p>
          contamination check:{" "}
          <Badge tone={contamination.contaminated ? "danger" : "success"}>
            {contamination.contaminated ? "findings" : "clean"}
          </Badge>
          {(contamination.findings ?? []).map((f, i) => (
            <code key={i}> {f}</code>
          ))}
        </p>
      )}
      <BlockerList blockers={(run.blockers ?? []) as Blocker[]} />
    </article>
  );
}

function PromotionCard({
  release,
  setNotice,
  onChanged,
}: {
  release: Release;
  setNotice: (key: string, m: string) => void;
  onChanged: () => void;
}) {
  const data = useLazyLoadQuery<learningPromotionDecisionQuery>(
    PromotionDecisionQuery,
    { modelReleaseId: release.id },
    { fetchPolicy: "network-only" },
  );
  const [decide, deciding] = useMutation<learningPromotionDecideMutation>(
    PromotionDecideMutation,
  );
  const [approve, approving] = useMutation<learningPromotionApproveMutation>(
    PromotionApproveMutation,
  );
  const [promote, promoting] = useMutation<learningPromotionPromoteMutation>(
    PromotionPromoteMutation,
  );
  const [scope, setScope] = useState("");
  const [limitations, setLimitations] = useState("");
  const busy = deciding || approving || promoting;
  const decision = data.promotionDecision;
  const card = (decision?.modelCard ?? {}) as {
    claims?: { blanketImprovedChemistry?: string; scopedImprovement?: string };
    limitations?: string[];
    scope?: string | null;
    evaluatedAgainst?: { verdict?: string | null; suiteName?: string | null };
  };
  const limitationList = limitations
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  const report = (
    errors: readonly { code: string; message: string }[] | null | undefined,
    ok: string,
  ) => {
    const err = errors?.[0];
    setNotice(release.id, err ? `${err.code}: ${err.message}` : ok);
    if (!err) onChanged();
  };
  return (
    <article>
      <header>
        <strong>{release.name}</strong>{" "}
        <Badge tone={release.state === "promoted" ? "success" : "neutral"}>
          {release.state}
        </Badge>{" "}
        {decision ? (
          <Badge tone={decision.eligible ? "success" : "danger"}>
            gate {decision.eligible ? "eligible" : "blocked"}
          </Badge>
        ) : (
          <Badge tone="neutral">no decision</Badge>
        )}
        {decision?.approvalId && <Badge tone="info">scoped approval bound</Badge>}
      </header>
      {decision && (
        <>
          <p role="note">
            verdict {card.evaluatedAgainst?.verdict ?? "—"} · claims — blanket
            improved-chemistry{" "}
            <Badge tone="danger">
              {card.claims?.blanketImprovedChemistry ?? "not_permitted"}
            </Badge>{" "}
            scoped improvement{" "}
            <Badge
              tone={card.claims?.scopedImprovement === "permitted" ? "success" : "warning"}
            >
              {card.claims?.scopedImprovement ?? "not_permitted"}
            </Badge>
          </p>
          <BlockerList blockers={(decision.blockers ?? []) as Blocker[]} />
          {(card.limitations ?? []).length > 0 && (
            <p role="note">limitations: {(card.limitations ?? []).join(" · ")}</p>
          )}
        </>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          promote({
            variables: {
              input: {
                modelReleaseId: release.id,
                scope,
                limitations: limitationList,
              },
            },
            onCompleted: (r) => report(r.learning.promotionPromote.errors, "promoted"),
          });
        }}
      >
        <TextField
          label="release scope (documented experimental role)"
          value={scope}
          onChange={(e) => setScope(e.target.value)}
          required
        />
        <TextField
          label="limitations (one per line)"
          value={limitations}
          onChange={(e) => setLimitations(e.target.value)}
        />
        <div role="group" aria-label="promotion actions">
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() =>
              decide({
                variables: { input: { modelReleaseId: release.id } },
                onCompleted: (r) =>
                  report(r.learning.promotionDecide.errors, "gate decision recorded"),
              })
            }
          >
            run gate decision
          </Button>
          <Button
            variant="secondary"
            disabled={busy || !scope}
            onClick={() =>
              approve({
                variables: {
                  input: {
                    modelReleaseId: release.id,
                    scope,
                    limitations: limitationList,
                  },
                },
                onCompleted: (r) =>
                  report(
                    r.learning.promotionApprove.errors,
                    "scoped release approval granted",
                  ),
              })
            }
          >
            approve scoped release
          </Button>
          <Button variant="primary" type="submit" disabled={busy || !scope}>
            promote (gated)
          </Button>
        </div>
      </form>
    </article>
  );
}

function PromotionSurface({ taskId }: { taskId: string | null }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const [notices, setNotices] = useState<Record<string, string>>({});
  const setNotice = (key: string, m: string) =>
    setNotices((n) => ({ ...n, [key]: m }));
  const data = useLazyLoadQuery<learningEvaluationReleasesQuery>(
    EvaluationReleasesQuery,
    { taskId },
    { fetchPolicy: "network-only" },
  );
  const candidates = data.modelReleases.filter(
    (r) => r.state === "validated" || r.state === "promoted" || r.state === "superseded",
  );
  return (
    <section>
      <h4>promotion decision surface</h4>
      <p role="note">
        the gate requires a completed final-kind matched comparison — held-out
        flat-or-worse fails regardless of training loss. unknown acceptance
        thresholds are stored blockers; a release serves only through a
        documented scoped approval. no release may carry a blanket
        improved-chemistry claim.
      </p>
      {candidates.length === 0 ? (
        <EmptyState title="No promotable releases — validate a release in the models section first." />
      ) : (
        candidates.map((r) => (
          <Suspense key={`${r.id}-${refreshKey}`} fallback={<LoadingState label="loading decision…" />}>
            <PromotionCard
              release={r}
              setNotice={setNotice}
              onChanged={() => setRefreshKey((k) => k + 1)}
            />
          </Suspense>
        ))
      )}
      {Object.entries(notices).map(([k, m]) => (
        <p key={k} role="status">
          {m}
        </p>
      ))}
    </section>
  );
}

function SuiteCard({
  suite,
  releases,
  setNotice,
  onChanged,
}: {
  suite: Suite;
  releases: readonly Release[];
  setNotice: (key: string, m: string) => void;
  onChanged: () => void;
}) {
  const [labels, labelling] = useMutation<learningEvaluationSuiteLabelsMutation>(
    EvaluationSuiteLabelsMutation,
  );
  const [freeze, freezing] = useMutation<learningEvaluationSuiteFreezeMutation>(
    EvaluationSuiteFreezeMutation,
  );
  const [startRun, starting] = useMutation<learningEvaluationRunStartMutation>(
    EvaluationRunStartMutation,
  );
  const [labelsJson, setLabelsJson] = useState("");
  const [releaseId, setReleaseId] = useState("");
  const [baselineId, setBaselineId] = useState("");
  const definition = (suite.definition ?? {}) as {
    tasks?: { example_id?: string; kind?: string }[];
    thresholds?: { metric?: string; value?: number | null }[];
  };
  const busy = labelling || freezing || starting;
  const report = (
    errors: readonly { code: string; message: string }[] | null | undefined,
    ok: string,
  ) => {
    const err = errors?.[0];
    setNotice(suite.id, err ? `${err.code}: ${err.message}` : ok);
    if (!err) onChanged();
  };
  const submitLabels = () => {
    try {
      const parsed = JSON.parse(labelsJson) as unknown;
      if (!Array.isArray(parsed)) throw new Error("labels must be a JSON array");
      labels({
        variables: { input: { evaluationSuiteId: suite.id, labels: parsed } },
        onCompleted: (r) =>
          report(r.learning.evaluationSuiteLabels.errors, "hidden labels attached"),
      });
    } catch (e) {
      setNotice(suite.id, `invalid labels JSON: ${(e as Error).message}`);
    }
  };
  return (
    <article>
      <header>
        <strong>
          {suite.name} v{suite.version}
        </strong>{" "}
        <Badge tone={suite.state === "frozen" ? "success" : "warning"}>{suite.state}</Badge>{" "}
        <Badge tone={suite.kind === "final" ? "info" : "neutral"}>{suite.kind}</Badge>{" "}
        <Badge tone="neutral">{definition.tasks?.length ?? 0} tasks</Badge>
      </header>
      <p role="note">
        digest {suite.digest.slice(0, 16)}… · labels hidden behind the evaluation
        service principal — the suite definition carries hashes only · data
        fixture_only · not scientific validation
      </p>
      {(definition.thresholds ?? []).length > 0 && (
        <p>
          thresholds:{" "}
          {(definition.thresholds ?? []).map((t, i) => (
            <Badge key={i} tone={t.value === null || t.value === undefined ? "warning" : "info"}>
              {t.metric} {t.value === null || t.value === undefined ? "unknown" : t.value}
            </Badge>
          ))}
        </p>
      )}
      {suite.state === "draft" && (
        <div role="group" aria-label="draft suite actions">
          <label>
            hidden labels (JSON array of targets){" "}
            <textarea
              rows={3}
              value={labelsJson}
              onChange={(e) => setLabelsJson(e.target.value)}
              placeholder='[{"example_id":"ex1","expect":"exact","value":"42"}]'
            />
          </label>
          <Button variant="secondary" disabled={busy || !labelsJson} onClick={submitLabels}>
            attach labels
          </Button>
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() =>
              freeze({
                variables: { input: { evaluationSuiteId: suite.id } },
                onCompleted: (r) =>
                  report(
                    r.learning.evaluationSuiteFreeze.errors,
                    "suite frozen — tool catalog pinned",
                  ),
              })
            }
          >
            freeze suite
          </Button>
        </div>
      )}
      {suite.state === "frozen" && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            startRun({
              variables: {
                input: {
                  evaluationSuiteId: suite.id,
                  modelReleaseId: releaseId,
                  baselineReleaseId: baselineId || null,
                },
              },
              onCompleted: (r) =>
                report(
                  r.learning.evaluationRunStart.errors,
                  "matched comparison completed",
                ),
            });
          }}
        >
          <label>
            candidate release{" "}
            <select
              defaultValue=""
              onChange={(e) => setReleaseId(e.target.value)}
              required
            >
              <option value="" disabled>
                pick one…
              </option>
              {releases.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} — {r.state}
                </option>
              ))}
            </select>
          </label>{" "}
          <label>
            baseline (empty = unmodified base){" "}
            <select defaultValue="" onChange={(e) => setBaselineId(e.target.value)}>
              <option value="">unmodified base</option>
              {releases.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} — {r.state}
                </option>
              ))}
            </select>
          </label>{" "}
          <Button variant="primary" type="submit" disabled={busy || !releaseId}>
            run matched comparison
          </Button>
        </form>
      )}
    </article>
  );
}

function SuiteList({
  taskId,
  setNotice,
  onChanged,
}: {
  taskId: string | null;
  setNotice: (key: string, m: string) => void;
  onChanged: () => void;
}) {
  const suites = useLazyLoadQuery<learningEvaluationSuitesQuery>(
    EvaluationSuitesQuery,
    { taskId },
    { fetchPolicy: "network-only" },
  );
  const releases = useLazyLoadQuery<learningEvaluationReleasesQuery>(
    EvaluationReleasesQuery,
    { taskId },
    { fetchPolicy: "network-only" },
  );
  if (suites.evaluationSuites.length === 0) {
    return <EmptyState title="No evaluation suites registered yet." />;
  }
  return (
    <>
      {suites.evaluationSuites.map((s) => (
        <SuiteCard
          key={s.id}
          suite={s}
          releases={releases.modelReleases}
          setNotice={setNotice}
          onChanged={onChanged}
        />
      ))}
    </>
  );
}

function RunList({ taskId }: { taskId: string | null }) {
  const data = useLazyLoadQuery<learningEvaluationRunsQuery>(
    EvaluationRunsQuery,
    {},
    { fetchPolicy: "network-only" },
  );
  void taskId;
  if (data.evaluationRuns.length === 0) {
    return <EmptyState title="No evaluation runs yet." />;
  }
  return (
    <>
      {data.evaluationRuns.map((r) => (
        <RunCard key={r.id} run={r} />
      ))}
    </>
  );
}

/** Evaluation + promotion panel (§18, CS-0803): versioned suites,
 * hidden-label access control, matched base-vs-adapted comparisons,
 * and the gated promotion decision surface — honest capability labels. */
export function EvaluationsPanel({ taskId }: { taskId: string | null }) {
  const [create, creating] = useMutation<learningEvaluationSuiteCreateMutation>(
    EvaluationSuiteCreateMutation,
  );
  const [name, setName] = useState("");
  const [kind, setKind] = useState("development");
  const [tasksJson, setTasksJson] = useState("");
  const [thresholdsJson, setThresholdsJson] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [notices, setNotices] = useState<Record<string, string>>({});
  const setNotice = (key: string, m: string) =>
    setNotices((n) => ({ ...n, [key]: m }));

  const doCreate = () => {
    try {
      const tasks = JSON.parse(tasksJson) as unknown;
      if (!Array.isArray(tasks)) throw new Error("tasks must be a JSON array");
      const thresholds = thresholdsJson.trim()
        ? (JSON.parse(thresholdsJson) as unknown)
        : null;
      create({
        variables: {
          input: {
            name,
            kind,
            taskId: taskId ?? null,
            tasks,
            thresholds,
          },
        },
        onCompleted: (r) => {
          const err = r.learning.evaluationSuiteCreate.errors[0];
          setError(err ? `${err.code}: ${err.message}` : null);
          if (!err) {
            setName("");
            setTasksJson("");
            setThresholdsJson("");
            setRefreshKey((k) => k + 1);
          }
        },
      });
    } catch (e) {
      setError(`invalid JSON: ${(e as Error).message}`);
    }
  };

  return (
    <div>
      <p>
        evaluation is independent of the optimizer's reward: versioned
        suites pin tasks, allowed context, tool versions, budgets and
        acceptance thresholds; hidden targets stay behind the evaluation
        service principal — never reachable by the agent under test or
        its retrieval tools. fixture-only data is not scientific
        validation.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          doCreate();
        }}
      >
        <TextField
          label="suite name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <label>
          kind{" "}
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="development">development (tuning)</option>
            <option value="final">final (untouched held-out)</option>
          </select>
        </label>
        <label>
          tasks (JSON array — public part only){" "}
          <textarea
            rows={4}
            value={tasksJson}
            onChange={(e) => setTasksJson(e.target.value)}
            placeholder='[{"example_id":"ex1","messages":[{"role":"user","content":"…"}],"subgroup":"g1","answerable":true,"group_keys":["g1"]}]'
          />
        </label>
        <label>
          thresholds (JSON array, optional){" "}
          <textarea
            rows={2}
            value={thresholdsJson}
            onChange={(e) => setThresholdsJson(e.target.value)}
            placeholder='[{"metric":"correctness","direction":"min","value":null}]'
          />
        </label>
        <Button
          variant="primary"
          type="submit"
          disabled={creating || !name || !tasksJson}
        >
          {creating ? "registering…" : "register suite"}
        </Button>
      </form>
      {error && (
        <p role="alert">
          <Badge tone="danger">{error}</Badge>
        </p>
      )}
      <Suspense fallback={<LoadingState label="loading suites…" />}>
        <SuiteList
          key={refreshKey}
          taskId={taskId}
          setNotice={setNotice}
          onChanged={() => setRefreshKey((k) => k + 1)}
        />
      </Suspense>
      {Object.entries(notices).map(([k, m]) => (
        <p key={k} role="status">
          {m}
        </p>
      ))}
      <h4>suite runs</h4>
      <Suspense fallback={<LoadingState label="loading runs…" />}>
        <RunList key={`r${refreshKey}`} taskId={taskId} />
      </Suspense>
      <PromotionSurface key={`d${refreshKey}`} taskId={taskId} />
    </div>
  );
}
