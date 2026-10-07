import { expect, test } from "@playwright/test";

import { decodeGlobalId, gql, signIn } from "./at-1103-helpers";

/** PAR-01 — contract save path parity.
 *
 * Before the fix the editor wrote `requiredMetrics` while the
 * evaluator enumerated `metrics`: a contract saved through the real
 * UI evaluated as zero requirements. This spec drives the actual UI —
 * save, reload (hydration), freeze — then asserts the exact
 * metric/operator/unit/target reaches `taskEvaluation`. API helpers
 * only bootstrap auth + project + task; the contract under test is
 * written through the editor itself.
 */

async function seedTask(token: string): Promise<string> {
  const proj = await gql(
    token,
    `mutation { projectCreate(input: {slug: "e2e-par01", name: "E2E PAR-01"}) {
       project { id } errors { message } } }`,
  );
  const task = await gql(
    token,
    `mutation ($p: ID!) { taskCreate(input: {projectId: $p,
       title: "contract parity task", mode: "discover",
       targetKind: "formulation", objective: "par-01 regression"}) {
       task { id } errors { message } } }`,
    { p: proj.data.projectCreate.project.id },
  );
  expect(task.data.taskCreate.errors ?? []).toEqual([]);
  return task.data.taskCreate.task.id as string;
}

test.describe("PAR-01 contract editor ↔ evaluator parity", () => {
  test("save → reload → freeze via UI reaches the evaluator", async ({
    page,
    context,
  }) => {
    const token = await signIn(context);
    const taskId = await seedTask(token);

    await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
    const editor = page.locator('[aria-label="success contract editor"]');
    await expect(editor).toBeVisible();
    await expect(editor.getByText("no contract yet")).toBeVisible();

    // author the contract through the real controls
    await editor.getByLabel("metric label").first().fill("viscosity");
    await editor.getByLabel("metric id").first().fill("metric.viscosity");
    await editor.getByLabel("operator").first().selectOption("gte");
    await editor.getByLabel("target value(s)").first().fill("500");
    await editor.getByLabel("unit").first().selectOption("mPa·s");
    await editor.getByLabel("conditions").first().fill("25 °C, spindle A");
    await expect(page.locator("[data-save-state='unsaved']")).toBeVisible();

    await editor.getByRole("button", { name: "save draft" }).click();
    await expect(page.locator("[data-save-state='saved']")).toBeVisible();
    await expect(editor.getByText("draft revision 1")).toBeVisible();

    // reload — the stored draft hydrates; nothing reverts to the old
    // hard-coded blank 'viscosity / Pa_s' row
    await page.reload();
    const editor2 = page.locator('[aria-label="success contract editor"]');
    await expect(editor2.getByLabel("metric label").first()).toHaveValue(
      "viscosity",
    );
    await expect(editor2.getByLabel("metric id").first()).toHaveValue(
      "metric.viscosity",
    );
    await expect(editor2.getByLabel("target value(s)").first()).toHaveValue(
      "500",
    );
    await expect(editor2.getByLabel("unit").first()).toHaveValue("mPa·s");
    await expect(editor2.getByLabel("conditions").first()).toHaveValue(
      "25 °C, spindle A",
    );
    await expect(editor2.getByText("draft revision 1")).toBeVisible();

    // freeze through the UI, then read the evaluator for the same rev
    await editor2.getByRole("button", { name: "freeze contract" }).click();
    await expect(
      editor2.locator(".cs-contract__identity").getByText("frozen"),
    ).toBeVisible();

    const report = await gql(
      token,
      `query ($t: ID!) { taskEvaluation(taskId: $t) }`,
      { t: taskId },
    );
    const evaln = report.data.taskEvaluation;
    expect(evaln.assessable).toBe(true);
    expect(evaln.legacyPayload).toBe(false);
    expect(evaln.metrics).toHaveLength(1);
    expect(evaln.metrics[0].metricId).toBe("metric.viscosity");
    expect(evaln.metrics[0].label).toBe("viscosity");
    // unmeasured → honestly inconclusive, never a fabricated verdict
    expect(evaln.metrics[0].verdict).toBe("inconclusive");
    expect(evaln.suggestedDecision).toBe("inconclusive");
  });

  test("unknown draft fields cannot silently freeze assessable", async ({
    context,
  }) => {
    const token = await signIn(context);
    const taskId = await seedTask(token);

    // A draft preserves unknown fields — freeze must refuse them.
    const draft = await gql(
      token,
      `mutation ($t: ID!, $p: JSON!) { contractDraftCreate(
         input: { taskId: $t, payload: $p }) {
         contractRevision { id revision status } errors { code message } } }`,
      {
        t: taskId,
        p: {
          metrics: [{ name: "gloss", target: ">= 80" }],
          thresholds: { gloss: ">80" },
          unknowns: ["substrate not chosen"],
        },
      },
    );
    expect(draft.data.contractDraftCreate.errors).toEqual([]);
    const revId = draft.data.contractDraftCreate.contractRevision.id;

    const frozen = await gql(
      token,
      `mutation ($r: ID!) { contractFreeze(input: { revisionId: $r }) {
         contractRevision { id status } errors { code message } } }`,
      { r: revId },
    );
    const errs = frozen.data.contractFreeze.errors;
    expect(errs.length).toBeGreaterThan(0);
    expect(errs[0].code).toBe("VALIDATION");
    expect(frozen.data.contractFreeze.contractRevision).toBeNull();

    // resolving the unknowns + dropping the foreign field lets it freeze
    const draft2 = await gql(
      token,
      `mutation ($t: ID!, $p: JSON!) { contractDraftCreate(
         input: { taskId: $t, payload: $p }) {
         contractRevision { id } errors { code message } } }`,
      {
        t: taskId,
        p: { metrics: [{ name: "gloss", target: ">= 80", unit: "dimensionless" }] },
      },
    );
    const revId2 = draft2.data.contractDraftCreate.contractRevision.id;
    const frozen2 = await gql(
      token,
      `mutation ($r: ID!) { contractFreeze(input: { revisionId: $r }) {
         contractRevision { id status revision } errors { code message } } }`,
      { r: revId2 },
    );
    expect(frozen2.data.contractFreeze.errors).toEqual([]);
    expect(frozen2.data.contractFreeze.contractRevision.status).toBe("frozen");
    expect(frozen2.data.contractFreeze.contractRevision.revision).toBe(2);

    // the same revision evaluates — and the metric reached it
    const report = await gql(
      token,
      `query ($t: ID!) { taskEvaluation(taskId: $t) }`,
      { t: taskId },
    );
    expect(report.data.taskEvaluation.assessable).toBe(true);
    expect(report.data.taskEvaluation.metrics[0].metricId).toBe("gloss");
  });

  test("history lists revisions and restores unsaved edits", async ({
    page,
    context,
  }) => {
    const token = await signIn(context);
    const taskId = await seedTask(token);

    await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
    const editor = page.locator('[aria-label="success contract editor"]');
    await expect(editor).toBeVisible();

    await editor.getByLabel("metric label").first().fill("tack");
    await editor.getByLabel("metric id").first().fill("metric.tack");
    await editor.getByLabel("target value(s)").first().fill("10");
    await editor.getByLabel("unit").first().selectOption("dimensionless");
    await editor.getByRole("button", { name: "save draft" }).click();
    await expect(page.locator("[data-save-state='saved']")).toBeVisible();
    await editor.getByRole("button", { name: "freeze contract" }).click();
    await expect(
      editor.locator(".cs-contract__identity").getByText("frozen"),
    ).toBeVisible();

    // edit past the frozen contract → unsaved, then leave the section
    await editor.getByLabel("metric label").first().fill("tack revised");
    await expect(page.locator("[data-save-state='unsaved']")).toBeVisible();
    const sections = page.locator('nav[aria-label="task sections"]');
    // runs lives under the advanced group (PAR-09 progressive
    // disclosure) — leaving overview still unmounts the editor
    await sections.getByRole("link", { name: "advanced" }).click();
    await page
      .locator('nav[aria-label="section views"]')
      .getByRole("link", { name: "runs" })
      .click();
    await expect(
      page.locator('[aria-label="success contract editor"]'),
    ).toHaveCount(0);

    // back to overview — the unsaved form is restored, not lost
    await sections.getByRole("link", { name: "overview" }).click();
    const editorBack = page.locator('[aria-label="success contract editor"]');
    await expect(
      editorBack.getByLabel("metric label").first(),
    ).toHaveValue("tack revised");
    await expect(page.locator("[data-save-state='unsaved']")).toBeVisible();
    await expect(editorBack.getByText("restored unsaved edits")).toBeVisible();

    // history shows the frozen revision and opens it read-only
    await editorBack.getByText("revision history").click();
    await editorBack.getByRole("button", { name: "view" }).first().click();
    await expect(editorBack.getByText(/viewing revision 1/)).toBeVisible();
    await expect(
      page.locator("[data-save-state='read_only_revision']"),
    ).toBeVisible();
    await expect(editorBack.getByText("metric.tack")).toBeVisible();
  });
});
