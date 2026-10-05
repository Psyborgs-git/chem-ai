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

/** Seed chain: project → task → candidate+contract → approved plan →
 * open execution → batch A → sample a1. */
async function seedExecution(token: string, tag: string) {
  const proj = await gql(
    token,
    `mutation { projectCreate(input: {slug: "e2e-0502-${tag}",
       name: "E2E 0502 ${tag}"}) { project { id } errors { message } } }`,
  );
  const projectId = proj.data.projectCreate.project.id as string;
  const task = await gql(
    token,
    `mutation ($p: ID!) { taskCreate(input: {projectId: $p,
       title: "results task ${tag}", mode: "discover",
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
  const draft = await gql(
    token,
    `mutation ($t: ID!) { contractDraftCreate(input: { taskId: $t,
       payload: { metrics: [{ name: "viscosity", target: ">= 100 mPa·s" }],
         constraints: [], warnings: [] } }) {
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
        method: "ASTM D2196",
        samplePlan: [{ batch: "A", aliquots: 1 }],
        acceptanceCriteria: "viscosity in band",
        hazardNotes: "none",
        resourceNeeds: "viscometer",
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
  const rev = await gql(
    token,
    `mutation ($i: ID!) { lab { planReview(input: {planId: $i,
       decision: "approved", rationale: "ok"}) {
       plan { id } errors { code message } } } }`,
    { i: planId },
  );
  expect(rev.data.lab.planReview.errors).toEqual([]);
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
  return { projectId, taskId, taskTitle: `results task ${tag}`, sampleId };
}

async function recordMeasurement(
  token: string,
  sampleId: string,
  value: Record<string, unknown>,
  repeatType = "same_sample",
  method = "ASTM D2196",
): Promise<string> {
  const r = await gql(
    token,
    `mutation ($i: MeasurementRecordInput!) { lab { measurements {
       measurementRecord(input: $i) {
       measurement { id } errors { code message } } } } }`,
    {
      i: {
        sampleId,
        method,
        repeatType,
        value: { kind: "numeric", ...value },
      },
    },
  );
  expect(r.data.lab.measurements.measurementRecord.errors).toEqual([]);
  return r.data.lab.measurements.measurementRecord.measurement.id as string;
}

async function openResults(page: import("@playwright/test").Page, tag: string) {
  await page.goto("/lab");
  await page
    .locator("#lab-project")
    .selectOption({ label: `E2E 0502 ${tag}` });
  await page
    .locator("#lab-task")
    .selectOption({ label: `results task ${tag}` });
}

/** AT-0502-1 — three repeat readings on one aliquot are observations,
 * not three independent batches. */
test("same-aliquot readings do not inflate replication (AT-0502-1)", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  const s = await seedExecution(token, "at1");
  for (const mag of ["101.0", "102.4", "99.8"]) {
    await recordMeasurement(token, s.sampleId, {
      value: mag,
      unit: "mPa·s",
    });
  }
  await openResults(page, "at1");
  const summary = page.locator('[data-field="replication-summary"]');
  await expect(summary.locator('[data-field="independent-batches"]')).toHaveText(
    "1",
  );
  await expect(summary.locator('[data-field="observations"]')).toHaveText("3");
  await expect(
    page.locator('[data-field="measurement-value"]'),
  ).toHaveCount(3);
  await expect(
    page.locator('[data-field="by-repeat-type"]'),
  ).toContainText('"same_sample":3');
});

/** AT-0502-2 — an incompatible unit (mass vs viscosity) must produce
 * an inconclusive comparison with an actionable finding. */
test("incompatible unit yields inconclusive + finding (AT-0502-2)", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  const s = await seedExecution(token, "at2");
  const mId = await recordMeasurement(token, s.sampleId, {
    value: "12.5",
    unit: "g",
  });
  const check = await gql(
    token,
    `query ($m: ID!, $x: JSON!) {
       measurementContractCheck(measurementId: $m, metric: $x) }`,
    {
      m: mId,
      x: { name: "viscosity", target: ">= 100 mPa·s" },
    },
  );
  const r = check.data.measurementContractCheck;
  expect(r.verdict).toBe("inconclusive");
  expect(
    r.findings.some(
      (f: { kind?: string; action?: string }) =>
        f.action && f.action.length > 0,
    ),
  ).toBeTruthy();

  await openResults(page, "at2");
  const item = page.locator(`[data-measurement-id="${mId}"]`);
  await item.locator('[data-field="contract-check"] summary').click();
  await item.getByRole("button", { name: "compare" }).click();
  await expect(
    item.locator('[data-field="contract-verdict"]'),
  ).toHaveAttribute("data-verdict", "inconclusive");
  await expect(
    item.locator('[aria-label="comparison findings"] li').first(),
  ).toContainText(/action:/);
});

/** AT-0502-3 — amending an accepted measurement keeps the original
 * immutable and flags supersession. */
test("amendment supersedes; original stays immutable (AT-0502-3)", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  const s = await seedExecution(token, "at3");
  const mId = await recordMeasurement(token, s.sampleId, {
    value: "102.4",
    unit: "mPa·s",
  });
  const rv = await gql(
    token,
    `mutation ($i: MeasurementReviewInput!) { lab { measurements {
       measurementReview(input: $i) {
       measurement { id status } errors { message } } } } }`,
    { i: { measurementId: mId, decision: "accepted", note: "ok" } },
  );
  expect(rv.data.lab.measurements.measurementReview.errors).toEqual([]);

  await openResults(page, "at3");
  const item = page.locator(`[data-measurement-id="${mId}"]`);
  await expect(item.locator(".cs-badge").first()).toHaveText("accepted");

  await item.getByRole("button", { name: "amend" }).click();
  await item.getByLabel("amendment reason (required)").fill("misread scale");
  await item
    .getByLabel("amended value (JSON)")
    .fill(
      JSON.stringify({ kind: "numeric", value: "120.4", unit: "mPa·s" }),
    );
  await item.getByRole("button", { name: "submit amendment" }).click();

  await expect(item).toHaveAttribute("data-status", "superseded");
  await expect(item.locator(".cs-badge--danger")).toHaveText("superseded");
  await expect(item.locator('[data-field="amendment"]')).toContainText(
    "misread scale",
  );
  // the original value is preserved, not overwritten
  await expect(item.locator('[data-field="measurement-value"]')).toHaveText(
    "102.4 mPa·s",
  );
});
