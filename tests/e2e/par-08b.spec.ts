import { expect, test } from "@playwright/test";

import { gql, signIn } from "./at-1103-helpers";

async function seedTask(token: string): Promise<string> {
  const proj = await gql(
    token,
    `mutation { projectCreate(input: {slug: "cmp-${Date.now() % 100000}", name: "Cmp"}) {
       project { id } errors { code message } } }`,
  );
  const projectId = proj.data.projectCreate.project.id as string;
  const task = await gql(
    token,
    `mutation ($p: ID!) { taskCreate(input: {
       projectId: $p, title: "composer task", mode: "improve",
       objective: "compose" }) {
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

async function openResearch(page: import("@playwright/test").Page, taskId: string) {
  await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
  await page.getByRole("button", { name: "research" }).click();
  await page.locator("details summary").first().click();
}

test.describe("PAR-08b research composer", () => {
  test("send through the UI persists the question and reports unavailable honestly", async ({
    page,
    context,
  }) => {
    const token = await signIn(context);
    const taskId = await seedTask(token);
    await seedSession(token, taskId);

    await openResearch(page, taskId);
    await page.getByLabel("ask the research agent").fill("what evidence exists?");
    await page.getByRole("button", { name: "send" }).click();

    // the user message is durable in the stream; no model is running in
    // e2e, so the honest outcome surfaces instead of a fake reply
    await expect(page.getByText("what evidence exists?")).toBeVisible();
    await expect(page.getByText(/model unavailable/)).toBeVisible({ timeout: 15000 });
    await expect(
      page.locator('ul[aria-label="session messages"] li[data-role="assistant"]'),
    ).toHaveCount(0);
  });

  test("cancel affordance records a durable cancel marker", async ({ page, context }) => {
    const token = await signIn(context);
    const taskId = await seedTask(token);
    await seedSession(token, taskId);

    await openResearch(page, taskId);

    // delay only the turn request (real request continues; the marker
    // mutation must pass unimpeded)
    await page.route("**/graphql", async (route) => {
      const body = route.request().postData() ?? "";
      if (body.includes("turnRequest")) {
        await new Promise((r) => setTimeout(r, 3000));
      }
      await route.continue();
    });

    await page.getByLabel("ask the research agent").fill("slow question");
    await page.getByRole("button", { name: "send" }).click();
    const cancelBtn = page.getByRole("button", { name: "cancel turn" });
    await expect(cancelBtn).toBeVisible();
    await cancelBtn.click();
    await expect(page.getByRole("button", { name: "cancel requested…" })).toBeVisible();

    // the cancel marker is a durable user-kind session record in the
    // stream (the button also carries "cancel requested…" — scope to li)
    await expect(
      page.locator('ul[aria-label="session messages"] li[data-kind="message"]', {
        hasText: "cancel requested",
      }),
    ).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/model unavailable/)).toBeVisible({ timeout: 15000 });
  });
});
