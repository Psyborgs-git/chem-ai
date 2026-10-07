import { expect, request, test, type BrowserContext } from "@playwright/test";

const API = "http://127.0.0.1:8790";
const ORIGIN = { origin: "http://127.0.0.1:8790" };

async function signIn(context: BrowserContext): Promise<string> {
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

async function gql(
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

function decodeGlobalId(globalId: string): string {
  const parts = atob(globalId).split(":");
  return parts[parts.length - 1];
}

const METRIC_ID = "metric.synthetic-performance";

/** Seed chain: project → task → candidate → frozen contract (evaluator
 * metric shape) → approved plan → open execution → batch → sample. */
async function seedTask(token: string, tag: string) {
  const proj = await gql(
    token,
    `mutation { projectCreate(input: {slug: "e2e-0503-${tag}",
       name: "E2E 0503 ${tag}"}) { project { id } errors { message } } }`,
  );
  const projectId = proj.data.projectCreate.project.id as string;
  const task = await gql(
    token,
    `mutation ($p: ID!) { taskCreate(input: {projectId: $p,
       title: "closeout task ${tag}", mode: "discover",
       targetKind: "formulation", objective: "binder ${tag}"}) {
       task { id } errors { message } } }`,
    { p: projectId },
  );
  const taskId = task.data.taskCreate.task.id as string;
  const cand = await gql(
    token,
    `mutation ($t: ID!) { candidates { create(input: {taskId: $t,
       entityKind: "formulation", hypothesis: "h",
       proposedDifferences: [{field: "solvent", op: "reduce"}]}) {
       candidate { id } errors { message } } } }`,
    { t: taskId },
  );
  const candUuid = decodeGlobalId(cand.data.candidates.create.candidate.id);
  const candGid = cand.data.candidates.create.candidate.id as string;
  // PAR-02: evaluation only reports candidates a human review accepted —
  // drive the real draft → submitted → accepted_for_research lifecycle.
  const sub = await gql(
    token,
    `mutation ($c: ID!) { candidates { submit(input: {candidateId: $c}) {
       candidate { id status } errors { code message } } } }`,
    { c: candGid },
  );
  expect(sub.data.candidates.submit.errors).toEqual([]);
  const accept = await gql(
    token,
    `mutation ($c: ID!) { candidates { review(input: {candidateId: $c,
       accept: true}) {
       candidate { id status } errors { code message } } } }`,
    { c: candGid },
  );
  expect(accept.data.candidates.review.errors).toEqual([]);
  const draft = await gql(
    token,
    `mutation ($t: ID!) { contractDraftCreate(input: { taskId: $t,
       payload: { metrics: [{ id: "${METRIC_ID}",
         label: "Synthetic test-only index", required: true,
         operator: "gte", target_values: ["5"],
         unit: "dimensionless",
         required_evidence: ["lab_measurement"],
         aggregation: "fixture-single-value" }],
         hard_constraints: [] } }) {
       contractRevision { id } errors { message } } }`,
    { t: taskId },
  );
  const revGid = draft.data.contractDraftCreate.contractRevision.id as string;
  await gql(
    token,
    `mutation ($r: ID!) { contractFreeze(input: { revisionId: $r }) {
       contractRevision { id } errors { message } } }`,
    { r: revGid },
  );
  const plan = await gql(
    token,
    `mutation ($t: ID!, $p: JSON!) { lab { planCreate(input: {taskId: $t,
       title: "plan ${tag}", payload: $p}) {
       plan { id status } errors { message } } } }`,
    {
      t: taskId,
      p: {
        candidateRevisionId: candUuid,
        contractRevisionId: decodeGlobalId(revGid),
        method: "fixture-index",
        samplePlan: [{ batch: "A", aliquots: 1 }],
        acceptanceCriteria: "index >= 5",
        hazardNotes: "none",
        resourceNeeds: "none",
      },
    },
  );
  const planId = plan.data.lab.planCreate.plan.id as string;
  await gql(
    token,
    `mutation ($i: ID!) { lab { planSubmit(input: {planId: $i}) {
       plan { id } errors { message } } } }`,
    { i: planId },
  );
  await gql(
    token,
    `mutation ($i: ID!) { lab { planReview(input: {planId: $i,
       decision: "approved", rationale: "ok"}) {
       plan { id } errors { code message } } } }`,
    { i: planId },
  );
  const ex = await gql(
    token,
    `mutation ($i: ID!) { lab { measurements { executionOpen(
       input: {planId: $i}) { execution { id } errors { code message } } } } }`,
    { i: planId },
  );
  expect(ex.data.lab.measurements.executionOpen.errors).toEqual([]);
  const executionId =
    ex.data.lab.measurements.executionOpen.execution.id as string;
  const batch = await gql(
    token,
    `mutation ($i: ID!) { lab { measurements { batchAdd(
       input: {executionId: $i, label: "A"}) {
       batch { id } errors { message } } } } }`,
    { i: executionId },
  );
  const batchId = batch.data.lab.measurements.batchAdd.batch.id as string;
  const sample = await gql(
    token,
    `mutation ($i: ID!) { lab { measurements { sampleAdd(
       input: {batchId: $i, label: "a1", kind: "aliquot"}) {
       sample { id } errors { message } } } } }`,
    { i: batchId },
  );
  const sampleId = sample.data.lab.measurements.sampleAdd.sample.id as string;
  return { taskId, sampleId };
}

async function acceptedMeasurement(
  token: string,
  sampleId: string,
  value: string,
  metric?: string,
): Promise<void> {
  const r = await gql(
    token,
    `mutation ($i: MeasurementRecordInput!) { lab { measurements {
       measurementRecord(input: $i) {
       measurement { id } errors { code message } } } } }`,
    {
      i: {
        sampleId,
        method: "fixture-index",
        repeatType: "independent_batch",
        metric: metric ?? null,
        value: { kind: "numeric", value, unit: "dimensionless" },
      },
    },
  );
  expect(r.data.lab.measurements.measurementRecord.errors).toEqual([]);
  const mid = r.data.lab.measurements.measurementRecord.measurement.id;
  const rev = await gql(
    token,
    `mutation ($i: MeasurementReviewInput!) { lab { measurements {
       measurementReview(input: $i) {
       measurement { id status } errors { code message } } } } }`,
    { i: { measurementId: mid, decision: "accepted" } },
  );
  expect(rev.data.lab.measurements.measurementReview.errors).toEqual([]);
}

async function transition(token: string, taskId: string, toState: string) {
  const r = await gql(
    token,
    `mutation ($i: TaskTransitionInput!) { taskTransition(input: $i) {
       task { id workflowState } errors { code message } } }`,
    { i: { taskId, toState } },
  );
  expect(r.data.taskTransition.errors).toEqual([]);
}

/** AT-0503-3 journey — accepted attributed evidence → evaluator
 * suggests supported_success → human reviewer closes; the packet binds
 * contract + evidence revisions. */
test("closeout: eligible evaluation → human close (AT-0503-3)", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  const s = await seedTask(token, "close");
  await acceptedMeasurement(token, s.sampleId, "6", METRIC_ID);
  await transition(token, s.taskId, "active");

  await page.goto(`/tasks/${encodeURIComponent(s.taskId)}`);
  await page.getByRole("button", { name: "closeout" }).click();

  const report = page.locator('[data-field="evaluation-report"]');
  await expect(report).toBeVisible();
  await expect(
    page.locator('[data-field="metric-verdict"] >> text=met'),
  ).toBeVisible();
  await expect(
    page.locator('text=suggestion: supported_success'),
  ).toBeVisible();
  await expect(page.locator("text=fixture-only")).toBeVisible();

  // active → awaiting_review via the UI transition
  await page.getByRole("button", { name: "send to review" }).click();
  await expect(page.locator('[data-field="close-form"]')).toBeVisible({
    timeout: 15000,
  });

  // human confirmation required — button stays disabled without it
  await page.locator("#closure-decision").selectOption("supported_success");
  const closeBtn = page.getByRole("button", { name: "close task" });
  await expect(closeBtn).toBeDisabled();
  await page
    .locator("text=I confirm this closure as the human reviewer")
    .click();
  await expect(closeBtn).toBeEnabled();
  await closeBtn.click();
  await expect(page.locator('[data-field="closed-note"]')).toBeVisible({
    timeout: 15000,
  });

  // the bound packet was signed against the frozen contract + evidence
  const packet = await gql(
    token,
    `query ($t: ID!) { taskCloseoutPacket(taskId: $t) }`,
    { t: s.taskId },
  );
  expect(packet.data.taskCloseoutPacket.fixtureOnly).toBe(true);
  expect(packet.data.taskCloseoutPacket.evidenceIds.length).toBe(1);
});

/** AT-0503-1 journey — a required metric with no evidence keeps the
 * task inconclusive; supported_success is not selectable. */
test("closeout: unmeasured metric stays inconclusive (AT-0503-1)", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  const s = await seedTask(token, "gap");
  await transition(token, s.taskId, "active");
  await transition(token, s.taskId, "awaiting_review");

  await page.goto(`/tasks/${encodeURIComponent(s.taskId)}`);
  await page.getByRole("button", { name: "closeout" }).click();

  await expect(
    page.locator('[data-field="evaluation-report"]'),
  ).toBeVisible();
  await expect(
    page.locator('[data-field="metric-verdict"] >> text=inconclusive'),
  ).toBeVisible();
  await expect(
    page.locator('text=suggestion: inconclusive'),
  ).toBeVisible();

  // supported_success is disabled in the UI…
  const option = page.locator(
    '#closure-decision option[value="supported_success"]',
  );
  await expect(option).toBeDisabled();

  // …and the service would refuse it anyway — close honestly instead
  await page.locator("#closure-decision").selectOption("inconclusive");
  await page
    .locator("text=I confirm this closure as the human reviewer")
    .click();
  await page.getByRole("button", { name: "close task" }).click();
  await expect(page.locator('[data-field="closed-note"]')).toBeVisible({
    timeout: 15000,
  });
});
