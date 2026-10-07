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

async function createProjectTask(
  token: string,
  tag: string,
  mode: string,
  extraInput = "",
) {
  const proj = await gql(
    token,
    `mutation { projectCreate(input: {slug: "e2e-0504-${tag}",
       name: "E2E 0504 ${tag}"}) { project { id } errors { message } } }`,
  );
  const projectId = proj.data.projectCreate.project.id as string;
  const task = await gql(
    token,
    `mutation ($p: ID!) { taskCreate(input: {projectId: $p,
       title: "task ${tag}", mode: "${mode}", targetKind: "formulation",
       objective: "obj ${tag}" ${extraInput}}) {
       task { id } errors { message } } }`,
    { p: projectId },
  );
  expect(task.data.taskCreate.errors ?? []).toEqual([]);
  return task.data.taskCreate.task.id as string;
}

async function freezeMetricContract(
  token: string,
  taskId: string,
  metrics: Record<string, unknown>[],
): Promise<string> {
  const draft = await gql(
    token,
    `mutation ($t: ID!, $p: JSON!) { contractDraftCreate(
       input: { taskId: $t, payload: $p }) {
       contractRevision { id revision } errors { message } } }`,
    { t: taskId, p: { metrics, hard_constraints: [] } },
  );
  const revGid = draft.data.contractDraftCreate.contractRevision.id as string;
  await gql(
    token,
    `mutation ($r: ID!) { contractFreeze(input: { revisionId: $r }) {
       contractRevision { id status } errors { message } } }`,
    { r: revGid },
  );
  return decodeGlobalId(revGid);
}

async function measuredPlan(
  token: string,
  taskId: string,
  tag: string,
  contractUuid: string,
  value: string,
): Promise<void> {
  const cand = await gql(
    token,
    `mutation ($t: ID!) { candidates { create(input: {taskId: $t,
       entityKind: "formulation", hypothesis: "reduce solvent",
       proposedDifferences: [{field: "solvent", op: "reduce"}]}) {
       candidate { id } errors { message } } } }`,
    { t: taskId },
  );
  const candUuid = decodeGlobalId(cand.data.candidates.create.candidate.id);
  const candGid = cand.data.candidates.create.candidate.id as string;
  // PAR-02: evaluation only reports accepted candidates — drive the real
  // draft → submitted → accepted_for_research lifecycle.
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
  const plan = await gql(
    token,
    `mutation ($t: ID!, $p: JSON!) { lab { planCreate(input: {taskId: $t,
       title: "plan ${tag}", payload: $p}) {
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
        value: { kind: "numeric", value, unit: "dimensionless" },
      },
    },
  );
  const mid = rec.data.lab.measurements.measurementRecord.measurement.id;
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

async function closeTask(
  token: string,
  taskId: string,
  decision: string,
): Promise<void> {
  const r = await gql(
    token,
    `mutation ($i: TaskCloseInput!) { taskClose(input: $i) {
       task { id workflowState closureDecision } errors { code message } } }`,
    { i: { taskId, closureDecision: decision } },
  );
  expect(r.data.taskClose.errors).toEqual([]);
}

async function startSession(token: string, taskId: string) {
  const r = await gql(
    token,
    `mutation ($i: SessionStartInput!) { research { sessionStart(input: $i) {
       session { id startManifest { items } } errors { code message } } } }`,
    { i: { taskId } },
  );
  expect(r.data.research.sessionStart.errors).toEqual([]);
  return r.data.research.sessionStart.session;
}

/** AT-0504-1 — improve journey: measured evidence → human close → a
 * later contract revision must not rewrite the signed outcome; a new
 * session retains the history. */
test("improve journey: close binds contract; new revision cannot rewrite it (AT-0504-1)", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  const taskId = await createProjectTask(token, "imp", "improve",
    `, modeInputs: {baselineRevisionId: "baseline-rev-1",
       variationScope: "solvent only"}`);
  const contractA = await freezeMetricContract(token, taskId, [
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
  ]);
  await measuredPlan(token, taskId, "imp", contractA, "7");
  await transition(token, taskId, "active");
  await transition(token, taskId, "awaiting_review");
  await closeTask(token, taskId, "supported_success");

  // a NEW contract revision freezes afterwards — the signed closure
  // must still bind revision A
  const contractB = await freezeMetricContract(token, taskId, [
    {
      id: METRIC_ID,
      label: "Synthetic index",
      required: true,
      operator: "gte",
      target_values: ["9"],
      unit: "dimensionless",
      required_evidence: ["lab_measurement"],
      aggregation: "fixture-single-value",
    },
  ]);
  expect(contractB).not.toBe(contractA);

  const decisions = await gql(
    token,
    `query ($t: ID!) { taskDecisions(taskId: $t) {
       edges { node { kind payload createdAt } } } }`,
    { t: taskId },
  );
  const closure = decisions.data.taskDecisions.edges.find(
    (e: { node: { kind: string } }) => e.node.kind === "closure",
  );
  expect(closure.node.payload.contractRevisionId).toBe(contractA);
  expect(closure.node.payload.packet.fixtureOnly).toBe(true);
  expect(closure.node.payload.closureDecision).toBe("supported_success");

  // a new session retains the closure history
  const session = await startSession(token, taskId);
  const closureItem = session.startManifest.items.find(
    (i: { kind: string; text: string }) =>
      i.kind === "decision" && i.text.includes("closure"),
  );
  expect(closureItem).toBeTruthy();
  expect(closureItem.text).toContain("supported_success");

  // report + decisions tabs render the bound packet in the browser
  await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
  await page.getByRole("button", { name: "decisions" }).click();
  await expect(page.locator('[data-field="decision-log"]')).toBeVisible();
  await expect(
    page.locator('[data-field="decision-closure"]'),
  ).toContainText("supported_success");
  await expect(
    page.locator('[data-field="decision-contract"]'),
  ).toContainText(contractA);
  await page.locator('[data-field="decision-packet"] summary').click();
  await expect(
    page.locator("text=scientific validation: not_validated"),
  ).toBeVisible();

  await page.getByRole("button", { name: "report" }).click();
  await expect(page.locator('[data-field="task-report"]')).toBeVisible();
  await expect(
    page.locator('[data-field="report-contract"]'),
  ).toContainText("revision 2");
});

/** AT-0504-2 — match journey: functional scope closes on measured
 * functional evidence; composition stays unknown and no exact-identity
 * claim ever appears. */
test("match journey: functional scope only, composition not established (AT-0504-2)", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  const rp = await gql(
    token,
    `mutation { materials { referenceProductCreate(input: {name: "Competitor X",
       supplier: "ACME", compositionKnowledge: "unknown"}) {
       product { id compositionKnowledge } errors { message } } } }`,
  );
  const refId = decodeGlobalId(
    rp.data.materials.referenceProductCreate.product.id,
  );
  expect(
    rp.data.materials.referenceProductCreate.product.compositionKnowledge,
  ).toBe("unknown");

  const taskId = await createProjectTask(token, "mat", "match_reference",
    `, modeInputs: {referenceProductId: "${refId}",
       matchScope: "functional"}`);
  const contract = await freezeMetricContract(token, taskId, [
    {
      id: METRIC_ID,
      label: "Functional index",
      required: true,
      operator: "gte",
      target_values: ["5"],
      unit: "dimensionless",
      required_evidence: ["lab_measurement"],
      aggregation: "fixture-single-value",
    },
    {
      id: "metric.spectral-match",
      label: "Spectral similarity",
      required: false,
      operator: "gte",
      target_values: ["0.95"],
      unit: "fraction",
      required_evidence: ["lab_measurement"],
      aggregation: "fixture-single-value",
    },
  ]);
  await measuredPlan(token, taskId, "mat", contract, "8");
  await transition(token, taskId, "active");
  await transition(token, taskId, "awaiting_review");
  await closeTask(token, taskId, "supported_success");

  await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
  await page.getByRole("button", { name: "report" }).click();
  const report = page.locator('[data-field="task-report"]');
  await expect(report).toBeVisible();
  // functional metric met, optional analytical metric honestly
  // inconclusive (never measured)
  await expect(
    page.locator('[data-field="report-metric-verdict"] >> text=met'),
  ).toBeVisible();
  await expect(
    page.locator('text=functional match says nothing about composition'),
  ).toBeVisible();
  // no identity / recipe claim anywhere on the report
  await expect(page.locator("text=same molecule")).toHaveCount(0);
  await expect(page.locator("text=exact identity established")).toHaveCount(0);
  await expect(page.locator("text=recipe recovered")).toHaveCount(0);
});

/** AT-0504-3 — discover journey: a stopped execution's failure cause
 * lands in the next session manifest; the task is informed without
 * invented chemistry. */
test("discover journey: failed experiment informs the next session (AT-0504-3)", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  const taskId = await createProjectTask(token, "dis", "discover");
  const contract = await freezeMetricContract(token, taskId, [
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
  ]);
  await measuredPlan(token, taskId, "dis", contract, "2");

  // record the failure honestly: observations + execution stopped
  const executions = await gql(
    token,
    `query ($t: ID!) { taskExecutions(taskId: $t) { id } }`,
    { t: taskId },
  );
  const exId = executions.data.taskExecutions[0].id as string;
  await gql(
    token,
    `mutation ($i: ActualsRecordInput!) { lab { measurements {
       actualsRecord(input: $i) { execution { id }
       errors { code message } } } } }`,
    {
      i: {
        executionId: exId,
        actual: { materials: ["lot-7"], process: "stirred 2h" },
        deviations: ["phase separation observed at 40C"],
        observations: "emulsion broke — candidate failed at temperature",
      },
    },
  );
  await gql(
    token,
    `mutation ($i: ExecutionCloseInput!) { lab { measurements {
       executionClose(input: $i) { execution { id status }
       errors { code message } } } } }`,
    { i: { executionId: exId, status: "stopped" } },
  );

  // next session: the failure is in the manifest — not invisible history
  const session = await startSession(token, taskId);
  const outcome = session.startManifest.items.find(
    (i: { kind: string }) => i.kind === "experiment_outcome",
  );
  expect(outcome).toBeTruthy();
  expect(outcome.text).toContain("emulsion broke");
  expect(outcome.text).toContain("stopped");

  // the manifest renders in the research tab
  await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
  await page.getByRole("button", { name: "research" }).click();
  await expect(
    page.locator('[data-kind="experiment_outcome"]'),
  ).toContainText("emulsion broke", { timeout: 15000 });
});
