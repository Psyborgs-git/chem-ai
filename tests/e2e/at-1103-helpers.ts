import { expect, request, test, type BrowserContext, type Page } from "@playwright/test";

const API = "http://127.0.0.1:8790";
const ORIGIN = { origin: "http://127.0.0.1:8790" };

export async function signIn(context: BrowserContext): Promise<string> {
  const api = await request.newContext({ baseURL: API });
  const res = await api.post("/api/auth/setup", {
    headers: ORIGIN,
    data: {
      login: "e2e-owner",
      display_name: "E2E Owner",
      password: "e2e-password-10",
    },
  });
  const res2 = res.ok()
    ? res
    : await api.post("/api/auth/login", {
        headers: ORIGIN,
        data: { login: "e2e-owner", password: "e2e-password-10" },
      });
  expect(res2.ok()).toBeTruthy();
  const setCookie = res2.headers()["set-cookie"] ?? "";
  const token = /studio_session=([^;]+)/.exec(setCookie)?.[1];
  expect(token).toBeTruthy();
  await context.addCookies([
    { name: "studio_session", value: token!, url: "http://127.0.0.1:4173" },
  ]);
  return token!;
}

export async function gql(
  token: string,
  query: string,
  variables: Record<string, unknown> = {},
) {
  const api = await request.newContext({ baseURL: API });
  const res = await api.post("/graphql", {
    data: { query, variables },
    headers: { cookie: `studio_session=${token}`, ...ORIGIN },
  });
  const body = await res.json();
  if (body.errors) throw new Error(JSON.stringify(body.errors));
  return body;
}

export function decodeGlobalId(globalId: string): string {
  const parts = atob(globalId).split(":");
  return parts[parts.length - 1];
}

export const METRIC_ID = "metric.synthetic-performance";

type FocusedDescriptor = {
  tag: string;
  text: string;
  id: string;
  inTaskNav: boolean;
  inSubNav: boolean;
  inPrimaryNav: boolean;
  pressed: string | null;
  current: string | null;
};

export async function focused(page: Page): Promise<FocusedDescriptor> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) {
      return { tag: "body", text: "", id: "", inTaskNav: false, inSubNav: false, inPrimaryNav: false, pressed: null, current: null };
    }
    return {
      tag: el.tagName.toLowerCase(),
      text: (el.textContent ?? "").trim(),
      id: el.id ?? "",
      inTaskNav: !!el.closest('nav[aria-label="task sections"]'),
      inSubNav: !!el.closest('nav[aria-label="section views"]'),
      inPrimaryNav: !!el.closest('nav[aria-label="primary"]'),
      pressed: el.getAttribute("aria-pressed"),
      current: el.getAttribute("aria-current"),
    };
  });
}

/** Pure-keyboard travel: press Tab until `match` holds for the focused
 * element, bounded — a miss means the element is unreachable by
 * keyboard and the test must fail. */
export async function tabUntil(
  page: Page,
  match: (f: FocusedDescriptor) => boolean,
  maxTabs = 80,
): Promise<FocusedDescriptor> {
  for (let i = 0; i < maxTabs; i++) {
    await page.keyboard.press("Tab");
    const f = await focused(page);
    if (match(f)) return f;
  }
  throw new Error(`focus never reached target within ${maxTabs} Tab presses`);
}

export async function seedClosedTask(
  token: string,
  opts: { close?: boolean } = {},
): Promise<string> {
  const proj = await gql(
    token,
    `mutation { projectCreate(input: {slug: "e2e-1103", name: "E2E 1103"}) {
       project { id } errors { message } } }`,
  );
  const projectId = proj.data.projectCreate.project.id as string;
  const task = await gql(
    token,
    `mutation ($p: ID!) { taskCreate(input: {projectId: $p,
       title: "a11y review task", mode: "improve", targetKind: "formulation",
       objective: "keyboard+viewport review",
       modeInputs: {baselineRevisionId: "baseline-rev-1",
         variationScope: "solvent only"}}) {
       task { id } errors { message } } }`,
    { p: projectId },
  );
  expect(task.data.taskCreate.errors ?? []).toEqual([]);
  const taskId = task.data.taskCreate.task.id as string;

  const draft = await gql(
    token,
    `mutation ($t: ID!, $p: JSON!) { contractDraftCreate(
       input: { taskId: $t, payload: $p }) {
       contractRevision { id revision } errors { message } } }`,
    {
      t: taskId,
      p: {
        metrics: [
          {
            id: METRIC_ID,
            label: "Synthetic index",
            required: true,
            operator: "gte",
            target_values: ["5"],
            unit: "dimensionless",
            required_evidence: ["lab_measurement"],
            aggregation: "fixture-single-value",
          },
        ],
        hard_constraints: [
          {
            id: "gate.solvent-free",
            text: "solvent index must reach the pass line",
            check: {
              kind: "metric",
              id: METRIC_ID,
              operator: "gte",
              target_values: ["5"],
              unit: "dimensionless",
              required_evidence: ["lab_measurement"],
              aggregation: "fixture-single-value",
            },
          },
        ],
      },
    },
  );
  const revGid = draft.data.contractDraftCreate.contractRevision.id as string;
  const freeze = await gql(
    token,
    `mutation ($r: ID!) { contractFreeze(input: { revisionId: $r }) {
       contractRevision { id status } errors { message } } }`,
    { r: revGid },
  );
  expect(freeze.data.contractFreeze.errors ?? []).toEqual([]);
  const contractUuid = decodeGlobalId(revGid);

  const cand = await gql(
    token,
    `mutation ($t: ID!) { candidates { create(input: {taskId: $t,
       entityKind: "formulation", hypothesis: "reduce solvent",
       proposedDifferences: [{field: "solvent", op: "reduce"}]}) {
       candidate { id } errors { message } } } }`,
    { t: taskId },
  );
  expect(cand.data.candidates.create.errors ?? []).toEqual([]);
  const candUuid = decodeGlobalId(cand.data.candidates.create.candidate.id);
  const candGid = cand.data.candidates.create.candidate.id as string;
  // PAR-02: evaluation only reports accepted candidates — drive the real
  // draft → submitted → accepted_for_research lifecycle.
  const candSub = await gql(
    token,
    `mutation ($c: ID!) { candidates { submit(input: {candidateId: $c}) {
       candidate { id status } errors { code message } } } }`,
    { c: candGid },
  );
  expect(candSub.data.candidates.submit.errors).toEqual([]);
  const candAccept = await gql(
    token,
    `mutation ($c: ID!) { candidates { review(input: {candidateId: $c,
       accept: true}) {
       candidate { id status } errors { code message } } } }`,
    { c: candGid },
  );
  expect(candAccept.data.candidates.review.errors).toEqual([]);
  const plan = await gql(
    token,
    `mutation ($t: ID!, $p: JSON!) { lab { planCreate(input: {taskId: $t,
       title: "plan a11y", payload: $p}) {
       plan { id } errors { message } } } }`,
    {
      t: taskId,
      p: {
        candidateRevisionId: candUuid,
        contractRevisionId: contractUuid,
        method: "fixture-index",
        samplePlan: [{ batch: "A", aliquots: 1 }],
        acceptanceCriteria: "index >= 5",
        hazardNotes: "none",
        resourceNeeds: "none",
      },
    },
  );
  expect(plan.data.lab.planCreate.errors ?? []).toEqual([]);
  const planId = plan.data.lab.planCreate.plan.id as string;
  const sub = await gql(
    token,
    `mutation ($i: ID!) { lab { planSubmit(input: {planId: $i}) {
       plan { id } errors { message } } } }`,
    { i: planId },
  );
  expect(sub.data.lab.planSubmit.errors ?? []).toEqual([]);
  const rev = await gql(
    token,
    `mutation ($i: ID!) { lab { planReview(input: {planId: $i,
       decision: "approved", rationale: "ok"}) {
       plan { id } errors { code message } } } }`,
    { i: planId },
  );
  expect(rev.data.lab.planReview.errors ?? []).toEqual([]);
  const ex = await gql(
    token,
    `mutation ($i: ID!) { lab { measurements { executionOpen(
       input: {planId: $i}) { execution { id } errors { code message } } } } }`,
    { i: planId },
  );
  expect(ex.data.lab.measurements.executionOpen.errors ?? []).toEqual([]);
  const executionId = ex.data.lab.measurements.executionOpen.execution.id;
  const batch = await gql(
    token,
    `mutation ($i: ID!) { lab { measurements { batchAdd(
       input: {executionId: $i, label: "A"}) {
       batch { id } errors { message } } } } }`,
    { i: executionId },
  );
  const batchId = batch.data.lab.measurements.batchAdd.batch.id;
  const sample = await gql(
    token,
    `mutation ($i: ID!) { lab { measurements { sampleAdd(
       input: {batchId: $i, label: "a1", kind: "aliquot"}) {
       sample { id } errors { message } } } } }`,
    { i: batchId },
  );
  const sampleId = sample.data.lab.measurements.sampleAdd.sample.id;
  const rec = await gql(
    token,
    `mutation ($i: MeasurementRecordInput!) { lab { measurements {
       measurementRecord(input: $i) {
       measurement { id } errors { code message } } } } }`,
    {
      i: {
        sampleId,
        method: "fixture-index",
        repeatType: "independent_batch",
        metric: METRIC_ID,
        value: { kind: "numeric", value: "7", unit: "dimensionless" },
      },
    },
  );
  const mid = rec.data.lab.measurements.measurementRecord.measurement.id;
  await gql(
    token,
    `mutation ($i: MeasurementReviewInput!) { lab { measurements {
       measurementReview(input: $i) {
       measurement { id status } errors { code message } } } } }`,
    { i: { measurementId: mid, decision: "accepted" } },
  );
  for (const toState of ["active", "awaiting_review"]) {
    const r = await gql(
      token,
      `mutation ($i: TaskTransitionInput!) { taskTransition(input: $i) {
         task { id workflowState } errors { code message } } }`,
      { i: { taskId, toState } },
    );
    expect(r.data.taskTransition.errors).toEqual([]);
  }
  // PAR-09 seeds an awaiting-review task by passing {close:false};
  // the default keeps every existing caller's fully closed fixture.
  if (opts.close !== false) {
    const close = await gql(
      token,
      `mutation ($i: TaskCloseInput!) { taskClose(input: $i) {
         task { id workflowState closureDecision } errors { code message } } }`,
      { i: { taskId, closureDecision: "supported_success" } },
    );
    expect(close.data.taskClose.errors).toEqual([]);
    expect(close.data.taskClose.task.workflowState).toBe("closed");
  }
  return taskId;
}
