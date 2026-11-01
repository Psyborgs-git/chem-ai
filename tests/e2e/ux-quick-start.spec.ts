import { expect, test, type Request } from "@playwright/test";

import { gql, signIn } from "./at-1103-helpers";

function isOperation(request: Request, operation: string): boolean {
  if (request.method() !== "POST" || !request.url().includes("/graphql")) return false;
  try {
    const payload = request.postDataJSON() as { query?: string };
    return typeof payload.query === "string" && payload.query.includes(operation);
  } catch {
    return false;
  }
}

test("Home calculates CCO once, shows its actual drawing, and reloads the saved result", async ({ page, context }) => {
  test.setTimeout(90_000);
  const token = await signIn(context);
  let submissions = 0;
  page.on("request", (request) => {
    if (isOperation(request, "homeQuickCalculationMutation")) submissions += 1;
  });
  await page.goto("/");
  const explore = page.getByRole("button", { name: "Explore molecule", exact: true });
  await explore.click();
  await expect(explore).toHaveAttribute("aria-expanded", "true");
  const form = page.getByRole("form", { name: "Quick molecular calculation" });
  await expect(form).toBeVisible();
  await expect(form.getByLabel("Molecular structure", { exact: true })).toBeFocused();
  await expect(form.locator("[required]")).toHaveCount(1);
  await form.getByLabel("Molecular structure", { exact: true }).fill("CCO");
  const responsePromise = page.waitForResponse((response) => isOperation(response.request(), "homeQuickCalculationMutation"), { timeout: 70_000 });
  await form.getByRole("button", { name: "Calculate properties", exact: true }).click();
  const response = await responsePromise;
  const payload = await response.json();
  expect(payload.errors).toBeUndefined();
  const saved = payload.data.runs.quickDescribeStructure;
  expect(saved.errors).toEqual([]);
  expect(saved.run.status).toBe("succeeded");
  const runId = saved.run.id as string;
  const taskId = saved.run.taskId as string;

  await expect(page.locator(`[data-field="recent-tasks"] a[href="/tasks/${encodeURIComponent(taskId)}/overview"]`)).toBeVisible();
  const result = page.getByRole("region", { name: "Calculation result", exact: true });
  await expect(result.locator('[data-field="molecular-formula"]')).toHaveText("C2H6O");
  await expect(result.locator('[data-field="molecular-weight"]')).toContainText("46.069");
  const drawing = result.getByRole("img", { name: "Molecular structure of CCO", exact: true });
  await expect(drawing).toBeVisible();
  await expect(drawing).toHaveAttribute("src", /^data:image\/svg\+xml,/);
  await expect.poll(() => drawing.evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth > 0)).toBe(true);

  const persisted = await gql(token, `query($id: ID!) { node(id: $id) { ... on Run {
    id status taskId inputSummary resultSummary
  } } }`, { id: runId });
  const record = persisted.data.node;
  expect(record.id).toBe(runId);
  expect(record.inputSummary.smiles).toBe("CCO");
  expect(record.resultSummary.descriptors.mw).toBeCloseTo(46.069, 3);
  expect(record.resultSummary.structure.formula).toBe("C2H6O");
  expect(record.resultSummary.engine.id).toBe("rdkit");
  expect(record.resultSummary.engine.version).toBeTruthy();
  expect(record.resultSummary.evidence_type).toBe("descriptor");
  const imageSource = await drawing.getAttribute("src");
  expect(decodeURIComponent(imageSource!.slice(imageSource!.indexOf(",") + 1))).toBe(record.resultSummary.structure.depiction_svg);
  expect(submissions).toBe(1);
  await test.info().attach("home-real-molecule-result", { body: await result.screenshot(), contentType: "image/png" });

  await result.getByRole("link", { name: "Open full result", exact: true }).click();
  await expect.poll(() => decodeURIComponent(new URL(page.url()).pathname)).toBe(`/runs/${runId}`);
  const savedUrl = page.url();
  await page.reload();
  await expect(page).toHaveURL(savedUrl);
  await expect(page.getByRole("heading", { name: "Molecular calculation", exact: true })).toBeVisible();
  await expect(page.locator('[data-field="molecular-formula"]')).toHaveText("C2H6O");
  await expect(page.locator('[data-field="molecular-weight"]')).toContainText("46.069");
  await expect(page.getByRole("img", { name: "Molecular structure of CCO", exact: true })).toBeVisible();
  const runs = await gql(token, `query($task: ID!) { taskRuns(taskId: $task) { edges { node { id } } } }`, { task: taskId });
  expect(runs.data.taskRuns.edges.map((edge: { node: { id: string } }) => edge.node.id)).toEqual([runId]);
  expect(submissions).toBe(1);
});

test("Home starts Explore research with a title and activates it from the header", async ({ page, context }) => {
  const token = await signIn(context);
  const title = "UX explore molecule interactions";
  await page.goto("/");
  await page.getByRole("link", { name: /^(New research task|Start a research task)$/ }).click();
  const sheet = page.getByRole("dialog", { name: "Start a research task", exact: true });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole("radio", { name: "Explore", exact: true })).toBeChecked();
  const targetKind = sheet.getByRole("combobox", { name: "What are you exploring?" });
  await expect(targetKind).toHaveValue("molecule");
  await expect(targetKind.locator("option:checked")).toHaveText("A molecule");
  await expect(sheet.locator("[required]")).toHaveCount(1);
  await sheet.getByLabel("task title", { exact: true }).fill(title);
  const responsePromise = page.waitForResponse((response) => isOperation(response.request(), "tasksTaskCreateMutation"));
  await sheet.getByRole("button", { name: "Create task", exact: true }).click();
  const response = await responsePromise;
  const request = response.request().postDataJSON() as { variables: { input: { projectId?: string | null } } };
  expect(request.variables.input.projectId ?? null).toBeNull();
  const payload = await response.json();
  expect(payload.errors).toBeUndefined();
  expect(payload.data.taskCreate.errors).toEqual([]);
  const taskId = payload.data.taskCreate.task.id as string;
  await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
  const header = page.locator("header.cs-workbench-header");
  await expect(header.getByRole("link", { name: "Research inbox", exact: true })).toBeVisible();
  await expect(header.locator('[data-status="draft"]')).toBeVisible();
  const before = await gql(token, `query($id: ID!) { node(id: $id) { ... on Task {
    title mode targetKind objective workflowState project { name slug }
  } } }`, { id: taskId });
  expect(before.data.node).toMatchObject({ title, mode: "discover", targetKind: "molecule", objective: title, workflowState: "draft", project: { name: "Research inbox", slug: "research-inbox" } });
  await header.getByRole("button", { name: "Start task", exact: true }).click();
  await expect(header.locator('[data-status="active"]')).toBeVisible();
  await expect(header.getByRole("button", { name: "Start task", exact: true })).toHaveCount(0);
  const after = await gql(token, `query($id: ID!) { node(id: $id) { ... on Task { workflowState } } }`, { id: taskId });
  expect(after.data.node.workflowState).toBe("active");
  await test.info().attach("research-started-with-one-action", { body: await header.screenshot(), contentType: "image/png" });
});

test("Projects creates a project from its name alone in the sheet", async ({ page, context }) => {
  const token = await signIn(context);
  const name = "UX name only project";
  await page.goto("/");
  await page.getByRole("link", { name: "All projects", exact: true }).click();
  await page.getByRole("button", { name: /New project$/ }).first().click();
  const sheet = page.getByRole("dialog", { name: "New project", exact: true });
  await expect(sheet).toBeVisible();
  await expect(sheet.locator("[required]")).toHaveCount(1);
  await expect(sheet.getByLabel("project slug", { exact: true })).toBeHidden();
  await sheet.getByLabel("project name", { exact: true }).fill(name);
  const responsePromise = page.waitForResponse((response) => isOperation(response.request(), "tasksProjectCreateMutation"));
  await sheet.getByRole("button", { name: "Create project", exact: true }).click();
  const response = await responsePromise;
  const payload = await response.json();
  expect(payload.errors).toBeUndefined();
  expect(payload.data.projectCreate.errors).toEqual([]);
  const projectId = payload.data.projectCreate.project.id as string;
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  const persisted = await gql(token, `query($id: ID!) { node(id: $id) { ... on Project { id name slug } } }`, { id: projectId });
  expect(persisted.data.node.id).toBe(projectId);
  expect(persisted.data.node.name).toBe(name);
  expect(persisted.data.node.slug).toMatch(/^ux-name-only-project-[a-f0-9]{6}$/);
  await page.reload();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
});
