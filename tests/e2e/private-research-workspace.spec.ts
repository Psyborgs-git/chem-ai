import { createServer, type Server } from "node:http";
import { randomUUID } from "node:crypto";
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { decodeGlobalId, gql, signIn } from "./at-1103-helpers";

async function choose(page: Page, label: string, option: string) {
  if (label === "Training or evaluation track" && !await page.getByRole("combobox", { name: label, exact: true }).isVisible()) {
    await page.getByText("More training options", { exact: true }).click();
  }
  await page.getByRole("combobox", { name: label, exact: true }).click();
  await expect(page.getByRole("listbox")).toBeVisible();
  if (["Agent model", "Training or evaluation track"].includes(label)) {
    await page.getByRole("listbox").evaluate(async (node) => { await Promise.all(node.getAnimations().map((animation) => animation.finished.catch(() => undefined))); });
    await page.screenshot({ path: test.info().outputPath(`${label.toLowerCase().replaceAll(" ", "-")}-options.png`) });
  }
  await page.getByRole("option", { name: option, exact: true }).click();
}

async function workbenchScreenshots(page: Page, info: TestInfo, name: string) {
  await page.setViewportSize({ width: 1280, height: 900 });
  const changeTheme = async (theme: "light" | "dark") => {
    const toggle = page.getByRole("button", { name: `Switch to ${theme} theme` });
    if (!await toggle.count()) return;
    const expanded = await page.getByRole("button", { name: "Collapse chat", exact: true }).count();
    if (expanded) await page.getByRole("button", { name: "Collapse chat", exact: true }).click();
    await toggle.click();
    if (expanded) await page.getByRole("button", { name: "Expand chat", exact: true }).click();
  };
  await changeTheme("light");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.screenshot({ animations: "disabled", path: info.outputPath(`${name}-light.png`), fullPage: true });
  await changeTheme("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({ animations: "disabled", path: info.outputPath(`${name}-dark.png`), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  if (await page.locator("#research-agent").isVisible()) {
    expect(await page.locator("#research-agent").getByRole("button", { name: "Send", exact: true }).evaluate((node) => parseFloat(getComputedStyle(node).fontSize))).toBeGreaterThanOrEqual(14);
    await page.locator("#research-agent").screenshot({ animations: "disabled", path: info.outputPath(`${name}-narrow.png`) });
  } else await page.screenshot({ animations: "disabled", path: info.outputPath(`${name}-narrow.png`), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await changeTheme("light");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.setViewportSize({ width: 390, height: 844 });
  if (await page.locator("#research-agent").isVisible()) await page.locator("#research-agent").screenshot({ animations: "disabled", path: info.outputPath(`${name}-narrow-light.png`) });
  else await page.screenshot({ animations: "disabled", path: info.outputPath(`${name}-narrow-light.png`), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
}

test("private notes autosave, render formulae, and retain source-linked memory", async ({ page, context }) => {
  await signIn(context);
  const name = `Research notebook ${randomUUID()}`;
  await page.goto("/notebooks");
  await page.getByRole("button", { name: "New notebook", exact: true }).click();
  await page.getByLabel("Notebook title", { exact: true }).fill(name);
  await page.getByRole("button", { name: "Create notebook", exact: true }).click();
  await page.getByRole("button", { name: "Add first page" }).click();
  await page.getByLabel("Page title", { exact: true }).fill("Ethanol observations");
  await page.getByLabel("Notes · Markdown and $LaTeX$ supported", { exact: true }).fill("# Solvent notes\nKeep the original source.\n\nConcentration: $c=n/V$.");
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Page title", { exact: true })).toHaveValue("Ethanol observations");
  await page.getByRole("button", { name: "Preview", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Solvent notes" })).toBeVisible();
  await expect(page.locator(".katex")).toBeVisible();
  await page.screenshot({ animations: "disabled", path: test.info().outputPath("notebook-formula.png"), fullPage: true });
  await choose(page, "New page kind", "Recipe");
  await page.getByRole("button", { name: "Add page", exact: true }).click();
  await page.getByRole("button", { name: "Add ingredient" }).click();
  await page.getByLabel("Ingredient 1 name").fill("Ethanol");
  await page.getByLabel("Ingredient 1 amount").fill("10");
  await page.getByLabel("Ingredient 1 unit").fill("mL");
  await page.getByLabel("Procedure · one step per line").fill("Record the batch.\nMeasure the solvent.");
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible();
  await page.goto("/memory");
  const finding = `Use the retained source ${randomUUID()}`;
  await page.getByRole("button", { name: "Add memory", exact: true }).click();
  await page.getByLabel("Title", { exact: true }).fill(finding);
  await page.getByLabel("Finding, decision, or question").fill("Repeat the measurement before drawing a conclusion.");
  await page.getByRole("button", { name: "Remember", exact: true }).click();
  await expect(page.getByRole("heading", { name: finding })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: finding })).toBeVisible();
  await page.getByRole("region", { name: "Memory details", exact: true }).getByRole("button", { name: "More", exact: true }).click();
  await page.getByRole("menuitem", { name: "Forget", exact: true }).click();
  await expect(page.getByRole("heading", { name: finding })).toHaveCount(0);
});

test("SMILES dataset import exposes rejected rows and freezes leakage-aware partitions", async ({ page, context }) => {
  await signIn(context);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/learning");
  await expect(page.locator('[data-slot="tabs"]').filter({ has: page.getByRole("tablist", { name: "Local learning", exact: true }) })).toHaveCSS("flex-direction", "column");
  await page.getByRole("tab", { name: "Datasets", exact: true }).click();
  const name = `Property data ${randomUUID()}`;
  await page.getByLabel("File · CSV, JSONL, SDF, or SMILES").setInputFiles({ name: "structures.csv", mimeType: "text/csv", buffer: Buffer.from("smiles,target\nCCO,1\nCCN,2\nc1ccccc1,3\nC1CCCCC1,4\nC1CCOC1,5\ninvalid,6\nCCO,1\n") });
  await page.getByLabel("Dataset name", { exact: true }).fill(name);
  await page.getByText("Source and rights", { exact: true }).click();
  await choose(page, "Data origin", "Computed");
  await choose(page, "Training rights", "I own this data");
  await page.getByRole("button", { name: "Import and validate" }).click();
  const record = page.locator("article.cs-learning-data-row").filter({ hasText: name });
  await expect(record).toContainText("5 rows");
  await expect(record).toContainText("computed");
  await record.getByRole("button", { name: "Freeze" }).click();
  await expect(record).toContainText("frozen");
  await page.getByRole("tab", { name: "New run", exact: true }).click();
  await choose(page, "Training or evaluation track", "SMILES property model");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("combobox", { name: "Frozen dataset", exact: true }).click();
  await expect(page.getByRole("option", { name: `${name} · 5 rows`, exact: true })).toHaveCount(1);
  await page.keyboard.press("Escape");
  await page.reload();
  await page.getByRole("tab", { name: "Datasets", exact: true }).click();
  await expect(page.getByRole("button").filter({ hasText: name }).first()).toBeVisible();
  await page.getByRole("tab", { name: "New run", exact: true }).click();
  await choose(page, "Training or evaluation track", "SMILES property model");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await choose(page, "Frozen dataset", `${name} · 5 rows`);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByLabel("Maximum epochs")).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Device", exact: true })).toBeHidden();
  await workbenchScreenshots(page, test.info(), "learning-settings-basic");
  await page.getByText("Advanced settings", { exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Device", exact: true })).toBeVisible();
  await expect(page.getByText("Fixed schedule · 2 warm-up epochs", { exact: true })).toBeVisible();
  await workbenchScreenshots(page, test.info(), "learning-settings-advanced");
});

test("sidebar uses a second model on one provider and persists a real tool action", async ({ page, context }) => {
  test.setTimeout(90_000);
  const token = await signIn(context);
  const notebookTitle = `Agent created ${randomUUID()}`;
  const providerName = `Sidebar fixture ${randomUUID()}`;
  const calls: string[] = [];
  let failure: string | null = null;
  const server: Server = createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk: Buffer) => chunks.push(chunk));
    request.on("end", () => {
      response.setHeader("content-type", "application/json");
      try {
        const body = JSON.parse(Buffer.concat(chunks).toString("utf8")); calls.push(body.model);
        const toolResult = body.messages.find((message: { role: string }) => message.role === "tool");
        response.end(JSON.stringify({ choices: [{ message: toolResult ? { role: "assistant", content: "The private notebook was saved successfully." } : { role: "assistant", content: null, tool_calls: [{ id: "create-notebook-1", type: "function", function: { name: "create_notebook", arguments: JSON.stringify({ title: notebookTitle }) } }] } }], usage: { prompt_tokens: 40, completion_tokens: 15 } }));
      } catch (error) { failure = String(error); response.statusCode = 500; response.end("{}"); }
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address(); if (!address || typeof address === "string") throw new Error("Fixture missing port");
  let providerId: string | undefined;
  try {
    const created = await gql(token, `mutation($input:InferenceProviderSaveInput!){providers{save(input:$input){provider{id revision}errors{message}}}}`, { input: { name: providerName, kind: "openai_compatible", baseUrl: `http://127.0.0.1:${address.port}/v1`, model: "first-model", enabled: true, supportsTools: true } });
    expect(created.data.providers.save.errors).toEqual([]);
    providerId = created.data.providers.save.provider.id;
    const id = /^[0-9a-f-]{36}$/i.test(providerId!) ? providerId! : decodeGlobalId(providerId!);
    const saved = await context.request.post(`/api/agent-workspace/providers/${id}/models`, { data: { modelId: "second-model", label: "Second model", roles: ["planner"], supportsTools: true, enabled: true } });
    expect(saved.ok()).toBe(true);
    await page.goto("/notebooks");
    await page.getByRole("button", { name: "Open research agent" }).click();
    await expect(page.getByRole("region", { name: "Chat history", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "New chat", exact: true }).click();
    await choose(page, "Agent model", `Second model · ${providerName}`);
    await expect(page.getByLabel("Message research agent")).toHaveCSS("border-top-width", "0px");
    await expect(page.getByRole("combobox", { name: "Agent model", exact: true })).toHaveAttribute("data-slot", "select-trigger");
    expect(await page.getByRole("combobox", { name: "Agent model", exact: true }).evaluate((node) => node.tagName)).toBe("BUTTON");
    const promptEnd = "End of the complete research brief.";
    const prompt = `Create a private notebook named ${notebookTitle}.\n\n${"Keep source provenance and separate observations from hypotheses.\n".repeat(15)}${promptEnd}`;
    await page.getByLabel("Message research agent").fill(prompt);
    await page.getByRole("button", { name: "Send", exact: true }).click();
    const transcript = page.getByRole("log", { name: "Agent conversation messages" });
    await expect(transcript).toContainText("The private notebook was saved successfully.", { timeout: 30_000 });
    await expect(transcript).not.toContainText(promptEnd);
    await transcript.getByRole("button", { name: "Show full message", exact: true }).click();
    await expect(transcript).toContainText(promptEnd);
    await transcript.getByRole("button", { name: "Collapse message", exact: true }).click();
    const activity = transcript.locator(".cs-chat-trace");
    await expect(activity).toHaveCount(1);
    const activityTrigger = activity.getByRole("button", { name: "Research activity · 1 step", exact: true });
    await expect(activityTrigger).toHaveAttribute("aria-expanded", "false");
    await expect(activity.getByRole("button", { name: "Create notebook — technical details", exact: true })).toHaveCount(0);
    await activityTrigger.click();
    await activity.getByRole("button", { name: "Create notebook — technical details", exact: true }).click();
    await expect(activity.locator("pre")).toContainText(notebookTitle);
    await activityTrigger.click();
    await expect(activity.locator("pre")).toHaveCount(0);
    await expect(page.getByRole("button", { name: notebookTitle, exact: true })).toBeVisible();
    const contentRight = await page.locator("main").evaluate((node) => node.getBoundingClientRect().right);
    const panelLeft = await page.locator("#research-agent").evaluate((node) => node.getBoundingClientRect().left);
    expect(contentRight).toBeLessThanOrEqual(panelLeft + 1);
    await page.screenshot({ animations: "disabled", path: test.info().outputPath("agent-sidebar.png"), fullPage: true });
    expect(failure).toBeNull(); expect(calls).toEqual(["second-model", "second-model"]);
    await workbenchScreenshots(page, test.info(), "agent-workbench");
    await page.getByRole("button", { name: "Agent settings", exact: true }).click();
    const settings = page.getByRole("dialog", { name: "Chat settings", exact: true });
    await expect(settings).toHaveAttribute("data-slot", "dialog-content");
    await expect(settings.locator('[data-slot="tabs"]')).toHaveCSS("flex-direction", "column");
    for (const width of [1280, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      for (const name of ["General", "Autopilot", "Schedule"]) {
        await settings.getByRole("tab", { name, exact: true }).click();
        await expect(settings.getByRole("tab", { name, exact: true })).toHaveAttribute("aria-selected", "true");
        const tabBottom = await settings.getByRole("tablist").evaluate((node) => node.getBoundingClientRect().bottom);
        const panelTop = await settings.getByRole("tabpanel", { name, exact: true }).evaluate((node) => node.getBoundingClientRect().top);
        expect(tabBottom).toBeLessThanOrEqual(panelTop + 1);
        for (const inactivePanel of await settings.locator('[data-slot="tabs-content"][hidden]').all()) await expect(inactivePanel).toBeHidden();
        const control = name === "General" ? settings.getByRole("combobox", { name: "Agent role", exact: true }) : name === "Autopilot" ? settings.getByRole("spinbutton", { name: "Compute hours/day", exact: true }) : settings.getByRole("textbox", { name: "Research goal", exact: true });
        const controlRight = await control.evaluate((node) => node.getBoundingClientRect().right);
        const dialogRight = await settings.evaluate((node) => node.getBoundingClientRect().right);
        expect(controlRight).toBeLessThanOrEqual(dialogRight - 1);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
        await page.screenshot({ animations: "disabled", path: test.info().outputPath(`agent-settings-${name.toLowerCase()}-${width}.png`), fullPage: true });
      }
    }
    await settings.getByRole("button", { name: "Close", exact: true }).click();
    await expect(settings).toHaveCount(0);
    expect(calls).toEqual(["second-model", "second-model"]);
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.getByRole("button", { name: "Close agent", exact: true }).click();
    await page.reload();
    await expect(page.getByRole("button", { name: notebookTitle, exact: true })).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("button", { name: "Open research agent" }).click();
    await expect(page.getByRole("complementary", { name: "Research agent" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ animations: "disabled", path: test.info().outputPath("agent-mobile.png"), fullPage: true });
  } finally {
    if (providerId) { const state = await gql(token, "query{inferenceProviders{id revision}}"); const row = state.data.inferenceProviders.find((provider: { id: string }) => provider.id === providerId); if (row) await gql(token, "mutation($id:ID!,$revision:Int!){providers{delete(input:{id:$id,expectedRevision:$revision}){deleted errors{message}}}}", { id: providerId, revision: row.revision }); }
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

test("chat history searches older message bodies, switches sessions, and restores selection without inference", async ({ page, context }) => {
  test.setTimeout(90_000);
  const token = await signIn(context);
  const titleA = `Fibre measurements ${randomUUID()}`;
  const titleB = `Yarn construction ${randomUUID()}`;
  const bodyOnlyTerm = `archived-${randomUUID()}`;
  const calls: string[] = [];
  let failure: string | null = null;
  const server: Server = createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk: Buffer) => chunks.push(chunk));
    request.on("end", () => {
      response.setHeader("content-type", "application/json");
      try {
        const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        calls.push(body.model);
        response.end(JSON.stringify({ choices: [{ message: { role: "assistant", content: `Saved research response ${calls.length}.\n\n${"Retain source provenance and distinguish measured observations from hypotheses.\n\n".repeat(24)}` } }], usage: { prompt_tokens: 40, completion_tokens: 15 } }));
      } catch (error) { failure = String(error); response.statusCode = 500; response.end("{}"); }
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Fixture missing port");
  let providerId: string | undefined;
  try {
    const created = await gql(token, `mutation($input:InferenceProviderSaveInput!){providers{save(input:$input){provider{id revision}errors{message}}}}`, { input: { name: `History fixture ${randomUUID()}`, kind: "openai_compatible", baseUrl: `http://127.0.0.1:${address.port}/v1`, model: "history-model", enabled: true, supportsTools: true } });
    expect(created.data.providers.save.errors).toEqual([]);
    providerId = created.data.providers.save.provider.id;
    const id = /^[0-9a-f-]{36}$/i.test(providerId!) ? providerId! : decodeGlobalId(providerId!);
    const makeThread = async (title: string) => {
      const response = await context.request.post("/api/agent-workspace/threads", { data: { title } });
      expect(response.ok()).toBe(true);
      return (await response.json()).id as string;
    };
    const run = async (threadId: string, message: string) => {
      const response = await context.request.post(`/api/agent-workspace/threads/${threadId}/runs`, { data: { providerId: id, modelId: "history-model", role: "planner", message } });
      expect(response.ok()).toBe(true);
      const job = await response.json();
      await expect.poll(async () => {
        const status = await context.request.get(`/api/agent-workspace/runs/${job.id}`);
        expect(status.ok()).toBe(true);
        return (await status.json()).status;
      }, { timeout: 30_000, message: "The isolated mock-provider run should finish" }).toBe("completed");
    };
    const threadA = await makeThread(titleA);
    await run(threadA, `Retain this earlier observation for future research: ${bodyOnlyTerm}.`);
    await run(threadA, "Review the measurement protocol before the next experiment.");
    const threadB = await makeThread(titleB);
    await run(threadB, "Compare yarn geometry with the retained reference material.");
    expect(calls).toEqual(["history-model", "history-model", "history-model"]);

    const searchResponse = await context.request.get(`/api/agent-workspace/threads?q=${encodeURIComponent(bodyOnlyTerm)}&offset=0&limit=50`);
    expect(searchResponse.ok()).toBe(true);
    expect(searchResponse.headers()["cache-control"]).toBe("no-store");
    const search = await searchResponse.json();
    expect(search.threads.map((thread: { id: string }) => thread.id)).toEqual([threadA]);
    expect(search.threads[0].title).not.toContain(bodyOnlyTerm);
    expect(search.threads[0].lastMessagePreview).not.toContain(bodyOnlyTerm);
    expect(search.threads[0].messageCount).toBe(4);

    // Exercise actual backend cursor pagination with this small real thread.
    // Only the initial page size changes; no response body or older page is mocked.
    await page.route(`**/api/agent-workspace/threads/${threadA}*`, async (route) => {
      const url = new URL(route.request().url());
      if (route.request().method() === "GET" && url.pathname === `/api/agent-workspace/threads/${threadA}` && !url.searchParams.has("before")) {
        url.searchParams.set("limit", "2");
        await route.continue({ url: url.href });
      } else await route.continue();
    });

    const navigationMutations: string[] = [];
    page.on("request", (request) => {
      const path = new URL(request.url()).pathname;
      if (request.method() === "POST" && path.startsWith("/api/agent-workspace/threads")) navigationMutations.push(path);
    });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/notebooks");
    await page.getByRole("button", { name: "Open research agent" }).click();
    const history = page.getByRole("region", { name: "Chat history", exact: true });
    await expect(history).toBeVisible();
    await expect(history.getByRole("button", { name: `Open chat: ${titleA}`, exact: true })).toBeVisible();
    await expect(history.getByRole("button", { name: `Open chat: ${titleB}`, exact: true })).toBeVisible();
    const searched = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === "/api/agent-workspace/threads" && url.searchParams.get("q") === bodyOnlyTerm && response.ok();
    });
    await history.getByRole("searchbox", { name: "Search chats" }).fill(bodyOnlyTerm);
    await searched;
    await expect(history.getByRole("button", { name: `Open chat: ${titleA}`, exact: true })).toBeVisible();
    await expect(history.getByRole("button", { name: `Open chat: ${titleB}`, exact: true })).toHaveCount(0);
    await history.getByRole("button", { name: `Open chat: ${titleA}`, exact: true }).click();
    const current = page.getByRole("region", { name: "Current chat", exact: true });
    await expect(current.getByRole("heading", { name: titleA, exact: true })).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(current.getByRole("log")).not.toContainText(bodyOnlyTerm);
    const scrollArea = current.getByLabel("Conversation scroll area", { exact: true });
    await scrollArea.hover();
    await page.mouse.wheel(0, -10000);
    const older = current.getByRole("button", { name: "Load earlier messages", exact: true });
    await expect(older).toBeVisible();
    await older.scrollIntoViewIfNeeded();
    await expect.poll(() => scrollArea.evaluate((node) => node.scrollTop)).toBeLessThan(1);
    await scrollArea.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    const readingAnchor = current.getByText("Review the measurement protocol before the next experiment.", { exact: true });
    const anchorBefore = await readingAnchor.evaluate((node) => node.getBoundingClientRect().top);
    const earlierPage = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === `/api/agent-workspace/threads/${threadA}` && url.searchParams.has("before") && url.searchParams.get("limit") === "500" && response.ok();
    });
    await older.click();
    await earlierPage;
    await expect(current.getByRole("log")).toContainText(bodyOnlyTerm);
    await expect.poll(async () => Math.abs(await readingAnchor.evaluate((node) => node.getBoundingClientRect().top) - anchorBefore), { message: "Prepending the real older page should preserve the reader's message position at 390px" }).toBeLessThan(8);
    await page.screenshot({ animations: "disabled", path: test.info().outputPath("agent-history-mobile-prepend-position.png"), fullPage: true });
    await page.setViewportSize({ width: 1280, height: 900 });
    await expect(current.getByRole("log")).toContainText("Saved research response 2.");
    await page.getByRole("button", { name: "History", exact: true }).click();
    await history.getByRole("searchbox", { name: "Search chats" }).fill("");
    await history.getByRole("button", { name: `Open chat: ${titleB}`, exact: true }).click();
    await expect(current.getByRole("heading", { name: titleB, exact: true })).toBeVisible();
    await expect(current.getByRole("log")).toContainText("Saved research response 3.");
    await expect(current.getByRole("log")).not.toContainText(bodyOnlyTerm);
    const selectionKey = `studio.agent.activeThread:${search.ownerScope}`;
    await expect.poll(() => page.evaluate((key) => localStorage.getItem(key), selectionKey)).toBe(threadB);
    await page.reload();
    await page.getByRole("button", { name: "Open research agent" }).click();
    await expect(current.getByRole("heading", { name: titleB, exact: true })).toBeVisible();
    await expect(current.getByRole("log")).toContainText("Saved research response 3.");
    await page.getByRole("button", { name: "Expand chat", exact: true }).click();
    await expect(history).toBeVisible();
    await expect(current).toBeVisible();
    await expect(history.getByRole("button", { name: `Open chat: ${titleB}`, exact: true })).toHaveAttribute("aria-current", "page");
    await workbenchScreenshots(page, test.info(), "agent-history-workspace");
    await page.getByRole("button", { name: "New chat", exact: true }).click();
    await expect(current.getByRole("heading", { name: "New chat", exact: true })).toBeVisible();
    await expect(current.getByRole("log")).not.toContainText("Saved research response");
    await expect(current.getByLabel("Message research agent")).toHaveValue("");
    await expect.poll(() => page.evaluate((key) => localStorage.getItem(key), selectionKey)).toBeNull();
    const ids = await context.request.get("/api/agent-workspace/threads?offset=0&limit=100");
    expect((await ids.json()).threads.filter((thread: { id: string }) => [threadA, threadB].includes(thread.id))).toHaveLength(2);
    expect(failure).toBeNull();
    expect(calls).toEqual(["history-model", "history-model", "history-model"]);
    expect(navigationMutations).toEqual([]);
  } finally {
    if (providerId) { const state = await gql(token, "query{inferenceProviders{id revision}}"); const row = state.data.inferenceProviders.find((provider: { id: string }) => provider.id === providerId); if (row) await gql(token, "mutation($id:ID!,$revision:Int!){providers{delete(input:{id:$id,expectedRevision:$revision}){deleted errors{message}}}}", { id: providerId, revision: row.revision }); }
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

test("Downloads retains uploaded originals and exports citation metadata", async ({ page, context }) => {
  await signIn(context);
  await page.goto("/downloads");
  const title = `review-${randomUUID()}.txt`;
  const original = "Original research note for future human review.\n";
  await page.getByLabel("Retain a paper, dataset, or reference file").setInputFiles({ name: title, mimeType: "text/plain", buffer: Buffer.from(original) });
  const details = page.getByRole("region", { name: "Source details" });
  await expect(details.getByRole("heading", { name: title })).toBeVisible();
  const href = await details.getByRole("link", { name: "Download original" }).getAttribute("href");
  const retained = await context.request.get(href!);
  expect(retained.ok()).toBe(true); expect(await retained.text()).toBe(original);
  const exported = page.waitForEvent("download");
  await details.getByRole("button", { name: "Cite", exact: true }).click();
  await page.getByRole("menuitem", { name: "Export citation", exact: true }).click();
  expect((await exported).suggestedFilename()).toBe("citation.json");
  await page.reload();
  await expect(page.getByRole("button", { name: title, exact: true })).toBeVisible();
  await page.getByRole("button", { name: title, exact: true }).click();
  await workbenchScreenshots(page, test.info(), "downloads-inspector");
  await page.screenshot({ animations: "disabled", path: test.info().outputPath("downloads-library.png"), fullPage: true });
});

test("Home shortcuts, secondary navigation and workspace search preserve intent with accessible motion", async ({ page, context }) => {
  test.setTimeout(90_000);
  await signIn(context);
  const title = `Exact retained silk source ${randomUUID()}.txt`;
  const uploaded = await context.request.post("/api/library/sources/upload", { multipart: { title, file: { name: title, mimeType: "text/plain", buffer: Buffer.from("Retained source for navigation review, not a material-performance claim.\n") } } });
  expect(uploaded.ok()).toBe(true);
  const source = await uploaded.json();
  const mutations: string[] = [];
  page.on("request", (request) => {
    const pathname = new URL(request.url()).pathname;
    if (request.method() === "POST" && (/^\/api\/(?:learning-workspace|simulations)\/(?:jobs|preflight)/.test(pathname) || /^\/api\/agent-workspace\/threads(?:\/[^/]+\/runs)?$/.test(pathname) || pathname.includes("/preview"))) mutations.push(pathname);
  });
  await page.addInitScript(() => {
    const state = window as Window & { researchMotion?: { name: string; target: string }[] };
    state.researchMotion = [];
    document.addEventListener("animationstart", (event) => {
      if (event.target instanceof HTMLElement && event.target.matches(".cs-route-content, .cs-agent-panel")) state.researchMotion!.push({ name: event.animationName, target: event.target.className });
    });
  });
  const motion = () => page.evaluate(() => (window as Window & { researchMotion?: { name: string; target: string }[] }).researchMotion ?? []);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your research", exact: true })).toBeVisible();
  const navigation = page.getByRole("navigation", { name: "primary", exact: true });
  await expect(navigation.locator(".cs-nav-primary").getByRole("link")).toHaveCount(5);
  await expect(navigation.getByRole("button", { name: "More", exact: true })).toHaveAttribute("aria-expanded", "false");
  await expect(navigation.getByRole("link", { name: "Downloads", exact: true })).toBeHidden();
  await workbenchScreenshots(page, test.info(), "apple-home");
  await page.getByRole("button", { name: "Explore molecule", exact: true }).click();
  await expect(page.locator("#quick-structure")).toBeFocused();
  await page.locator("#quick-structure").fill("CCO");
  await page.getByRole("button", { name: "Close molecule explorer", exact: true }).click();
  await expect(page.getByRole("region", { name: "Molecule explorer", exact: true })).toBeHidden();
  await page.getByRole("link", { name: "New notebook", exact: true }).click();
  await expect(page.locator(".cs-inline-create").getByLabel("Notebook title", { exact: true })).toBeFocused();
  await expect(page.locator(".cs-inline-create").getByLabel("Notebook title", { exact: true })).toHaveValue("");
  await expect(page.getByRole("button", { name: "Create notebook", exact: true })).toBeVisible();
  await navigation.getByRole("link", { name: "Home", exact: true }).click();
  await page.getByRole("link", { name: "Find papers", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Search resources", exact: true })).toBeFocused();
  await navigation.getByRole("link", { name: "Home", exact: true }).click();
  const beforeRoute = (await motion()).filter((item) => item.name === "cs-route-arrive").length;
  await page.getByRole("link", { name: "Train model", exact: true }).click();
  await expect(page.getByRole("tab", { name: "New run", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "Choose a task", exact: true })).toBeVisible();
  await expect.poll(async () => (await motion()).filter((item) => item.name === "cs-route-arrive").length).toBeGreaterThan(beforeRoute);
  await page.getByRole("button", { name: /Train a property model/ }).click();
  await expect(page.getByRole("heading", { name: "Choose training data", exact: true })).toBeVisible();
  expect(mutations).toEqual([]);

  await navigation.getByRole("button", { name: "More", exact: true }).click();
  await expect(navigation.getByRole("link", { name: "Downloads", exact: true })).toBeVisible();
  await navigation.getByRole("link", { name: "Downloads", exact: true }).click();
  await expect(navigation.getByRole("link", { name: "Downloads", exact: true })).toHaveAttribute("aria-current", "page");
  await navigation.getByRole("button", { name: "More", exact: true }).click();
  await expect(navigation.getByRole("link", { name: "Downloads", exact: true })).toBeHidden();
  await page.reload();
  await expect(navigation.getByRole("button", { name: "More", exact: true })).toHaveAttribute("aria-expanded", "true");
  await expect(navigation.getByRole("link", { name: "Downloads", exact: true })).toBeVisible();
  await workbenchScreenshots(page, test.info(), "apple-secondary-navigation");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation", exact: true }).click();
  await expect(navigation.getByRole("link", { name: "Downloads", exact: true })).toBeVisible();
  await page.screenshot({ animations: "disabled", path: test.info().outputPath("apple-secondary-navigation-mobile-open.png"), fullPage: true });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Open navigation", exact: true })).toBeFocused();
  await page.setViewportSize({ width: 1280, height: 900 });
  await navigation.getByRole("link", { name: "Home", exact: true }).click();

  await page.keyboard.press("ControlOrMeta+k");
  const finder = page.getByRole("dialog", { name: "Find your work", exact: true });
  await expect(finder).toBeVisible();
  const locationBeforeSearch = page.url();
  await finder.getByRole("combobox", { name: "Search your workspace", exact: true }).fill(title);
  const exactSource = finder.getByRole("option").filter({ hasText: title });
  await expect(exactSource).toHaveCount(1);
  await expect(exactSource).toContainText("Saved source");
  expect(page.url()).toBe(locationBeforeSearch);
  for (const theme of ["light", "dark"] as const) {
    await page.keyboard.press("Escape");
    const toggle = page.getByRole("button", { name: `Switch to ${theme} theme`, exact: true });
    if (await toggle.count()) await toggle.click();
    await page.keyboard.press("ControlOrMeta+k");
    await finder.getByRole("combobox", { name: "Search your workspace", exact: true }).fill(title);
    await expect(exactSource).toHaveCount(1);
    await page.screenshot({ animations: "disabled", path: test.info().outputPath(`apple-workspace-palette-${theme}.png`), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ animations: "disabled", path: test.info().outputPath(`apple-workspace-palette-${theme}-390.png`), fullPage: true });
    await page.setViewportSize({ width: 1280, height: 900 });
  }
  const selected = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/library/sources/${source.id}` && response.ok());
  await exactSource.click();
  await selected;
  await expect(finder).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Source details", exact: true }).getByRole("heading", { name: title, exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Open research agent", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Research agent", exact: true })).toBeVisible();
  await expect.poll(async () => (await motion()).some((item) => item.name === "cs-chat-open")).toBe(true);
  await page.getByRole("button", { name: "Close agent", exact: true }).click();
  await expect.poll(async () => (await motion()).some((item) => item.name === "cs-chat-close")).toBe(true);
  await expect(page.locator("#research-agent")).toHaveCount(0);
  await page.emulateMedia({ reducedMotion: "reduce" });
  const beforeReduced = (await motion()).length;
  await navigation.getByRole("link", { name: "Home", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Your research", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Open research agent", exact: true }).click();
  await expect(page.locator("#research-agent")).toBeVisible();
  await expect(page.locator(".cs-route-content")).toHaveCSS("animation-name", "none");
  await expect(page.locator("#research-agent")).toHaveCSS("animation-name", "none");
  expect((await motion()).length).toBe(beforeReduced);
  expect(mutations).toEqual([]);
});
