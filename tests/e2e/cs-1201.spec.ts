import { expect, test } from "@playwright/test";
import { gql, signIn } from "./at-1103-helpers";

/** CS-1201 — the CS-1104 fresh-operator walkthrough recorded four UI
 * defects: nav links to pages that do not exist, a /compute/fallback
 * query failure rendering the signed-out state, and lists going stale
 * after mutations. These specs pin the fixed behaviour. */

async function seedTask(token: string): Promise<string> {
  const proj = await gql(
    token,
    `mutation { projectCreate(input: {slug: "e2e-1201", name: "E2E 1201"}) {
       project { id } errors { message } } }`,
  );
  const task = await gql(
    token,
    `mutation ($p: ID!) { taskCreate(input: {projectId: $p,
       title: "ui gap task", mode: "improve", targetKind: "formulation",
       objective: "e2e coverage for CS-1201",
       modeInputs: {baselineRevisionId: "baseline-rev-1",
         variationScope: "solvent only"}}) {
       task { id } errors { message } } }`,
    { p: proj.data.projectCreate.project.id },
  );
  expect(task.data.taskCreate.errors ?? []).toEqual([]);
  return task.data.taskCreate.task.id as string;
}

test.describe("CS-1201 ui gap fixes", () => {
  test("primary nav has no dead links; /models renders the registry", async ({
    page,
    context,
  }) => {
    await signIn(context);
    await page.goto("/models");
    // Dead nav links stay gone: settings is still not a primary
    // destination. Materials & Products was restored by PAR-07 — now
    // backed by a real /materials registry surface, so it must be
    // present AND land on the registry, not a 404.
    const nav = page.getByRole("navigation", { name: "primary" });
    await expect(nav.getByRole("link", { name: "Settings" })).toHaveCount(0);
    const materialsLink = nav.getByRole("link", {
      name: "Materials & Products",
    });
    await expect(materialsLink).toHaveCount(1);
    // /models mounts the real CS-0802 registry panel, not a 404.
    await expect(page.getByText("Page not found.")).toHaveCount(0);
    await expect(page.getByRole("article", { name: "serving pointer" })).toBeVisible();
    await expect(page.getByRole("button", { name: "register release" })).toBeVisible();
    await expect(page.getByText("session pins")).toBeVisible();

    // the restored link is live — /materials renders the registry
    await materialsLink.click();
    await expect(page).toHaveURL(/\/materials/);
    await expect(
      page.getByRole("heading", { name: "Materials & Products" }),
    ).toBeVisible();
    await expect(page.getByText("Page not found.")).toHaveCount(0);
  });

  test("/compute/fallback/<bad-id> shows not-found, never signed-out", async ({
    page,
    context,
  }) => {
    await signIn(context);
    await page.goto("/compute/fallback/not-a-run-id");
    await expect(page.getByText("Run not found.")).toBeVisible();
    await expect(page.getByText("Not signed in")).toHaveCount(0);

    // A structurally-valid GlobalID for a run that does not exist hits
    // the query and still lands on the same empty state.
    const unknownRun = btoa("Run:00000000-0000-0000-0000-000000000000");
    await page.goto(`/compute/fallback/${encodeURIComponent(unknownRun)}`);
    await expect(page.getByText("Run not found.")).toBeVisible();
    await expect(page.getByText("Not signed in")).toHaveCount(0);
  });

  test("candidate list reflects a new proposal without a reload", async ({
    page,
    context,
  }) => {
    const token = await signIn(context);
    const taskId = await seedTask(token);
    await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
    await page.getByRole("button", { name: "candidates" }).click();
    await expect(page.getByText("No candidates proposed yet.")).toBeVisible();

    await page.getByLabel("hypothesis").fill("e2e hypothesis");
    await page.getByRole("button", { name: /Propose candidate/ }).click();

    // The list refetches on propose — a fresh row appears in place.
    const rows = page.locator("li.cs-candidate");
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText("formulation");
    await expect(page.getByText("proposed as draft")).toBeVisible();
  });

  test("contractFreeze serializes — concurrent drafts cannot race a revision", async ({
    context,
  }) => {
    // The freeze flake was a bare `contractFreeze: null` field; the
    // fix locks the task row and returns a typed retryable CONFLICT on
    // transient persistence failures. Two drafts created back-to-back
    // must get distinct revisions, then both freeze deterministically.
    const token = await signIn(context);
    const taskId = await seedTask(token);
    const payload = {
      metrics: [
        {
          id: "metric.cs1201",
          label: "Synthetic",
          required: true,
          operator: "gte",
          target_values: ["5"],
          unit: "dimensionless",
          required_evidence: ["lab_measurement"],
        },
      ],
      hard_constraints: [],
    };
    const [d1, d2] = await Promise.all([
      gql(
        token,
        `mutation ($t: ID!, $p: JSON!) { contractDraftCreate(
           input: { taskId: $t, payload: $p }) {
           contractRevision { id revision } errors { code message } } }`,
        { t: taskId, p: payload },
      ),
      gql(
        token,
        `mutation ($t: ID!, $p: JSON!) { contractDraftCreate(
           input: { taskId: $t, payload: $p }) {
           contractRevision { id revision } errors { code message } } }`,
        { t: taskId, p: payload },
      ),
    ]);
    // With the task-row lock, both drafts either commit with distinct
    // revisions or return the typed retryable error — never a null
    // field. Assert both committed cleanly (serialized).
    const err1 = d1.data.contractDraftCreate.errors ?? [];
    const err2 = d2.data.contractDraftCreate.errors ?? [];
    expect(err1).toEqual([]);
    expect(err2).toEqual([]);
    const r1 = d1.data.contractDraftCreate.contractRevision.revision as number;
    const r2 = d2.data.contractDraftCreate.contractRevision.revision as number;
    expect(r1).not.toBe(r2);

    const rev2Id = d2.data.contractDraftCreate.contractRevision.id as string;
    const freeze = await gql(
      token,
      `mutation ($r: ID!) { contractFreeze(input: { revisionId: $r }) {
         contractRevision { id status } errors { code message } } }`,
      { r: rev2Id },
    );
    expect(freeze.data.contractFreeze.errors ?? []).toEqual([]);
    expect(freeze.data.contractFreeze.contractRevision.status).toBe("frozen");
  });
});
