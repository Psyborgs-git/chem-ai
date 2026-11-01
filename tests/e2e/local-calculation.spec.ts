import { expect, test } from "@playwright/test";
import { gql, signIn } from "./at-1103-helpers";

/** Real engine journeys: the browser submits structures through the
 * same authenticated mutation as a user. No descriptor is mocked or
 * inserted through a seed API. Optional-engine absence is an
 * explicit skip, never a successful calculation claim. */
async function makeTask(token: string, tag: string) {
  const capability = await gql(token, "query { engineCapabilities { rdkit { status detail } } }");
  test.skip(capability.data.engineCapabilities.rdkit.status !== "available", capability.data.engineCapabilities.rdkit.detail);
  const project = await gql(token, `mutation ($name: String!, $slug: String!) {
    projectCreate(input: {name: $name, slug: $slug}) { project { id } errors { code message } }
  }`, { name: `Local calculation ${tag}`, slug: `local-calculation-${tag}-${Date.now()}` });
  expect(project.data.projectCreate.errors).toEqual([]);
  const task = await gql(token, `mutation ($project: ID!, $title: String!) {
    taskCreate(input: {projectId: $project, title: $title, mode: "discover", targetKind: "molecule", objective: "Inspect structural descriptors with the installed local RDKit engine"}) {
      task { id } errors { code message }
    }
  }`, { project: project.data.projectCreate.project.id, title: `RDKit ${tag}` });
  expect(task.data.taskCreate.errors).toEqual([]);
  return task.data.taskCreate.task.id as string;
}

test("local RDKit: ethanol produces durable computed descriptors", async ({ page, context }) => {
  const token = await signIn(context);
  const taskId = await makeTask(token, "ethanol");
  await page.goto(`/tasks/${encodeURIComponent(taskId)}/overview`);
  await page.getByRole("link", { name: "Run calculation", exact: true }).click();
  await expect(page).toHaveURL(/view=calculations/);
  await page.getByLabel("SMILES structure", { exact: true }).fill("CCO");
  await page.getByRole("button", { name: "Calculate properties", exact: true }).click();
  await expect(page.getByRole("link", { name: "Open saved result" })).toBeVisible({ timeout: 30_000 });
  const latest = page.getByRole("region", { name: "Latest calculation" });
  await expect(latest.locator('[data-field="molecular-formula"]')).toHaveText("C2H6O");
  await expect(latest.locator('[data-field="molecular-weight"]')).toContainText("46.069");
  await page.getByRole("link", { name: "Open saved result" }).click();
  await expect(page).toHaveURL(/\/runs\//);
  await expect(page.locator('[data-field="inchi-key"]')).toHaveText("LFQSCWFLJHTTHZ-UHFFFAOYSA-N");
  await expect(page.getByRole("row", { name: "Hydrogen-bond donors 1 Dimensionless" })).toBeVisible();
  await expect(page.getByRole("row", { name: "Hydrogen-bond acceptors 1 Dimensionless" })).toBeVisible();
  await expect(page.getByText(/not laboratory measurements/)).toBeVisible();
  await page.reload();
  await expect(page.locator('[data-field="molecular-formula"]')).toHaveText("C2H6O");
  await page.screenshot({ path: test.info().outputPath("ethanol-descriptors.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  const molecularWeight = page.getByRole("row", { name: /^Molecular weight 46\.069 g\/mol$/ }).getByRole("cell").first();
  await expect(molecularWeight).toHaveText("46.069");
  expect(await molecularWeight.evaluate((cell) => {
    const bounds = cell.getBoundingClientRect();
    const region = cell.closest(".cs-table-wrap")!.getBoundingClientRect();
    return bounds.left >= region.left && bounds.right <= region.right && bounds.right <= innerWidth;
  })).toBe(true);
  await page.screenshot({ path: test.info().outputPath("ethanol-descriptors-mobile.png"), fullPage: true });
  await page.getByRole("link", { name: "Back to task calculations" }).click();
  await expect(page.getByRole("list", { name: "task runs" }).locator('[data-status="succeeded"]')).toHaveCount(1);
});

test("local RDKit: invalid SMILES persists a failed run without descriptors", async ({ page, context }) => {
  const token = await signIn(context);
  const taskId = await makeTask(token, "parse-failure");
  await page.goto(`/tasks/${encodeURIComponent(taskId)}/experiments?view=calculations`);
  await page.getByLabel("SMILES structure", { exact: true }).fill("not_a_valid_smiles");
  await page.getByRole("button", { name: "Calculate properties", exact: true }).click();
  await expect(page.getByRole("link", { name: "Open saved result" })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("link", { name: "Open saved result" }).click();
  await expect(page.getByRole("alert")).toContainText("PARSE_FAILED");
  await expect(page.locator('[data-field="molecular-formula"]')).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("PARSE_FAILED");
  await expect(page.getByText("No completed calculation result is available.")).toBeVisible();
});
