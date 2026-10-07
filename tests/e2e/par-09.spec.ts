import { expect, request, test } from "@playwright/test";
import {
  gql,
  seedClosedTask,
  signIn,
  tabUntil,
} from "./at-1103-helpers";

const API = "http://127.0.0.1:8790";
const ORIGIN = { origin: "http://127.0.0.1:8790" };

/** PAR-09 — primary task organization: six groups (overview, research,
 * candidates, experiments, evidence, decisions) with advanced panels
 * under progressive disclosure, URL-driven group/subview state, a
 * persistent context header, honest save states and pageInfo-driven
 * pagination on the long lists. No visual redesign is asserted — only
 * structure, deep links and honest state. */

async function makeProject(token: string, tag: string): Promise<string> {
  const r = await gql(
    token,
    `mutation { projectCreate(input: {slug: "par09-${tag}", name: "PAR-09 ${tag}"}) {
       project { id } errors { code message } } }`,
  );
  expect(r.data.projectCreate.errors ?? []).toEqual([]);
  return r.data.projectCreate.project.id as string;
}

async function makeTask(
  token: string,
  projectId: string,
  title = "par-09 task",
): Promise<string> {
  const r = await gql(
    token,
    `mutation ($p: ID!, $t: String!) { taskCreate(input: {projectId: $p,
       title: $t, mode: "discover", objective: "par-09 navigation fixture"}) {
       task { id } errors { code message } } }`,
    { p: projectId, t: title },
  );
  expect(r.data.taskCreate.errors ?? []).toEqual([]);
  return r.data.taskCreate.task.id as string;
}

const DRAFT_PAYLOAD = {
  metrics: [
    {
      id: "metric.par09",
      label: "Synthetic index",
      required: true,
      operator: "gte",
      target_values: ["5"],
      unit: "dimensionless",
      required_evidence: ["lab_measurement"],
      aggregation: "fixture-single-value",
    },
  ],
  hard_constraints: [],
};

async function draftContract(token: string, taskId: string): Promise<string> {
  const r = await gql(
    token,
    `mutation ($t: ID!, $p: JSON!) { contractDraftCreate(
       input: { taskId: $t, payload: $p }) {
       contractRevision { id revision } errors { code message } } }`,
    { t: taskId, p: DRAFT_PAYLOAD },
  );
  expect(r.data.contractDraftCreate.errors ?? []).toEqual([]);
  return r.data.contractDraftCreate.contractRevision.id as string;
}

async function seedCandidates(
  token: string,
  taskId: string,
  count: number,
): Promise<void> {
  for (let i = 0; i < count; i++) {
    const r = await gql(
      token,
      `mutation ($t: ID!, $h: String!) { candidates { create(input: {
         taskId: $t, entityKind: "formulation", hypothesis: $h,
         proposedDifferences: [{field: "solvent", op: "reduce"}]}) {
         candidate { id } errors { code message } } } }`,
      { t: taskId, h: `par09-candidate-${i}` },
    );
    expect(r.data.candidates.create.errors ?? []).toEqual([]);
  }
}

async function seedClaims(token: string, count: number): Promise<void> {
  for (let i = 0; i < count; i++) {
    const r = await gql(
      token,
      `mutation ($i: ClaimCreateInput!) { evidence {
         claimCreate(input: $i) { claim { id } errors { code message } } } }`,
      {
        i: {
          kind: "document_claim",
          subject: { name: `par09-subject-${i}` },
          statement: { text: `par09-evidence-${i}` },
        },
      },
    );
    expect(r.data.evidence.claimCreate.errors ?? []).toEqual([]);
  }
}

/** Upload + import a CSV source, promote its first record to a claim,
 * return { artifactId, claimId } — the claim tracks the source's fate. */
async function seedImportedClaim(
  token: string,
): Promise<{ artifactId: string; claimId: string }> {
  const api = await request.newContext({ baseURL: API });
  const init = await api.post("/api/artifacts/uploads", {
    headers: { ...ORIGIN, cookie: `studio_session=${token}` },
    data: { original_name: `par09-${Date.now()}.csv`, media_type: "text/csv" },
  });
  const artifactId = (await init.json()).artifactId as string;
  await api.put(`/api/artifacts/uploads/${artifactId}/content`, {
    headers: { ...ORIGIN, cookie: `studio_session=${token}` },
    data: "component,amount\nwater,50\n",
  });
  await api.post(`/api/artifacts/uploads/${artifactId}/finish`, {
    headers: { ...ORIGIN, cookie: `studio_session=${token}` },
    data: {},
  });
  const imp = await gql(
    token,
    `mutation ($a: String!) { imports { artifactImport(input: {artifactId: $a}) {
       batch { id status } errors { code message } } } }`,
    { a: artifactId },
  );
  expect(imp.data.imports.artifactImport.errors).toEqual([]);
  const batchId = imp.data.imports.artifactImport.batch.id as string;
  const recs = await gql(
    token,
    `query ($b: ID!) { importRecords(batchId: $b, first: 5) {
       edges { node { id locator originalText } } } }`,
    { b: batchId },
  );
  const record = recs.data.importRecords.edges[0].node;
  const promoted = await gql(
    token,
    `mutation ($i: PromoteRecordInput!) { imports {
       recordPromote(input: $i) { claim { id status } errors { code message } } } }`,
    {
      i: {
        recordId: record.id,
        subject: { source: "import", name: "par09-imported" },
        statement: { original: record.originalText },
      },
    },
  );
  expect(promoted.data.imports.recordPromote.errors).toEqual([]);
  return {
    artifactId,
    claimId: promoted.data.imports.recordPromote.claim.id as string,
  };
}

test.describe("PAR-09 task workspace organization", () => {
  test("group + subview live in the URL — deep links, refresh and back restore context", async ({
    page,
    context,
  }) => {
    const token = await signIn(context);
    const taskId = await makeTask(token, await makeProject(token, "nav"));

    // bare task URL lands on the overview group
    await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
    await expect(page).toHaveURL(/\/tasks\/.+\/overview$/);
    await expect(
      page.locator('[aria-label="success contract editor"]'),
    ).toBeVisible();

    const sections = page.locator('nav[aria-label="task sections"]');
    // six primary groups + the advanced disclosure — the 13 flat
    // sections are gone from the primary nav
    for (const g of [
      "overview",
      "research",
      "candidates",
      "experiments",
      "evidence",
      "decisions",
      "advanced",
    ]) {
      await expect(sections.getByRole("link", { name: g })).toBeVisible();
    }
    await expect(
      sections.getByRole("link", { name: "training" }),
    ).toHaveCount(0);

    // clicking a group link moves the URL, not just component state
    await sections.getByRole("link", { name: "experiments" }).click();
    await expect(page).toHaveURL(/\/experiments\?view=plans$/);
    await expect(
      sections.getByRole("link", { name: "experiments" }),
    ).toHaveAttribute("aria-current", "page");

    // subview is a search param on the same path
    const subnav = page.locator('nav[aria-label="section views"]');
    await subnav.getByRole("link", { name: "results" }).click();
    await expect(page).toHaveURL(/\/experiments\?view=results$/);
    await expect(
      page.locator('section[aria-labelledby="results-heading"]'),
    ).toBeVisible();

    // refresh restores the same group + subview
    await page.reload();
    await expect(page).toHaveURL(/\/experiments\?view=results$/);

    // back walks the URL history: subview → group → overview
    await page.goBack();
    await expect(page).toHaveURL(/\/experiments\?view=plans$/);
    await page.goBack();
    await expect(page).toHaveURL(/\/overview$/);

    // a deep link into an advanced panel works without clicking through
    await page.goto(`/tasks/${encodeURIComponent(taskId)}/advanced?view=runs`);
    await expect(
      page.locator('section[aria-labelledby="runs-heading"]'),
    ).toBeVisible();

    // an unknown group segment corrects to overview instead of dead-ending
    await page.goto(`/tasks/${encodeURIComponent(taskId)}/not-a-group`);
    await expect(page).toHaveURL(/\/overview$/);
    await expect(
      page.locator('[aria-label="success contract editor"]'),
    ).toBeVisible();
  });

  test("context header shows objective, contract state, gaps and the next authorized action", async ({
    page,
    context,
  }) => {
    const token = await signIn(context);
    const taskId = await makeTask(token, await makeProject(token, "ctx"));
    const revGid = await draftContract(token, taskId);

    await page.goto(`/tasks/${encodeURIComponent(taskId)}/candidates`);
    const header = page.locator(".cs-task-context");
    await expect(header.locator('[data-field="objective"]')).toContainText(
      "par-09 navigation fixture",
    );
    await expect(header.locator('[data-field="contract-state"]')).toContainText(
      "rev 1 (draft)",
    );
    // a draft contract means the next authorized move is to freeze it
    await expect(header.locator('[data-field="next-action"]')).toContainText(
      "freeze",
    );

    // freeze elsewhere → the header's next action follows the new state
    const frozen = await gql(
      token,
      `mutation ($r: ID!) { contractFreeze(input: { revisionId: $r }) {
         contractRevision { id status } errors { code message } } }`,
      { r: revGid },
    );
    expect(frozen.data.contractFreeze.errors ?? []).toEqual([]);
    await page.reload();
    await expect(header.locator('[data-field="contract-state"]')).toContainText(
      "(frozen)",
    );
    // a draft task with a frozen contract moves on to candidates
    await expect(header.locator('[data-field="next-action"]')).toContainText(
      "candidate",
    );
  });

  test("candidates and evidence claims paginate past one page via pageInfo", async ({
    page,
    context,
  }) => {
    const token = await signIn(context);
    const taskId = await makeTask(token, await makeProject(token, "pages"));
    await seedCandidates(token, taskId, 25);
    await seedClaims(token, 25);

    await page.goto(`/tasks/${encodeURIComponent(taskId)}/candidates`);
    // page 1: the 20 newest candidates, not all 25
    await expect(page.locator("li.cs-candidate")).toHaveCount(20);
    await expect(
      page.locator("li.cs-candidate", { hasText: "par09-candidate-24" }),
    ).toBeVisible();
    await expect(
      page.locator("li.cs-candidate", { hasText: "par09-candidate-4" }),
    ).toHaveCount(0);
    const loadMore = page.getByRole("button", { name: "load more" });
    await loadMore.click();
    await expect(
      page.locator("li.cs-candidate", { hasText: "par09-candidate-0" }),
    ).toBeVisible();
    await expect(page.locator("li.cs-candidate")).toHaveCount(25);
    await expect(loadMore).toHaveCount(0);

    // evidence claims paginate the same way on the task evidence group
    await page.goto(`/tasks/${encodeURIComponent(taskId)}/evidence`);
    await expect(page.locator("article[data-claim-id]")).toHaveCount(20);
    await expect(
      page.locator("article[data-claim-id]", {
        hasText: "par09-evidence-24",
      }),
    ).toBeVisible();
    await page.getByRole("button", { name: "load more" }).click();
    await expect(
      page.locator("article[data-claim-id]", {
        hasText: "par09-evidence-0",
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "load more" }),
    ).toHaveCount(0);
  });

  test("source revocation marks imported claims superseded and the list refreshes honestly", async ({
    page,
    context,
  }) => {
    const token = await signIn(context);
    const projectId = await makeProject(token, "revoke");
    const taskId = await makeTask(token, projectId);
    const { artifactId, claimId } = await seedImportedClaim(token);

    await page.goto(`/tasks/${encodeURIComponent(taskId)}/evidence`);
    const claim = page.locator(`article[data-claim-id="${claimId}"]`);
    await expect(claim).toBeVisible();
    await expect(claim).toHaveAttribute("data-status", "proposed");

    // revoke the source — claims drawn from it become superseded, not
    // silently deleted (CS-0305 propagation)
    const revoked = await gql(
      token,
      `mutation ($i: SourceRevokeInput!) { imports {
         sourceRevoke(input: $i) { revocationId errors { code message } } } }`,
      { i: { artifactId, reason: "par-09 regression" } },
    );
    expect(revoked.data.imports.sourceRevoke.errors).toEqual([]);
    expect(revoked.data.imports.sourceRevoke.revocationId).toBeTruthy();

    // a fresh fetch shows the honest superseded state
    await page.reload();
    await expect(
      page.locator(`article[data-claim-id="${claimId}"]`),
    ).toHaveAttribute("data-status", "superseded");
  });

  test("a contract edit that raced another write stays editable and never claims saved", async ({
    page,
    context,
  }) => {
    const token = await signIn(context);
    const projectId = await makeProject(token, "conflict");
    const taskId = await makeTask(token, projectId);
    const revGid = await draftContract(token, taskId);

    await page.goto(`/tasks/${encodeURIComponent(taskId)}/overview`);
    const editor = page.locator('[aria-label="success contract editor"]');
    await expect(editor.getByRole("button", { name: "save draft" })).toBeVisible();

    // another actor freezes the draft behind this editor's back —
    // clicking freeze now must surface the refusal, not claim success
    const frozen = await gql(
      token,
      `mutation ($r: ID!) { contractFreeze(input: { revisionId: $r }) {
         contractRevision { id status } errors { code message } } }`,
      { r: revGid },
    );
    expect(frozen.data.contractFreeze.errors ?? []).toEqual([]);
    await editor.getByRole("button", { name: "freeze contract" }).click();
    await expect(
      page.getByRole("alert").filter({ hasText: /only a draft|frozen/ }),
    ).toBeVisible();
    await expect(page.locator("[data-save-state='saved']")).toHaveCount(0);

    // a reload re-hydrates truthfully: the frozen revision is the
    // current contract, and drafting resumes at the next revision —
    // the stale freeze attempt is never rewritten as a save
    await page.reload();
    await expect(editor).toContainText("current frozen: rev 1");
    await expect(
      page.locator('[data-field="contract-state"]'),
    ).toContainText("(frozen)");
  });

  test("an API outage during save reports unsaved and recovers on retry", async ({
    page,
    context,
  }) => {
    const token = await signIn(context);
    const projectId = await makeProject(token, "outage");
    const taskId = await makeTask(token, projectId);

    await page.goto(`/tasks/${encodeURIComponent(taskId)}/overview`);
    const editor = page.locator('[aria-label="success contract editor"]');
    await editor.getByLabel("metric id").first().fill("metric.par09");
    await editor.getByLabel("metric label").first().fill("Synthetic");
    await editor.getByLabel("target value(s)").first().fill("5");
    await editor.getByLabel("unit").first().selectOption("dimensionless");

    await page.route("**/graphql", (route) => route.abort());
    await editor.getByRole("button", { name: "save draft" }).click();
    await expect(
      page.getByRole("alert").filter({ hasText: /not saved|not persisted/ }),
    ).toBeVisible();
    await expect(
      page.getByText("unsaved changes — not persisted"),
    ).toBeVisible();
    // §22.4 — never a false offline persistence claim
    await expect(page.getByText("saved offline")).toHaveCount(0);
    await expect(page.getByText(/^saved$/)).toHaveCount(0);

    // connectivity back → the same form retries and durably saves
    await page.unroute("**/graphql");
    await editor.getByRole("button", { name: "save draft" }).click();
    await expect(page.locator("[data-save-state='saved']")).toBeVisible();
  });

  test("home lists pending decisions and recent tasks as real links", async ({
    page,
    context,
  }) => {
    const token = await signIn(context);
    const taskId = await seedClosedTask(token, { close: false });

    await page.goto("/");
    const pending = page.locator('[data-field="pending-decisions"]');
    await expect(pending).toContainText("a11y review task");
    await expect(pending).toContainText("awaiting review");
    const recent = page.locator('[data-field="recent-tasks"]');
    await expect(recent).toContainText("a11y review task");

    // the pending entry deep-links to the closeout subview
    await pending.getByRole("link", { name: /a11y review task/ }).click();
    await expect(page).toHaveURL(/\/decisions\?view=closeout$/);
    await expect(
      page.locator('section[aria-labelledby="closeout-heading"]'),
    ).toBeVisible();
  });

  test("small-laptop width keeps the nav and context header usable", async ({
    page,
    context,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const token = await signIn(context);
    const taskId = await seedClosedTask(token, { close: false });
    await page.goto(`/tasks/${encodeURIComponent(taskId)}/decisions`);

    const sections = page.locator('nav[aria-label="task sections"]');
    for (const g of [
      "overview",
      "research",
      "candidates",
      "experiments",
      "evidence",
      "decisions",
      "advanced",
    ]) {
      await expect(sections.getByRole("link", { name: g })).toBeVisible();
    }
    await expect(page.locator(".cs-task-context")).toBeVisible();
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test("keyboard-only travel reaches every group and subview", async ({
    page,
    context,
  }) => {
    const token = await signIn(context);
    const taskId = await makeTask(token, await makeProject(token, "keys"));

    await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
    await expect(page.locator(".cs-task-context")).toBeVisible();

    // tab to a group link, activate it — the URL changes
    await tabUntil(page, (f) => f.inTaskNav && f.text === "evidence");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/evidence\?view=claims$/);
    // navigation remounts the boundary, so DOM focus is lost — the
    // activated group still carries aria-current for the next reader
    await expect(
      page
        .locator('nav[aria-label="task sections"]')
        .getByRole("link", { name: "evidence" }),
    ).toHaveAttribute("aria-current", "page");

    // subview links are in the tab order too
    await tabUntil(page, (f) => f.inSubNav && f.text === "source quality");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/evidence\?view=quality$/);
    await expect(page.getByRole("heading", { name: "revoke a source" })).toBeVisible();

    // advanced disclosure: the group link, then the runs subview
    await tabUntil(page, (f) => f.inTaskNav && f.text === "advanced");
    await page.keyboard.press("Enter");
    await tabUntil(page, (f) => f.inSubNav && f.text === "runs");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/advanced\?view=runs$/);
    await expect(
      page.locator('section[aria-labelledby="runs-heading"]'),
    ).toBeVisible();
  });
});
