import { expect, type Page } from "@playwright/test";

/** Exercise visible creator entry points; forms are no longer permanent page furniture. */
export async function openProjectCreator(page: Page) {
  const form = page.getByRole("form", { name: "create project" });
  if (!(await form.isVisible())) await page.getByRole("button", { name: "New project", exact: true }).or(page.getByRole("link", { name: "New project", exact: true })).first().click();
}
export async function openTaskCreator(page: Page) {
  const form = page.getByRole("form", { name: "create task" });
  if (!(await form.isVisible())) await page.getByRole("button", { name: "New research task", exact: true }).or(page.getByRole("link", { name: "New research task", exact: true })).first().click();
}
export async function openCreationDetails(page: Page, formName: "create project" | "create task") {
  const details = page.getByRole("form", { name: formName }).locator("details.cs-create-details");
  if (!(await details.evaluate((node) => (node as HTMLDetailsElement).open))) await details.locator("summary").click();
}
export async function openTaskTool(page: Page, tool: string) {
  const names: Record<string, string> = { runs: "Run history", analysis: "Reference analysis", models: "Models", datasets: "Datasets", training: "Training", evaluations: "Evaluations", optimization: "Optimization" };
  const disclosure = page.locator("details.cs-workbench-tools");
  if (!(await disclosure.evaluate((node) => (node as HTMLDetailsElement).open))) await disclosure.locator("summary").click();
  await page.getByRole("navigation", { name: "task tools" }).getByRole("link", { name: names[tool] ?? tool, exact: true }).click();
}
export async function openRegistryCreator(page: Page, formName: string, title: string) {
  if (!(await page.getByRole("form", { name: formName }).isVisible())) await page.locator("details.cs-create-disclosure > summary").filter({ hasText: title }).click();
}
export async function openCriteriaEditor(page: Page) {
  const editor = page.locator('[aria-label="success contract editor"]');
  const open = page.getByRole("button", { name: /^(Define success criteria|Edit criteria)$/ });
  // A restored ?edit=criteria route can still be resolving when navigation
  // completes. Wait for its actual surface before deciding which control to use.
  await expect(editor.or(open)).toBeVisible();
  if (!(await editor.isVisible())) await open.click();
}

/** Active sessions start expanded; leave an already-open stream alone. */
export async function openResearchStream(page: Page) {
  const summary = page.locator('[data-task-view="research"] summary').filter({ hasText: /^stream$/ }).first();
  if (!(await summary.locator("..").evaluate((node) => (node as HTMLDetailsElement).open))) await summary.click();
}
