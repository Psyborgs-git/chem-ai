import { expect, request, test } from "@playwright/test";

import { gql, signIn } from "./at-1103-helpers";

const ORIGIN = { origin: "http://127.0.0.1:8790" };

async function seedTask(token: string): Promise<string> {
  const proj = await gql(
    token,
    `mutation { projectCreate(input: {slug: "strm-${Date.now() % 100000}", name: "Strm"}) {
       project { id } errors { code message } } }`,
  );
  const projectId = proj.data.projectCreate.project.id as string;
  const task = await gql(
    token,
    `mutation ($p: ID!) { taskCreate(input: {
       projectId: $p, title: "stream task", mode: "improve",
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
): Promise<void> {
  const r = await gql(
    token,
    `mutation ($s: ID!, $role: String!, $kind: String!, $content: String!) {
       research { messagePost(input: { sessionId: $s, role: $role,
         kind: $kind, content: $content }) { message { id } errors { code message } } } }`,
    { s: sessionId, role: "assistant", kind, content },
  );
  expect(r.data.research.messagePost.errors).toEqual([]);
}

/** Navigate to the session stream on the task's research section. */
async function openSessionStream(page: import("@playwright/test").Page, taskId: string) {
  await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
  await page.getByRole("button", { name: "research" }).click();
  await page.locator("details summary").first().click();
}

test.describe("PAR-08a stream recovery", () => {
  test("initial snapshot failure retries and recovers", async ({ page, context }) => {
    const token = await signIn(context);
    const taskId = await seedTask(token);
    const sessionId = await seedSession(token, taskId);
    await postMessage(token, sessionId, "message", "survives the outage");

    // transient snapshot outage: the stream must not silently go dead —
    // it shows an honest retry state, then recovers when the API returns
    await page.route("**/api/events/snapshot**", (route) => route.abort());
    await openSessionStream(page, taskId);
    await expect(page.getByText("snapshot unavailable — retrying")).toBeVisible();
    await expect(page.getByText("live")).not.toBeVisible();

    await page.unroute("**/api/events/snapshot**");
    await expect(page.getByText("survives the outage")).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("live")).toBeVisible({ timeout: 15000 });
  });

  test("revoked access ends the stream honestly instead of retrying forever", async ({
    page,
    context,
  }) => {
    const token = await signIn(context);
    const taskId = await seedTask(token);
    const sessionId = await seedSession(token, taskId);
    await postMessage(token, sessionId, "message", "before revocation");

    await openSessionStream(page, taskId);
    await expect(page.getByText("before revocation")).toBeVisible();

    // revoke: snapshot starts answering 403 (the socket's own error is
    // opaque to EventSource — the probe classifies terminal)
    await page.route("**/api/events/snapshot**", (route) =>
      route.fulfill({ status: 403, body: "forbidden" }),
    );
    await page.route("**/api/events/stream**", (route) =>
      route.fulfill({ status: 403, body: "forbidden" }),
    );

    // force the bounded connection to drop: the e2e server bounds streams
    // (STUDIO_EVENT_MAX_SECONDS=2) so the socket cycles on its own; on the
    // next reconnect the 403 stream close triggers a classified probe
    await expect(page.getByText("access revoked")).toBeVisible({ timeout: 20000 });
    await expect(page.getByText("access to this session was revoked")).toBeVisible();
    await expect(page.getByText("before revocation")).not.toBeVisible();
    await expect(page.getByText("live")).not.toBeVisible();
  });

  test("task stream outage shows reconnecting, then resyncs run state", async ({
    page,
    context,
  }) => {
    const token = await signIn(context);
    const taskId = await seedTask(token);
    const run = await gql(
      token,
      `mutation ($t: ID!) { runs { request(input: { taskId: $t, kind: "verify",
         request: { probe: true } }) { run { id status } errors { code message } } } }`,
      { t: taskId },
    );
    expect(run.data.runs.request.errors).toEqual([]);

    await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
    await page.getByRole("button", { name: "runs" }).click();
    await expect(
      page.locator('ul[aria-label="task runs"] li').first(),
    ).toContainText("requested");
    await expect(page.getByText("live")).toBeVisible({ timeout: 15000 });

    // stream-layer outage (queries still work): the badge must go honest —
    // never claim live while the channel is down — then recover on its own
    await page.route("**/api/events/stream**", (route) => route.abort());
    await expect(page.getByText("reconnecting…")).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("live")).not.toBeVisible();
    await page.unroute("**/api/events/stream**");
    await expect(page.getByText("live")).toBeVisible({ timeout: 15000 });
    await expect(
      page.locator('ul[aria-label="task runs"] li').first(),
    ).toContainText("requested");
  });
});
