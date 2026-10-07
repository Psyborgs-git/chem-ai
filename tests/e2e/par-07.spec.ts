import { expect, test } from "@playwright/test";

import { gql, signIn } from "./at-1103-helpers";

/** PAR-07 — the required regression, end to end through the real UI:
 * register synthetic materials → build an accepted baseline
 * formulation revision → select it by name when creating the task →
 * draft a structured successor → propose/submit/review a candidate →
 * review the ingredient/process diff → link the accepted revision
 * into a manual experiment plan → export the packet.
 *
 * API helpers only bootstrap auth + project (allowed); every domain
 * action below is UI-driven and no step copies a uuid from SQL.
 */

const RUN = `par07-${Date.now()}`;

async function makeProject(token: string): Promise<string> {
  const r = await gql(
    token,
    `mutation ($slug: String!, $name: String!) {
       projectCreate(input: {slug: $slug, name: $name}) {
         project { id } errors { code message } } }`,
    { slug: RUN, name: `PAR-07 ${RUN}` },
  );
  expect(r.data.projectCreate.errors).toEqual([]);
  return r.data.projectCreate.project.id as string;
}

async function registerIdentity(
  page: import("@playwright/test").Page,
  name: string,
  scheme: string,
  value: string,
) {
  const form = page.locator('form[aria-label="register material identity"]');
  await form.getByLabel("name").fill(name);
  await form.getByLabel(/scheme/).fill(scheme);
  await form.getByLabel("value").fill(value);
  await form.getByRole("button", { name: "register identity" }).click();
  await expect(
    page
      .getByRole("list", { name: "material identities" })
      .getByText(name, { exact: true }),
  ).toBeVisible({ timeout: 15000 });
}

/** One ingredient row: name, linked material via the picker, amount. */
async function fillIngredient(
  editor: import("@playwright/test").Locator,
  index: number,
  name: string,
  materialSearch: string,
  amount: string,
  role: string,
) {
  const row = editor.locator("ul[aria-label='ingredients'] > li").nth(index);
  await row.getByLabel("ingredient name").fill(name);
  await row.getByLabel(/link material/).fill(materialSearch);
  await row
    .getByRole("listbox")
    .getByRole("button", { name: new RegExp(materialSearch) })
    .click();
  await expect(row.getByText(/^selected:/)).toBeVisible();
  await row.getByLabel("amount").fill(amount);
  await row.getByLabel("role").fill(role);
}

test.describe("PAR-07 materials/formulation/candidate real workflows", () => {
  test("baseline → pick by name → structured successor → diff → manual plan", async ({
    page,
    context,
  }) => {
    test.setTimeout(180000);
    const token = await signIn(context);
    const projectId = await makeProject(token);

    // --- 1. registry: synthetic material identities (UI) ---
    await page.goto("/materials");
    await expect(
      page.getByRole("heading", { name: "Materials & Products" }),
    ).toBeVisible();
    await registerIdentity(page, `${RUN} water`, "cas", `w-${RUN}`);
    await registerIdentity(page, `${RUN} resin`, "cas", `r-${RUN}`);
    await registerIdentity(page, `${RUN} coalescent`, "cas", `c-${RUN}`);

    // --- 2. formulation family + baseline revision (UI) ---
    await page
      .getByRole("button", { name: "formulation families" })
      .click();
    const familyForm = page.locator(
      'form[aria-label="create formulation family"]',
    );
    await familyForm.getByLabel("family name").fill(`${RUN} base coat`);
    await familyForm
      .getByRole("button", { name: "create family" })
      .click();
    const familyList = page.getByRole("list", {
      name: "formulation families",
    });
    await familyList
      .getByRole("button", { name: `${RUN} base coat` })
      .click();
    await expect(
      page.getByRole("heading", { name: `${RUN} base coat` }),
    ).toBeVisible();

    await page
      .getByRole("button", { name: "new formulation revision" })
      .click();
    const editor = page.locator('section[aria-label="formulation editor"]');
    await fillIngredient(editor, 0, `${RUN} water`, `${RUN} water`, "70", "solvent");
    await editor.getByRole("button", { name: "add ingredient" }).click();
    await fillIngredient(editor, 1, `${RUN} resin`, `${RUN} resin`, "30", "binder");
    await editor.getByLabel("declared total").fill("100");
    await editor
      .getByLabel("completeness")
      .selectOption("complete");
    await editor
      .getByRole("button", { name: "save formulation draft" })
      .click();
    await expect(
      editor.getByRole("status").filter({ hasText: "draft rev 1" }),
    ).toBeVisible();
    const revList = page.getByRole("list", { name: "formulation revisions" });
    await revList
      .getByRole("button", { name: "accept revision" })
      .click();
    await expect(
      revList.locator("li", { hasText: "rev 1" }).locator(".cs-badge"),
    ).toHaveText("accepted", { timeout: 15000 });

    // --- 3. task creation: baseline selected by name, never by uuid ---
    // (accepting a successor marks the prior revision "superseded",
    // so the task is created while rev 1 is still the accepted tip)
    await page.goto("/projects");
    await page
      .getByRole("link", { name: `PAR-07 ${RUN}` })
      .click();
    const taskForm = page.locator('form[aria-label="create task"]');
    await taskForm.getByLabel("task title").fill(`${RUN} improve task`);
    await taskForm
      .getByRole("combobox", { name: "baseline formulation revision" })
      .fill(`${RUN} base coat`);
    await taskForm
      .getByRole("listbox")
      .getByRole("button", {
        name: new RegExp(`${RUN} base coat · rev 1 · accepted`),
      })
      .click();
    await taskForm.getByLabel("variation scope").fill("solvent system");
    await taskForm
      .getByRole("button", { name: "Create task (saves a draft)" })
      .click();
    await page.waitForURL(/\/tasks\//);
    const taskUrl = page.url();

    // --- 4. structured successor (descends from the accepted baseline) ---
    await page.goto("/materials");
    await page
      .getByRole("button", { name: "formulation families" })
      .click();
    await page
      .getByRole("list", { name: "formulation families" })
      .getByRole("button", { name: `${RUN} base coat` })
      .click();
    await page
      .getByRole("button", { name: "new formulation revision" })
      .click();
    const editor2 = page.locator(
      'section[aria-label="formulation editor"]',
    );
    await editor2
      .getByRole("button", { name: "copy parent contents into the editor" })
      .click();
    const row0 = editor2.locator("ul[aria-label='ingredients'] > li").nth(0);
    await row0.getByLabel("amount").fill("65");
    await editor2.getByRole("button", { name: "add ingredient" }).click();
    await fillIngredient(
      editor2,
      2,
      `${RUN} coalescent`,
      `${RUN} coalescent`,
      "5",
      "co-solvent",
    );
    await editor2
      .getByRole("button", { name: "save formulation draft" })
      .click();
    await expect(
      editor2.getByRole("status").filter({ hasText: "draft rev 2" }),
    ).toBeVisible();
    await revList
      .locator("li", { hasText: "rev 2" })
      .getByRole("button", { name: "accept revision" })
      .click();
    await expect(
      revList.locator("li", { hasText: "rev 2" }).locator(".cs-badge"),
    ).toHaveText("accepted", { timeout: 15000 });

    // --- 5. propose a candidate bound to the successor revision ---
    await page.goto(taskUrl);
    await page.getByRole("button", { name: "candidates" }).click();
    const propose = page.locator('form[aria-label="propose candidate"]');
    await propose
      .getByLabel("hypothesis")
      .fill("lower water + coalescent improves film");
    await propose
      .getByLabel("proposed difference (optional)")
      .fill("water 70→65, added coalescent 5");
    await propose
      .getByRole("combobox", { name: "entity revision" })
      .fill(`${RUN} base coat`);
    await propose
      .getByRole("listbox")
      .getByRole("button", {
        name: new RegExp(`${RUN} base coat · rev 2 · accepted`),
      })
      .click();
    await propose
      .getByRole("button", { name: "Propose candidate" })
      .click();
    await expect(
      page.getByRole("status").filter({ hasText: "proposed as draft" }),
    ).toBeVisible();
    const candRow = page.locator("li.cs-candidate");
    await candRow.getByRole("button", { name: "submit for review" }).click();
    await expect(
      candRow.locator(".cs-badge").first(),
    ).toHaveText("submitted", { timeout: 15000 });
    await candRow
      .getByRole("button", { name: "accept for research" })
      .click();
    await expect(
      candRow.locator(".cs-badge").first(),
    ).toHaveText("accepted_for_research", { timeout: 15000 });

    // --- 6. review the ingredient diff (rendered, not JSON) ---
    await candRow
      .getByRole("button", { name: "view diff vs baseline" })
      .click();
    const diff = page.locator('[data-field="ingredient-diff"]');
    await expect(diff).toBeVisible();
    const changedRow = diff.locator('tr[data-status="changed"]');
    await expect(changedRow).toHaveCount(1);
    await expect(changedRow).toContainText(`${RUN} water`);
    await expect(changedRow).toContainText("value: 70 → 65");
    const addedRow = diff.locator('tr[data-status="added"]');
    await expect(addedRow).toHaveCount(1);
    await expect(addedRow).toContainText(`${RUN} coalescent`);
    await expect(diff.locator('tr[data-status="unchanged"]')).toHaveCount(1);

    // --- 7. link the accepted revision into a manual experiment plan ---
    await page.goto("/lab");
    await page.locator("#lab-project").selectOption({ label: `PAR-07 ${RUN}` });
    await page
      .locator("#lab-task")
      .selectOption({ label: `${RUN} improve task` });

    const planForm = page.locator('section[aria-label="new experiment plan"]');
    await planForm.getByLabel("plan title").fill(`${RUN} lab confirmation`);
    await planForm
      .getByRole("listbox")
      .getByRole("button", {
        name: /formulation candidate rev 1 · lower water/,
      })
      .click();
    await planForm.getByLabel("method").fill("manual triplicate drawdown");
    await planForm.getByLabel("batch count").fill("2");
    await planForm
      .getByLabel("acceptance criteria (optional)")
      .fill("film forms at ambient cure");
    await planForm.getByRole("button", { name: "create plan" }).click();

    const card = page.locator(".cs-plan");
    await expect(card).toHaveCount(1);
    await expect(card.locator(".cs-badge")).toHaveText("draft");
    // the plan binds the exact accepted candidate revision — a uuid that
    // was picked by name, never typed
    await expect(
      card.locator('[data-field="candidate-revision"] code'),
    ).not.toHaveText("—");
    await expect(card.locator('[aria-label="blockers"]')).toHaveCount(0);

    await card.getByRole("button", { name: "submit for review" }).click();
    await expect(card.locator(".cs-badge")).toHaveText("submitted", {
      timeout: 15000,
    });
    await card.getByLabel("review rationale").fill("diff reviewed");
    await card.getByRole("button", { name: "approve" }).click();
    await expect(card.locator(".cs-badge")).toHaveText("approved", {
      timeout: 15000,
    });
    await card
      .getByRole("button", { name: "export manual packet" })
      .click();
    const packet = card.locator('[aria-label="execution packet"]');
    await expect(packet).toBeVisible();
    await expect(packet.locator(".cs-badge")).toContainText(
      "MANUAL EXECUTION",
    );
    await expect(
      card.locator('[data-field="candidate-revision"] code'),
    ).not.toHaveText("—");
  });
});
