import { expect, request, test, type BrowserContext } from "@playwright/test";

const API = "http://127.0.0.1:8790";
const ORIGIN = { origin: "http://127.0.0.1:8790" };

async function signIn(context: BrowserContext): Promise<string> {
  const api = await request.newContext({ baseURL: API });
  const res = await api.post("/api/auth/setup", {
    headers: ORIGIN,
    data: { login: "e2e-owner", display_name: "E2E Owner", password: "e2e-password-10" },
  });
  // setup only succeeds on an empty workspace; fall back to login
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

async function makeProject(token: string): Promise<string> {
  const r = await gql(
    token,
    `mutation { projectCreate(input: {slug: "e2e-proj", name: "E2E Project"}) {
       project { id } errors { code message } } }`,
  );
  return r.data.projectCreate.project.id;
}

function decodeGlobalId(globalId: string): string {
  const decoded = atob(globalId);
  const parts = decoded.split(":");
  return parts[parts.length - 1];
}

/** AT-0501-3 — a qualified reviewer approves a fixture plan; the
 * exported packet carries the exact bound revisions and the
 * manual-execution label. No equipment execution exists. */
test("approved plan exports a manual-execution packet (AT-0501-3)", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  const projectId = await makeProject(token);
  const task = await gql(
    token,
    `mutation ($p: ID!) { taskCreate(input: {projectId: $p,
       title: "lab plan task", mode: "discover",
       targetKind: "formulation", objective: "low-VOC binder"}) {
       task { id } errors { code message } } }`,
    { p: projectId },
  );
  const taskId = task.data.taskCreate.task.id as string;

  const cand = await gql(
    token,
    `mutation ($t: ID!) { candidates { create(input: {taskId: $t,
       entityKind: "formulation", hypothesis: "h1",
       proposedDifferences: [{field: "solvent", op: "reduce"}]}) {
       candidate { id } errors { message } } } }`,
    { t: taskId },
  );
  expect(cand.data.candidates.create.errors).toEqual([]);
  const candUuid = decodeGlobalId(cand.data.candidates.create.candidate.id);

  const draft = await gql(
    token,
    `mutation ($t: ID!) { contractDraftCreate(input: { taskId: $t,
       payload: { metrics: [{ name: "viscosity", target: ">= 500" }],
         constraints: ["keep pH below 9"], warnings: [] } }) {
       contractRevision { id } errors { code message } } }`,
    { t: taskId },
  );
  const revGid = draft.data.contractDraftCreate.contractRevision.id as string;
  const frozen = await gql(
    token,
    `mutation ($r: ID!) { contractFreeze(input: { revisionId: $r }) {
       contractRevision { id status } errors { code message } } }`,
    { r: revGid },
  );
  expect(frozen.data.contractFreeze.errors).toEqual([]);
  const contractUuid = decodeGlobalId(revGid);

  const plan = await gql(
    token,
    `mutation ($t: ID!, $p: JSON!) { lab { planCreate(input: {taskId: $t,
       title: "viscosity confirmation", payload: $p}) {
       plan { id status } errors { code message } } } }`,
    {
      t: taskId,
      p: {
        candidateRevisionId: candUuid,
        contractRevisionId: contractUuid,
        method: "ASTM D2196",
        samplePlan: [{ batch: "A", aliquots: 2 }],
        acceptanceCriteria: "viscosity within contract band",
        hazardNotes: "no special hazards identified",
        resourceNeeds: "mixer, viscometer",
      },
    },
  );
  expect(plan.data.lab.planCreate.errors).toEqual([]);

  await page.goto("/lab");
  await page.locator("#lab-project").selectOption({ label: "E2E Project" });
  await page.locator("#lab-task").selectOption({ label: "lab plan task" });

  const card = page.locator(".cs-plan");
  await expect(card).toHaveCount(1);
  await expect(card.locator(".cs-badge")).toHaveText("draft");
  // no blockers — all required inputs are bound
  await expect(card.locator('[aria-label="blockers"]')).toHaveCount(0);

  await card.getByRole("button", { name: "submit for review" }).click();
  await expect(card.locator(".cs-badge")).toHaveText("submitted");

  await card.getByLabel("review rationale").fill("fixture review ok");
  await card.getByRole("button", { name: "approve" }).click();
  await expect(card.locator(".cs-badge")).toHaveText("approved");

  await card.getByRole("button", { name: "export manual packet" }).click();
  const packetSection = card.locator('[aria-label="execution packet"]');
  await expect(packetSection).toBeVisible();
  await expect(packetSection.locator(".cs-badge")).toContainText(
    "MANUAL EXECUTION",
  );
  await expect(packetSection.locator('[data-field="packet-mode"]')).toHaveText(
    "manual",
  );
  // approval provenance is bound into the packet
  await expect(
    packetSection.locator('[data-field="packet-approval"] code'),
  ).not.toHaveText("—");

  await packetSection.getByText("packet contents").click();
  const packetJson = packetSection.locator('[data-field="packet-json"]');
  await expect(packetJson).toContainText(candUuid);
  await expect(packetJson).toContainText(contractUuid);
  await expect(packetJson).toContainText("ASTM D2196");

  // no equipment-execution affordance exists anywhere on the surface
  await expect(
    page.getByRole("button", { name: /execute|start equipment/i }),
  ).toHaveCount(0);
});
