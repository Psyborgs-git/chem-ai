import { expect, request, test, type BrowserContext } from "@playwright/test";

const API = "http://127.0.0.1:8790";
const ORIGIN = { origin: "http://127.0.0.1:8790" };

async function signIn(context: BrowserContext): Promise<string> {
  const api = await request.newContext({ baseURL: API });
  const res = await api.post("/api/auth/setup", {
    headers: ORIGIN,
    data: { login: "e2e-owner", display_name: "E2E Owner", password: "e2e-password-10" },
  });
  const res2 = res.ok()
    ? res
    : await api.post("/api/auth/login", {
        headers: ORIGIN,
        data: { login: "e2e-owner", password: "e2e-password-10" },
      });
  expect(res2.ok()).toBeTruthy();
  const token = /studio_session=([^;]+)/.exec(res2.headers()["set-cookie"] ?? "")?.[1];
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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
): Promise<any> {
  const api = await request.newContext({ baseURL: API });
  const res = await api.post("/graphql", {
    headers: { ...ORIGIN, cookie: `studio_session=${token}` },
    data: { query, variables },
  });
  return res.json();
}

/** Seed a task whose prior session ended after a candidate patch was
 * rejected against accepted evidence (AT-0304-1 "given"). */
async function seedPriorSession(token: string): Promise<string> {
  const proj = await gql(
    token,
    `mutation { projectCreate(input: {slug: "mem", name: "Mem"}) {
       project { id } errors { code message } } }`,
  );
  const projectId = proj.data.projectCreate.project.id as string;

  const task = await gql(
    token,
    `mutation ($p: ID!) { taskCreate(input: {
       projectId: $p, title: "mem task", mode: "improve",
       objective: "lower cost" }) {
       task { id } errors { code message } } }`,
    { p: projectId },
  );
  const taskId = task.data.taskCreate.task.id as string;

  const draft = await gql(
    token,
    `mutation ($t: ID!) { contractDraftCreate(input: { taskId: $t,
       payload: { metrics: [{ name: "viscosity", target: ">= 500" }],
         constraints: ["keep pH below 9", "no solvent swaps"],
         warnings: ["solvent lot identity unverified"] } }) {
       contractRevision { id revision } errors { code message } } }`,
    { t: taskId },
  );
  const revId = draft.data.contractDraftCreate.contractRevision.id as string;
  const frozen = await gql(
    token,
    `mutation ($r: ID!) { contractFreeze(input: { revisionId: $r }) {
       contractRevision { id status } errors { code message } } }`,
    { r: revId },
  );
  expect(frozen.data.contractFreeze.errors).toEqual([]);

  // accepted evidence claim
  const claim = await gql(
    token,
    `mutation { evidence { claimCreate(input: {
       kind: "document_claim",
       subject: { entity: "baseline" },
       statement: { text: "baseline viscosity 480 mPa·s" },
       locator: { row: 2, col: 1 } }) {
       claim { id } errors { code message } } } }`,
  );
  const claimId = claim.data.evidence.claimCreate.claim.id as string;
  const reviewed = await gql(
    token,
    `mutation ($c: ID!) { evidence { claimReview(input: {
       claimId: $c, decision: "accepted" }) {
       claim { id status } errors { code message } } } }`,
    { c: claimId },
  );
  expect(reviewed.data.evidence.claimReview.errors).toEqual([]);

  // session A: candidate + rejected patch tied to the claim
  const cand = await gql(
    token,
    `mutation ($t: ID!, $e: JSON!) { candidates { create(input: {
       taskId: $t, entityKind: "formulation", evidenceIds: $e }) {
       candidate { id } errors { code message } } } }`,
    { t: taskId, e: [claimId] },
  );
  const candId = cand.data.candidates.create.candidate.id as string;
  const patch = await gql(
    token,
    `mutation ($c: ID!) { candidates { patchPropose(input: {
       candidateId: $c,
       patch: { ops: [{ op: "set", path: "/solvent", value: "ethanol" }] } }) {
       patchId errors { code message } } } }`,
    { c: candId },
  );
  const patchId = patch.data.candidates.patchPropose.patchId as string;
  const rejected = await gql(
    token,
    `mutation ($p: String!) { candidates { patchReview(input: {
       patchId: $p, accept: false,
       rejectionReason: "solvent swaps barred by contract" }) {
       patchId status errors { code message } } } }`,
    { p: patchId },
  );
  expect(rejected.data.candidates.patchReview.errors).toEqual([]);

  const sA = await gql(
    token,
    `mutation ($t: ID!) { research { sessionStart(input: { taskId: $t }) {
       session { id } errors { code message } } } }`,
    { t: taskId },
  );
  const sessionA = sA.data.research.sessionStart.session.id as string;
  const ended = await gql(
    token,
    `mutation ($s: ID!) { research { sessionEnd(input: { sessionId: $s }) {
       session { id status } errors { code message } } } }`,
    { s: sessionA },
  );
  expect(ended.data.research.sessionEnd.errors).toEqual([]);
  return taskId;
}

/** AT-0304-1 — a new session resumes from a compiled manifest that
 * still carries the prior rejection, the hard constraints, and the
 * evidence IDs. Nothing needs re-explaining. */
test("new session manifest carries prior rejection + constraints + evidence (AT-0304-1)", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  const taskId = await seedPriorSession(token);

  await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
  await page.getByRole("button", { name: "research" }).click();
  // the prior session is visible as ended with its own snapshot
  await expect(page.locator("li", { hasText: "ended" }).first()).toBeVisible();

  await page.getByRole("button", { name: "start research session" }).click();
  await expect(page.getByRole("button", { name: "end active session" })).toBeVisible();

  const manifest = page
    .locator("li", { hasText: "active" })
    .locator(".cs-manifest");
  await expect(manifest).toBeVisible();

  // hard constraints survived — pinned, not budget-dependent
  const pinned = manifest.getByLabel("pinned constraints and warnings");
  await expect(pinned).toContainText("keep pH below 9");
  await expect(pinned).toContainText("identity unverified");

  // the prior rejection is present with its reason — no re-explanation
  const selected = manifest.getByLabel("selected context");
  await expect(selected.locator('[data-kind="rejected_approach"]')).toContainText(
    "solvent swaps barred",
  );
  // reviewed evidence rides in by claim ID, not as a paraphrase
  await expect(selected.locator('[data-kind="evidence"]')).toHaveCount(1);
});

/** AT-0304-2 surface — summaries render with a computed stale marker
 * and stay visually distinct from canonical state. */
test("stale summary is marked after contract change (AT-0304-2)", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  const proj = await gql(
    token,
    `mutation { projectCreate(input: { slug: "sum", name: "Sum" }) {
       project { id } errors { code message } } }`,
  );
  const task = await gql(
    token,
    `mutation ($p: ID!) { taskCreate(input: {
       projectId: $p, title: "sum task", mode: "discover" }) {
       task { id } errors { code message } } }`,
    { p: proj.data.projectCreate.project.id },
  );
  const taskId = task.data.taskCreate.task.id as string;

  // contract v1 → summary pinned to it → contract v2 makes it stale
  const d1 = await gql(
    token,
    `mutation ($t: ID!) { contractDraftCreate(input: { taskId: $t,
       payload: { metrics: [{ name: "m", target: ">= 1" }] } }) {
       contractRevision { id } errors { code message } } }`,
    { t: taskId },
  );
  await gql(
    token,
    `mutation ($r: ID!) { contractFreeze(input: { revisionId: $r }) {
       contractRevision { id } errors { code message } } }`,
    { r: d1.data.contractDraftCreate.contractRevision.id },
  );
  const sum = await gql(
    token,
    `mutation ($t: ID!) { research { summaryCreate(input: {
       taskId: $t, body: "v1 summary", sourceIds: [], generator: "test" }) {
       summaryId errors { code message } } } }`,
    { t: taskId },
  );
  expect(sum.data.research.summaryCreate.errors).toEqual([]);
  const d2 = await gql(
    token,
    `mutation ($t: ID!) { contractDraftCreate(input: { taskId: $t,
       payload: { metrics: [{ name: "m", target: ">= 2" }] } }) {
       contractRevision { id } errors { code message } } }`,
    { t: taskId },
  );
  await gql(
    token,
    `mutation ($r: ID!) { contractFreeze(input: { revisionId: $r }) {
       contractRevision { id } errors { code message } } }`,
    { r: d2.data.contractDraftCreate.contractRevision.id },
  );

  await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
  await page.getByRole("button", { name: "research" }).click();
  const summary = page.locator("li", { hasText: "v1 summary" });
  await expect(summary).toContainText("stale");
  await expect(summary).toContainText("derived");
});
