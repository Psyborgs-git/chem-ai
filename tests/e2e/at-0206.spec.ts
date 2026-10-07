import { expect, request, test, type BrowserContext } from "@playwright/test";

const API = "http://127.0.0.1:8790";
const ORIGIN = { origin: "http://127.0.0.1:8790" };

/** Establish an owner session and hand its cookie to the browser. */
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
    headers: { ...ORIGIN, cookie: `studio_session=${token}` },
    data: { query, variables },
  });
  const body = await res.json();
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

async function makeTask(token: string, projectId: string): Promise<string> {
  const r = await gql(
    token,
    `mutation ($p: ID!) { taskCreate(input: {projectId: $p, title: "e2e task",
       mode: "improve", modeInputs: {baselineRevisionId: "00000000-0000-0000-0000-000000000001",
       variationScope: "solvent"}}) {
       task { id } errors { code message } } }`,
    { p: projectId },
  );
  return r.data.taskCreate.task.id;
}

/** AT-0206-1 — a new user creates one task in each mode; each
 * persists with its mode-appropriate fields. */
test("create one task per mode (AT-0206-1)", async ({ page, context }) => {
  const token = await signIn(context);
  const projectId = await makeProject(token);

  await page.goto("/projects");
  await page.getByRole("link", { name: "E2E Project" }).click();

  const modes: { mode: string; fill: () => Promise<void> }[] = [
    {
      mode: "improve",
      fill: async () => {
        await page
          .getByLabel("baseline formulation revision id")
          .fill("00000000-0000-0000-0000-000000000001");
        await page.getByLabel("variation scope").fill("solvent system");
      },
    },
    {
      mode: "match_reference",
      fill: async () => {
        await page.locator("#mode").selectOption("match_reference");
        await page
          .getByLabel("reference product id")
          .fill("00000000-0000-0000-0000-0000000000ab");
        await page.locator("#match-scope").selectOption("functional_and_analytical");
      },
    },
    {
      mode: "discover",
      fill: async () => {
        await page.locator("#mode").selectOption("discover");
        await page.locator("#target-kind").selectOption("formulation");
        await page.getByLabel("objective", { exact: true }).fill("low-VOC binder");
      },
    },
  ];

  for (const m of modes) {
    await page.goto(`/projects/${encodeURIComponent(projectId)}`);
    await page.getByLabel("task title").fill(`task-${m.mode}`);
    await m.fill();
    await page.getByRole("button", { name: /create task/i }).click();
    // lands on the task workspace; the task persisted server-side
    await expect(page).toHaveURL(/\/tasks\//);
    await expect(page.getByRole("heading", { name: `task-${m.mode}` })).toBeVisible();
    // back and confirm it is listed
    await page.goto(`/projects/${encodeURIComponent(projectId)}`);
    await expect(page.getByRole("link", { name: `task-${m.mode}` })).toBeVisible();
  }
});

/** AT-0206-2 — local API dies mid-edit: save reports unsaved and
 * never claims offline persistence. */
test("API down during save reports unsaved (AT-0206-2)", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  const projectId = await makeProject(token);
  const taskId = await makeTask(token, projectId);

  await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
  const editor = page.locator('[aria-label="success contract editor"]');
  await editor.getByLabel("target value(s)").first().fill("1.5");
  await expect(page.getByText("unsaved changes — not persisted")).toBeVisible();

  // kill the API path before saving
  await page.route("**/graphql", (route) => route.abort());
  await editor.getByRole("button", { name: "save draft" }).click();

  await expect(
    page.getByRole("alert").filter({ hasText: /not persisted|error/i }),
  ).toBeVisible();
  await expect(
    page.getByText("unsaved changes — not persisted"),
  ).toBeVisible();
  await expect(page.getByText("saved offline")).toHaveCount(0);
  await expect(page.getByText(/^saved$/)).toHaveCount(0);
});

/** AT-0206-3 — a patch-accepted candidate produces a new revision;
 * navigating revisions shows distinct canonical IDs and history. */
test("candidate revision history shows distinct canonical IDs (AT-0206-3)", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  const projectId = await makeProject(token);
  const taskId = await makeTask(token, projectId);

  const cand = await gql(
    token,
    `mutation ($t: ID!) { candidates { create(input: {taskId: $t,
       entityKind: "formulation", hypothesis: "h1",
       proposedDifferences: [{field: "solvent", op: "reduce"}]}) {
       candidate { id revision } errors { message } } } }`,
    { t: taskId },
  );
  const candId = cand.data.candidates.create.candidate.id;

  const patch = await gql(
    token,
    `mutation ($c: ID!) { candidates { patchPropose(input: {candidateId: $c,
       patch: {proposedDifferences: [{field: "solvent", op: "replace"}]}}) {
       patchId status errors { message } } } }`,
    { c: candId },
  );
  const patchId = patch.data.candidates.patchPropose.patchId;

  const reviewed = await gql(
    token,
    `mutation ($p: String!) { candidates { patchReview(input: {patchId: $p,
       accept: true}) { status errors { message } } } }`,
    { p: patchId },
  );
  expect(reviewed.data.candidates.patchReview.status).toBe("accepted");

  await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
  await page.getByRole("button", { name: "candidates" }).click();

  const rows = page.locator(".cs-candidate");
  await expect(rows).toHaveCount(2);
  const ids = await rows
    .locator(".cs-candidate__id")
    .allTextContents();
  expect(new Set(ids).size).toBe(2); // distinct canonical IDs
  await expect(page.getByText("rev 1")).toBeVisible();
  await expect(page.getByText("rev 2")).toBeVisible();
  await expect(page.getByText(/child of/)).toBeVisible();

  // open the newer revision's content — parent revision is linked
  await rows.nth(1).getByRole("button", { name: "view content" }).click();
  await expect(page.getByRole("group", { name: "revision comparison" }))
    .toBeVisible();
  await expect(page.getByText("replace")).toBeVisible();
  await expect(page.getByText("reduce")).toBeVisible();
});
