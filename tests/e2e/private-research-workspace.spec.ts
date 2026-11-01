import { createServer, type Server } from "node:http";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { decodeGlobalId, gql, signIn } from "./at-1103-helpers";

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
  await expect(page.getByRole("status").filter({ hasText: "Saved · revision" })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Page title", { exact: true })).toHaveValue("Ethanol observations");
  await page.getByRole("button", { name: "Preview", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Solvent notes" })).toBeVisible();
  await expect(page.locator(".katex")).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("notebook-formula.png"), fullPage: true });
  await page.getByLabel("New page kind").selectOption("recipe");
  await page.getByRole("button", { name: "Add page", exact: true }).click();
  await page.getByRole("button", { name: "Add ingredient" }).click();
  await page.getByLabel("Ingredient 1 name").fill("Ethanol");
  await page.getByLabel("Ingredient 1 amount").fill("10");
  await page.getByLabel("Ingredient 1 unit").fill("mL");
  await page.getByLabel("Procedure · one step per line").fill("Record the batch.\nMeasure the solvent.");
  await expect(page.getByRole("status").filter({ hasText: "Saved · revision" })).toBeVisible();
  await page.goto("/memory");
  const finding = `Use the retained source ${randomUUID()}`;
  await page.getByLabel("Title", { exact: true }).fill(finding);
  await page.getByLabel("Finding, decision, or question").fill("Repeat the measurement before drawing a conclusion.");
  await page.getByRole("button", { name: "Remember", exact: true }).click();
  await expect(page.getByRole("heading", { name: finding })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: finding })).toBeVisible();
  await page.getByRole("button", { name: "Forget", exact: true }).last().click();
  await expect(page.getByRole("heading", { name: finding })).toHaveCount(0);
});

test("SMILES dataset import exposes rejected rows and freezes leakage-aware partitions", async ({ page, context }) => {
  await signIn(context);
  await page.goto("/learning");
  const name = `Property data ${randomUUID()}`;
  await page.getByLabel("File · CSV, JSONL, SDF, or SMILES").setInputFiles({ name: "structures.csv", mimeType: "text/csv", buffer: Buffer.from("smiles,target\nCCO,1\nCCN,2\nc1ccccc1,3\nC1CCCCC1,4\nC1CCOC1,5\ninvalid,6\nCCO,1\n") });
  await page.getByLabel("Dataset name", { exact: true }).fill(name);
  await page.getByLabel("Data origin").selectOption("computed");
  await page.getByRole("button", { name: "Import and validate" }).click();
  const record = page.locator("article").filter({ has: page.getByRole("heading", { name, exact: true }) });
  await expect(record).toContainText("5 accepted rows");
  await expect(record).toContainText("computed");
  await record.getByRole("button", { name: "Freeze snapshot" }).click();
  await expect(record).toContainText("frozen");
  await page.getByRole("tab", { name: "Train & evaluate" }).click();
  await expect(page.getByLabel("Frozen dataset").locator("option").filter({ hasText: name })).toHaveCount(1);
  await page.reload();
  await expect(page.getByRole("heading", { name, exact: true }).first()).toBeVisible();
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
    await page.getByLabel("Agent provider", { exact: true }).selectOption(id);
    await page.getByLabel("Agent model", { exact: true }).selectOption("second-model");
    await page.getByLabel("Message research agent").fill(`Create a private notebook named ${notebookTitle}.`);
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByRole("log", { name: "Agent conversation messages" })).toContainText("The private notebook was saved successfully.", { timeout: 30_000 });
    await expect(page.getByRole("button", { name: notebookTitle, exact: true })).toBeVisible();
    const contentRight = await page.locator("main").evaluate((node) => node.getBoundingClientRect().right);
    const panelLeft = await page.locator("#research-agent").evaluate((node) => node.getBoundingClientRect().left);
    expect(contentRight).toBeLessThanOrEqual(panelLeft + 1);
    await page.screenshot({ path: test.info().outputPath("agent-sidebar.png"), fullPage: true });
    expect(failure).toBeNull(); expect(calls).toEqual(["second-model", "second-model"]);
    await page.getByRole("button", { name: "Close agent", exact: true }).click();
    await page.reload();
    await expect(page.getByRole("button", { name: notebookTitle, exact: true })).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("button", { name: "Open research agent" }).click();
    await expect(page.getByRole("complementary", { name: "Research agent" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: test.info().outputPath("agent-mobile.png"), fullPage: true });
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
  await details.getByRole("button", { name: "Export citation", exact: true }).click();
  expect((await exported).suggestedFilename()).toBe("citation.json");
  await page.reload();
  await expect(page.getByRole("button", { name: title, exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("downloads-library.png"), fullPage: true });
});
