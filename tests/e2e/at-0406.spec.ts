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

async function seedTask(token: string): Promise<string> {
  const proj = await gql(
    token,
    `mutation { projectCreate(input: {slug: "ev-${Date.now() % 100000}", name: "Ev"}) {
       project { id } errors { code message } } }`,
  );
  const projectId = proj.data.projectCreate.project.id as string;
  const task = await gql(
    token,
    `mutation ($p: ID!) { taskCreate(input: {
       projectId: $p, title: "events task", mode: "improve",
       objective: "stream" }) {
       task { id } errors { code message } } }`,
    { p: projectId },
  );
  return task.data.taskCreate.task.id as string;
}

async function seedSession(token: string, taskId: string): Promise<string> {
  const r = await gql(
    token,
    `mutation ($t: ID!) { research { sessionStart(input: { taskId: $t }) {
       session { id } errors { code message } } } }`,
    { t: taskId },
  );
  expect(r.data.research.sessionStart.errors).toEqual([]);
  return r.data.research.sessionStart.session.id as string;
}

async function postMessage(
  token: string,
  sessionId: string,
  kind: string,
  content: string,
  refs?: Record<string, unknown>,
) {
  const r = await gql(
    token,
    `mutation ($s: ID!, $role: String!, $kind: String!, $content: String!, $refs: JSON) {
       research { messagePost(input: { sessionId: $s, role: $role,
         kind: $kind, content: $content, refs: $refs }) {
         message { id } errors { code message } } } }`,
    { s: sessionId, role: kind === "tool_result" ? "tool" : "assistant", kind, content, refs },
  );
  expect(r.data.research.messagePost.errors).toEqual([]);
}

test("AT-0406-1: reconnect after disconnect shows no duplicates and correct run state", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  const taskId = await seedTask(token);
  const sessionId = await seedSession(token, taskId);
  await postMessage(token, sessionId, "message", "first message");
  await postMessage(token, sessionId, "message", "second message");

  await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
  await page.locator('nav[aria-label="task sections"]').getByRole("link", { name: "research" }).click();
  await page.locator("details summary").first().click();

  await expect(page.getByText("first message")).toBeVisible();
  await expect(page.getByText("second message")).toBeVisible();

  // disconnect the stream; a message posted during the outage must
  // appear exactly once after reconnect — resume is by seq id
  await context.setOffline(true);
  await expect(page.getByText("reconnecting…")).toBeVisible({ timeout: 15000 });
  await postMessage(token, sessionId, "message", "posted while offline");

  // a run requested during the outage must also surface correctly
  const run = await gql(
    token,
    `mutation ($t: ID!) { runs { request(input: { taskId: $t, kind: "verify",
       request: { probe: true } }) { run { id status } errors { code message } } } }`,
    { t: taskId },
  );
  expect(run.data.runs.request.errors).toEqual([]);

  await context.setOffline(false);
  await expect(page.getByText("posted while offline")).toBeVisible({ timeout: 15000 });
  const items = await page
    .locator('ul[aria-label="session messages"] li[data-kind="message"]')
    .count();
  expect(items).toBe(3); // no duplicates after resume

  await page.locator('nav[aria-label="task sections"]').getByRole("link", { name: "advanced" }).click();
  await page.locator('nav[aria-label="section views"]').getByRole("link", { name: "runs" }).click();
  await expect(
    page.locator('ul[aria-label="task runs"] li').first(),
  ).toContainText("requested");
});

test("AT-0406-2: failed tool action is rendered failed even when text claims success", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  const taskId = await seedTask(token);
  const sessionId = await seedSession(token, taskId);
  await postMessage(
    token,
    sessionId,
    "tool_call",
    JSON.stringify({ tool: "propose_candidate_patch", arguments: { patch: {} } }),
  );
  await postMessage(
    token,
    sessionId,
    "tool_result",
    JSON.stringify({ ok: false, error: { code: "INVALID_INPUT", message: "patch rejected" } }),
    { tool: "propose_candidate_patch" },
  );
  // assistant prose claims the save succeeded — the UI must trust the
  // action row, not the prose
  await postMessage(token, sessionId, "message", "Candidate saved.");

  await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
  await page.locator('nav[aria-label="task sections"]').getByRole("link", { name: "research" }).click();
  await page.locator("details summary").first().click();

  await expect(page.getByText("action failed")).toBeVisible();
  await expect(page.getByText("action completed")).toHaveCount(0);
  await expect(page.getByText("Candidate saved.")).toBeVisible();
});

test("AT-0406-3: cancel shows 'cancel requested…' until terminal confirmation", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  const taskId = await seedTask(token);
  const run = await gql(
    token,
    `mutation ($t: ID!) { runs { request(input: { taskId: $t, kind: "verify",
       request: { probe: true } }) { run { id } errors { code message } } } }`,
    { t: taskId },
  );
  const runId = run.data.runs.request.run.id as string;

  await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
  await page.locator('nav[aria-label="task sections"]').getByRole("link", { name: "advanced" }).click();
  await page.locator('nav[aria-label="section views"]').getByRole("link", { name: "runs" }).click();
  await expect(page.locator("ul[aria-label='task runs'] li").first()).toContainText(
    "requested",
  );

  const cancel = await gql(
    token,
    `mutation ($r: ID!) { runs { requestCancel(input: { runId: $r }) {
       run { id status } errors { code message } } } }`,
    { r: runId },
  );
  expect(cancel.data.runs.requestCancel.errors).toEqual([]);
  expect(cancel.data.runs.requestCancel.run.status).toBe("cancel_requested");

  // the live event must update the row in place — and it stays
  // "cancel requested…" because no worker has confirmed the stop
  await expect(page.locator("ul[aria-label='task runs'] li").first()).toContainText(
    "cancel requested…",
    { timeout: 15000 },
  );
  await expect(
    page.locator("ul[aria-label='task runs'] li").first(),
  ).not.toContainText("cancelled");
});
