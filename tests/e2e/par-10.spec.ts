import {
  expect,
  request,
  test,
  type Locator,
  type Page,
} from "@playwright/test";

import { decodeGlobalId, gql, signIn } from "./at-1103-helpers";

/** PAR-10b — browser-first acceptance journeys + adversarial evaluation.
 *
 * The audit's PAR-10 correction: isolated specs that pass while whole
 * workflows are broken are not end-to-end proof. The three journeys
 * below drive the REAL surfaces each ticket delivered — PAR-06 sign-in
 * + project/task forms, PAR-07 registry pickers/diffs, PAR-01 contract
 * editor round-trip, PAR-09 task-workspace navigation — end to end.
 *
 * Helper boundary (audit rule): helpers bootstrap the owner account and
 * attach known fixture bytes; for the adversarial section they also seed
 * states the UI cannot author (structured absence-gate checks,
 * per-candidate evidence applicability bindings, historical executions).
 * No helper performs the action a test claims to verify: every domain
 * step in the journeys — sign-in, project/task create, contract
 * save/freeze, candidate lifecycle, plan approval, measurement
 * record/review, ingest/compare, claim review, closure — is UI-driven.
 *
 * Honest outcomes: nonassessable / inconclusive / not_evaluated /
 * insufficient states are asserted as EXPECTED results — never coerced
 * into success. Engine/model-dependent capability (research agent,
 * model registry) is asserted as explicitly unavailable, separately
 * from any scientific-validation claim.
 */

const API = "http://127.0.0.1:8790";
const ORIGIN = { origin: API };
const OWNER = {
  login: "e2e-owner",
  display: "E2E Owner",
  password: "e2e-password-10",
};

/** Account bootstrap only (allowed helper): create the owner through
 * the supported /api/auth/setup, or log in when it already exists.
 * Returns a token for gql/artifact fixture helpers. The browser session
 * itself is always established through the real PAR-06 sign-in UI. */
async function apiToken(): Promise<string> {
  const api = await request.newContext({ baseURL: API });
  const res = await api.post("/api/auth/setup", {
    headers: ORIGIN,
    data: {
      login: OWNER.login,
      display_name: OWNER.display,
      password: OWNER.password,
    },
  });
  const res2 = res.ok()
    ? res
    : await api.post("/api/auth/login", {
        headers: ORIGIN,
        data: { login: OWNER.login, password: OWNER.password },
      });
  expect(res2.ok()).toBeTruthy();
  const token = /studio_session=([^;]+)/.exec(
    res2.headers()["set-cookie"] ?? "",
  )?.[1];
  expect(token).toBeTruthy();
  return token!;
}

/** The real PAR-06 sign-in surface — never a console fetch or an
 * injected cookie in the journeys. */
async function signInViaUi(page: Page) {
  await page.goto("/");
  await page.getByLabel("login").fill(OWNER.login);
  await page.getByLabel("password", { exact: true }).fill(OWNER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({
    timeout: 15000,
  });
  await expect(page.getByText(`Signed in as ${OWNER.display}`)).toBeVisible();
}

async function createProjectViaUi(page: Page, slug: string, name: string) {
  await page.goto("/projects");
  await page.getByLabel("project slug").fill(slug);
  await page.getByLabel("project name").fill(name);
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page).toHaveURL(/\/projects\//);
  await expect(page.getByRole("heading", { name: "Project" })).toBeVisible();
}

async function registerIdentity(
  page: Page,
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
  editor: Locator,
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

/** Accepted formulation revision `rev` of `familyName`, built via the
 * registry UI — `copyParent` pulls the prior revision's ingredients into
 * the editor (PAR-07 surface). Returns after the revision shows
 * "accepted". */
async function acceptedFormulationRev(
  page: Page,
  familyName: string,
  rev: number,
  opts: { copyParent?: boolean; amountEdits?: [number, string][] } = {},
) {
  await page.goto("/materials");
  await page.getByRole("button", { name: "formulation families" }).click();
  await page
    .getByRole("list", { name: "formulation families" })
    .getByRole("button", { name: familyName })
    .click();
  await page.getByRole("button", { name: "new formulation revision" }).click();
  const editor = page.locator('section[aria-label="formulation editor"]');
  if (opts.copyParent) {
    await editor
      .getByRole("button", { name: "copy parent contents into the editor" })
      .click();
    for (const [rowIdx, amount] of opts.amountEdits ?? []) {
      await editor
        .locator("ul[aria-label='ingredients'] > li")
        .nth(rowIdx)
        .getByLabel("amount")
        .fill(amount);
    }
  }
  await editor.getByLabel("declared total").fill("100");
  await editor.getByLabel("completeness").selectOption("complete");
  await editor
    .getByRole("button", { name: "save formulation draft" })
    .click();
  await expect(
    editor.getByRole("status").filter({ hasText: `draft rev ${rev}` }),
  ).toBeVisible();
  const revList = page.getByRole("list", { name: "formulation revisions" });
  await revList
    .locator("li", { hasText: `rev ${rev}` })
    .getByRole("button", { name: "accept revision" })
    .click();
  await expect(
    revList.locator("li", { hasText: `rev ${rev}` }).locator(".cs-badge"),
  ).toHaveText("accepted", { timeout: 15000 });
}

/** Propose → submit → accept a candidate through the task's candidates
 * view (UI only). `bind` describes the entity picker step:
 * formulation → "entity revision" combobox, material → "material
 * identity" combobox. */
async function acceptCandidateViaUi(
  page: Page,
  taskUrl: string,
  opts: {
    hypothesis: string;
    difference?: string;
    entityKind?: "formulation" | "material";
    entitySearch?: string;
    entityPick?: RegExp;
  },
) {
  await page.goto(taskUrl);
  await page
    .locator('nav[aria-label="task sections"]')
    .getByRole("link", { name: "candidates" })
    .click();
  const propose = page.locator('form[aria-label="propose candidate"]');
  await propose.getByLabel("hypothesis").fill(opts.hypothesis);
  if (opts.difference) {
    await propose
      .getByLabel("proposed difference (optional)")
      .fill(opts.difference);
  }
  if (opts.entityKind === "material") {
    await propose.locator("#entity-kind").selectOption("material");
    await propose
      .getByRole("combobox", { name: "material identity" })
      .fill(opts.entitySearch ?? "");
  } else if (opts.entitySearch) {
    await propose
      .getByRole("combobox", { name: "entity revision" })
      .fill(opts.entitySearch);
  }
  if (opts.entityPick) {
    await propose
      .getByRole("listbox")
      .getByRole("button", { name: opts.entityPick })
      .click();
    await expect(propose.getByText(/bound to:/)).toBeVisible();
  }
  await propose
    .getByRole("button", { name: /Propose candidate/ })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "proposed as draft" }),
  ).toBeVisible({ timeout: 15000 });
  const candRow = page.locator("li.cs-candidate", {
    hasText: opts.hypothesis,
  });
  await candRow.getByRole("button", { name: "submit for review" }).click();
  await expect(candRow.locator(".cs-badge").first()).toHaveText("submitted", {
    timeout: 15000,
  });
  await candRow
    .getByRole("button", { name: "accept for research" })
    .click();
  await expect(candRow.locator(".cs-badge").first()).toHaveText(
    "accepted_for_research",
    { timeout: 15000 },
  );
}

/** Contract through the real PAR-01 editor: fill the first metric row,
 * save, reload (hydration round-trip), freeze. */
async function freezeContractViaUi(
  page: Page,
  metric: { label: string; id: string; operator: string; target: string },
  opts: { unknowns?: string[]; resolveUnknownsOnFreeze?: boolean } = {},
) {
  const contract = page.locator('[aria-label="success contract editor"]');
  await expect(contract).toBeVisible();
  for (const u of opts.unknowns ?? []) {
    await contract.getByLabel("new unknown").fill(u);
    await contract.getByRole("button", { name: "add unknown" }).click();
    await expect(contract.getByText(u)).toBeVisible();
  }
  await contract.getByLabel("metric label").first().fill(metric.label);
  await contract.getByLabel("metric id").first().fill(metric.id);
  await contract.getByLabel("operator").first().selectOption(metric.operator);
  await contract.getByLabel("target value(s)").first().fill(metric.target);
  await contract.getByLabel("unit").first().selectOption("dimensionless");
  await contract.getByLabel("aggregation").first().selectOption("single");
  await contract.getByRole("button", { name: "save draft" }).click();
  await expect(page.locator("[data-save-state='saved']")).toBeVisible();
  await page.reload();
  const editor2 = page.locator('[aria-label="success contract editor"]');
  await expect(editor2.getByLabel("metric id").first()).toHaveValue(
    metric.id,
  );
  await editor2.getByRole("button", { name: "freeze contract" }).click();
  if (opts.resolveUnknownsOnFreeze) {
    // the domain refuses to freeze while a declared unknown stands —
    // the refusal is part of the asserted acceptance behaviour
    await expect(
      editor2.getByRole("alert").filter({ hasText: "cannot be frozen" }),
    ).toBeVisible();
    for (const u of opts.unknowns ?? []) {
      await editor2
        .locator("li", { hasText: u })
        .getByRole("button", { name: "resolve" })
        .click();
    }
    await editor2.getByRole("button", { name: "save draft" }).click();
    await expect(page.locator("[data-save-state='saved']")).toBeVisible();
    await editor2
      .getByRole("button", { name: "freeze contract" })
      .click();
  }
  await expect(
    editor2.locator(".cs-contract__identity").getByText("frozen"),
  ).toBeVisible({ timeout: 15000 });
}

/** Approved manual plan through the task's experiments/plans view —
 * candidate + contract bound by picker, draft → submit → approve →
 * export packet (all UI). */
async function approvePlanViaUi(
  page: Page,
  opts: { title: string; candidatePick: RegExp; contractPick: RegExp },
) {
  await page
    .locator('nav[aria-label="task sections"]')
    .getByRole("link", { name: "experiments" })
    .click();
  const planForm = page.locator('section[aria-label="new experiment plan"]');
  await planForm.getByLabel("plan title").fill(opts.title);
  await planForm
    .getByRole("listbox")
    .getByRole("button", { name: opts.candidatePick })
    .click();
  await planForm
    .getByRole("listbox")
    .getByRole("button", { name: opts.contractPick })
    .click();
  await planForm.getByLabel("method").fill("manual drawdown");
  await planForm.getByLabel("batch count").fill("1");
  await planForm
    .getByLabel("acceptance criteria (optional)")
    .fill("fixture acceptance");
  await planForm.getByRole("button", { name: "create plan" }).click();
  const card = page.locator(".cs-plan").filter({ hasText: opts.title });
  await expect(card.locator(".cs-badge")).toHaveText("draft", {
    timeout: 15000,
  });
  await card.getByRole("button", { name: "submit for review" }).click();
  await expect(card.locator(".cs-badge")).toHaveText("submitted", {
    timeout: 15000,
  });
  await card.getByLabel("review rationale").fill("plan reviewed");
  await card.getByRole("button", { name: "approve" }).click();
  await expect(card.locator(".cs-badge")).toHaveText("approved", {
    timeout: 15000,
  });
  await card.getByRole("button", { name: "export manual packet" }).click();
  const packet = card.locator('[aria-label="execution packet"]');
  await expect(packet).toBeVisible();
  await expect(packet.locator(".cs-badge")).toContainText(
    "MANUAL EXECUTION",
  );
}

/** Record + review-accept one measurement through the results view:
 * open the plan's manual execution, add batch + sample, fill the
 * measurement form, accept it — all UI. */
async function recordAcceptedMeasurementViaUi(
  page: Page,
  opts: { planTitle: string; method: string; metric: string; value: string },
) {
  await page
    .locator('nav[aria-label="section views"]')
    .getByRole("link", { name: "results" })
    .click();
  const ready = page
    .locator('ul[aria-label="approved plans ready to execute"] li')
    .filter({ hasText: opts.planTitle });
  await ready.getByRole("button", { name: "open manual execution" }).click();
  const execution = page.locator(".cs-execution").first();
  await expect(execution).toBeVisible({ timeout: 15000 });
  await execution.getByLabel("new batch label").fill("A");
  await execution.getByRole("button", { name: "add batch" }).click();
  const batch = execution.locator("li[data-batch-id]");
  await expect(batch).toHaveCount(1);
  await batch.getByLabel("new sample label").fill("a1");
  await batch
    .locator('select[aria-label="sample kind"]')
    .selectOption("aliquot");
  await batch.getByRole("button", { name: "add sample" }).click();
  const sample = batch.locator("li[data-sample-id]");
  const mform = sample.locator('details[data-field="measurement-form"]');
  await mform.locator("summary").click();
  await mform.getByLabel("method").fill(opts.method);
  await mform.getByLabel(/contract metric id/).fill(opts.metric);
  await mform.getByLabel("repeat type").selectOption("independent_batch");
  await mform
    .locator('textarea[aria-label="measurement value (JSON)"]')
    .fill(
      JSON.stringify({
        kind: "numeric",
        value: opts.value,
        unit: "dimensionless",
      }),
    );
  await mform.getByRole("button", { name: "record" }).click();
  const measurement = sample.locator("li[data-measurement-id]");
  await expect(measurement).toBeVisible({ timeout: 15000 });
  await measurement.getByRole("button", { name: "accept" }).click();
  await expect(measurement).toHaveAttribute("data-status", "accepted", {
    timeout: 15000,
  });
}

/** Navigate to the task's closeout view via the PAR-09 workspace nav. */
async function gotoCloseout(page: Page, taskUrl: string) {
  await page.goto(taskUrl);
  await page
    .locator('nav[aria-label="task sections"]')
    .getByRole("link", { name: "decisions" })
    .click();
  await page
    .locator('nav[aria-label="section views"]')
    .getByRole("link", { name: "closeout" })
    .click();
  await expect(page.locator('[data-field="evaluation-report"]')).toBeVisible({
    timeout: 15000,
  });
}

/** Upload known fixture bytes through the artifact vault (allowed
 * helper — attaches bytes, performs no domain interpretation). */
async function uploadFixtureArtifact(
  token: string,
  name: string,
  bytes: string,
): Promise<string> {
  const api = await request.newContext({ baseURL: API });
  const init = await api.post("/api/artifacts/uploads", {
    headers: { ...ORIGIN, cookie: `studio_session=${token}` },
    data: { original_name: name, media_type: "text/csv" },
  });
  const artifactId = (await init.json()).artifactId as string;
  await api.put(`/api/artifacts/uploads/${artifactId}/content`, {
    headers: { ...ORIGIN, cookie: `studio_session=${token}` },
    data: bytes,
  });
  await api.post(`/api/artifacts/uploads/${artifactId}/finish`, {
    headers: { ...ORIGIN, cookie: `studio_session=${token}` },
    data: {},
  });
  return artifactId;
}

// ------------------------------------------------------------------
// journey 1 — improve: the full corrected-path loop, UI end to end
// ------------------------------------------------------------------

test.describe("PAR-10 acceptance journeys", () => {
  test("improve: UI project → baseline pick → real contract → candidate → approved plan → recorded/reviewed measurement → closeout", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const RUN = `par10i-${Date.now()}`;
    const token = await apiToken();
    await signInViaUi(page);
    await createProjectViaUi(page, RUN, `PAR-10 improve ${RUN}`);

    // registry: identities + family + accepted baseline revision (UI)
    await page.goto("/materials");
    await registerIdentity(page, `${RUN} water`, "cas", `w-${RUN}`);
    await registerIdentity(page, `${RUN} resin`, "cas", `r-${RUN}`);
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
    await page
      .getByRole("list", { name: "formulation families" })
      .getByRole("button", { name: `${RUN} base coat` })
      .click();
    await page
      .getByRole("button", { name: "new formulation revision" })
      .click();
    const editor = page.locator('section[aria-label="formulation editor"]');
    await fillIngredient(editor, 0, `${RUN} water`, `${RUN} water`, "70", "solvent");
    await editor.getByRole("button", { name: "add ingredient" }).click();
    await fillIngredient(editor, 1, `${RUN} resin`, `${RUN} resin`, "30", "binder");
    await editor.getByLabel("declared total").fill("100");
    await editor.getByLabel("completeness").selectOption("complete");
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

    // task: improve mode, baseline selected BY NAME (PAR-07 picker)
    await page.goto("/projects");
    await page
      .getByRole("link", { name: `PAR-10 improve ${RUN}` })
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
      .getByRole("button", { name: /Create task/ })
      .click();
    await page.waitForURL(/\/tasks\//);
    const taskUrl = page.url();

    // contract authored through the real editor (PAR-01 round-trip)
    await freezeContractViaUi(page, {
      label: "manual film index",
      id: "metric.film-index",
      operator: "gte",
      target: "5",
    });

    // successor formulation revision — the candidate's bound entity (UI);
    // amounts stay consistent: 65 + 35 still sums to the declared 100
    await acceptedFormulationRev(page, `${RUN} base coat`, 2, {
      copyParent: true,
      amountEdits: [
        [0, "65"],
        [1, "35"],
      ],
    });

    // candidate bound to the successor, full review lifecycle (UI)
    await acceptCandidateViaUi(page, taskUrl, {
      hypothesis: "lower water improves film",
      difference: "water 70→65",
      entityKind: "formulation",
      entitySearch: `${RUN} base coat`,
      entityPick: new RegExp(`${RUN} base coat · rev 2 · accepted`),
    });

    // PAR-07 diff surface is part of the workflow proof
    await page
      .locator("li.cs-candidate")
      .getByRole("button", { name: "view diff vs baseline" })
      .click();
    const diff = page.locator('[data-field="ingredient-diff"]');
    await expect(diff).toBeVisible();
    const changedRows = diff.locator('tr[data-status="changed"]');
    await expect(changedRows).toHaveCount(2);
    await expect(
      diff.locator('tr[data-status="changed"]', { hasText: `${RUN} water` }),
    ).toContainText("value: 70 → 65");
    await expect(
      diff.locator('tr[data-status="changed"]', { hasText: `${RUN} resin` }),
    ).toContainText("value: 30 → 35");

    // approved manual plan bound to candidate + frozen contract (UI)
    await approvePlanViaUi(page, {
      title: `${RUN} film check`,
      candidatePick: /formulation candidate rev 1 · lower water/,
      contractPick: /contract rev 1 · frozen/,
    });

    // recorded + human-reviewed measurement on the opened execution (UI)
    await recordAcceptedMeasurementViaUi(page, {
      planTitle: `${RUN} film check`,
      method: "manual-index",
      metric: "metric.film-index",
      value: "7",
    });

    // a reviewer moves the task to active — the one transition the UI
    // does not expose (helpers seed state, never the action under test)
    const taskGid = decodeURIComponent(
      taskUrl.split("/tasks/")[1].split("/")[0],
    );
    await transition(token, taskGid, "active");

    // closeout: evaluator suggests; the human reviewer closes (UI)
    await gotoCloseout(page, taskUrl);
    const report = page.locator('[data-field="evaluation-report"]');
    await expect(
      page.locator('text=suggestion: supported_success'),
    ).toBeVisible({ timeout: 15000 });
    // PAR-05 honesty: a manually recorded observation derives real
    // provenance, and validation state stays missing — never "validated"
    await expect(
      report.getByText(/real provenance.*independent validation: missing/),
    ).toBeVisible();
    const selected = page.locator('[data-field="selected-candidate-report"]');
    await expect(
      selected.locator('[data-field="metric-row"][data-verdict="met"]'),
    ).toHaveCount(1);

    await page.getByRole("button", { name: "send to review" }).click();
    await expect(page.locator('[data-field="close-form"]')).toBeVisible({
      timeout: 15000,
    });
    await page.locator("#closure-decision").selectOption("supported_success");
    const closeBtn = page.getByRole("button", { name: "close task" });
    await expect(closeBtn).toBeDisabled();
    await page
      .locator("text=I confirm this closure as the human reviewer")
      .click();
    await expect(closeBtn).toBeEnabled();
    await closeBtn.click();
    await expect(page.locator('[data-field="closed-note"]')).toBeVisible({
      timeout: 15000,
    });

    // post-hoc verification (assertion, not a step under test): the
    // signed packet binds the candidate's evidence with real origin
    const packet = await gql(
      token,
      `query ($t: ID!) { taskCloseoutPacket(taskId: $t) }`,
      { t: taskGid },
    );
    expect(packet.data.taskCloseoutPacket.fixtureOnly).toBe(false);
    expect(packet.data.taskCloseoutPacket.evidenceIds.length).toBe(1);
    expect(
      packet.data.taskCloseoutPacket.provenance.evidenceOrigin.composition,
    ).toBe("real_only");
    expect(
      packet.data.taskCloseoutPacket.scientificValidation,
    ).toBe("not_validated");
  });

  // ----------------------------------------------------------------
  // journey 2 — match: reference with unknown recipe, scoped targets,
  // analytical comparison + evidence review + candidate comparison
  // ----------------------------------------------------------------

  test("match: unknown-recipe reference → scoped targets → ingest/compare → claim review → per-candidate comparison", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const RUN = `par10m-${Date.now()}`;
    const token = await apiToken();
    await signInViaUi(page);
    await createProjectViaUi(page, RUN, `PAR-10 match ${RUN}`);

    // reference product — composition knowledge stays "unknown"
    await page.goto("/materials");
    await page.getByRole("button", { name: "reference products" }).click();
    const pform = page.locator('form[aria-label="register reference product"]');
    await pform.getByLabel("product name").fill(`${RUN} ref-coat`);
    await pform.getByLabel("supplier (optional)").fill("fixture supplier");
    await pform.getByLabel("category (optional)").fill("coating");
    await pform.locator("#prod-knowledge").selectOption("unknown");
    await pform.getByRole("button", { name: "register product" }).click();
    await expect(
      page
        .getByRole("list", { name: "reference products" })
        .getByText(`${RUN} ref-coat`),
    ).toBeVisible({ timeout: 15000 });

    // two material identities — the candidates' bound entities (UI)
    await page.getByRole("button", { name: "material identities" }).click();
    await registerIdentity(page, `${RUN} binder-a`, "cas", `ba-${RUN}`);
    await registerIdentity(page, `${RUN} binder-b`, "cas", `bb-${RUN}`);

    // match_reference task, scoped functional AND analytical (UI)
    await page.goto("/projects");
    await page
      .getByRole("link", { name: `PAR-10 match ${RUN}` })
      .click();
    const taskForm = page.locator('form[aria-label="create task"]');
    await taskForm.getByLabel("task title").fill(`${RUN} match task`);
    await taskForm.locator("#mode").selectOption("match_reference");
    await taskForm
      .getByRole("combobox", { name: "reference product" })
      .fill(`${RUN} ref-coat`);
    await taskForm
      .getByRole("listbox")
      .getByRole("button", {
        name: new RegExp(`${RUN} ref-coat .* knowledge: unknown`),
      })
      .click();
    await taskForm
      .locator("#match-scope")
      .selectOption("functional_and_analytical");
    await taskForm
      .getByRole("button", { name: /Create task/ })
      .click();
    await page.waitForURL(/\/tasks\//);
    const taskUrl = page.url();

    // scoped functional target through the real contract editor
    await freezeContractViaUi(page, {
      label: "gloss",
      id: "metric.gloss",
      operator: "gte",
      target: "80",
    });

    // analytical ingest requires an active task — a reviewer transition
    // (API; the UI exposes no draft→active affordance)
    const matchTaskGid = decodeURIComponent(
      taskUrl.split("/tasks/")[1].split("/")[0],
    );
    await transition(token, matchTaskGid, "active");

    // analytical scope: two csv-xy exports (fixture bytes via helper)
    // ingested + compared through the real analysis panel (UI)
    const xs = Array.from({ length: 24 }, (_, i) => 380 + i * 10);
    const csvA = xs.map((x, i) => `${x},${(0.2 + i * 0.01).toFixed(4)}`).join("\n");
    const csvB = xs.map((x, i) => `${x},${(0.19 + i * 0.011).toFixed(4)}`).join("\n");
    const artA = await uploadFixtureArtifact(token, `${RUN}-a.csv`, csvA);
    const artB = await uploadFixtureArtifact(token, `${RUN}-b.csv`, csvB);

    await page
      .locator('nav[aria-label="task sections"]')
      .getByRole("link", { name: "advanced" })
      .click();
    await page
      .locator('nav[aria-label="section views"]')
      .getByRole("link", { name: "analysis" })
      .click();

    const ingestSpec = (label: string, sample: string) =>
      JSON.stringify({
        schema_version: "1",
        method: "infrared",
        label,
        x_unit: "cm-1",
        y_unit: "absorbance",
        instrument: { vendor: "fixture", model: "fx-1" },
        sample: { label: sample },
        preprocessing: [],
      });
    for (const [art, label, sample] of [
      [artA, `${RUN} series A`, "sample-a"],
      [artB, `${RUN} series B`, "sample-b"],
    ] as const) {
      await page
        .getByLabel("Raw export artifact id (uuid)")
        .fill(art);
      await page
        .locator('textarea[aria-label="Ingest spec JSON"]')
        .fill(ingestSpec(label, sample));
      await page.getByRole("button", { name: "Ingest series" }).click();
      await expect(
        page.getByText(/Series recorded\./),
      ).toBeVisible({ timeout: 15000 });
    }

    await page
      .locator('select[aria-label="Left series"]')
      .selectOption({ label: `${RUN} series A (infrared)` });
    await page
      .locator('select[aria-label="Right series"]')
      .selectOption({ label: `${RUN} series B (infrared)` });
    await page
      .getByRole("button", { name: "Compute scoped similarity" })
      .click();
    const comparison = page.locator(
      'section[aria-label^="comparison"]',
    );
    await expect(comparison).toBeVisible({ timeout: 15000 });
    // PAR-08 honesty: similarity is scoped and explicitly NOT
    // composition evidence — no recovered-composition claim
    await expect(
      comparison.locator(".cs-badge"),
    ).toContainText("not_composition_evidence");
    await expect(
      comparison.locator('ul[aria-label="interpretation limits"]'),
    ).toContainText(
      "a matching similarity value is not evidence of identical composition",
    );

    // evidence review through the real claims surface (seed = bootstrap;
    // the review decision under test is UI-driven)
    const claim = await gql(
      token,
      `mutation { evidence { claimCreate(input: {
         kind: "document_claim",
         subject: { entity: "${RUN} ref-coat" },
         statement: { text: "supplier sheet claims gloss ≥ 80 at 60°" } }) {
         claim { id } errors { code message } } } }`,
    );
    expect(claim.data.evidence.claimCreate.errors ?? []).toEqual([]);
    const claimId = claim.data.evidence.claimCreate.claim.id as string;
    await page
      .locator('nav[aria-label="task sections"]')
      .getByRole("link", { name: "evidence" })
      .click();
    const claimCard = page.locator(`article[data-claim-id="${claimId}"]`);
    await expect(claimCard).toHaveAttribute("data-status", "proposed");
    await claimCard.getByRole("button", { name: "accept claim" }).click();
    await expect(claimCard).toHaveAttribute("data-status", "accepted", {
      timeout: 15000,
    });

    // two candidates bound to different identities (UI) → per-candidate
    // comparison at closeout
    await acceptCandidateViaUi(page, taskUrl, {
      hypothesis: "binder A matches gloss",
      entityKind: "material",
      entitySearch: `${RUN} binder-a`,
      entityPick: new RegExp(`${RUN} binder-a`),
    });
    await acceptCandidateViaUi(page, taskUrl, {
      hypothesis: "binder B matches gloss",
      entityKind: "material",
      entitySearch: `${RUN} binder-b`,
      entityPick: new RegExp(`${RUN} binder-b`),
    });

    await gotoCloseout(page, taskUrl);
    // two accepted candidates: each reported separately — no pooled
    // verdict exists, and none is claimed
    await expect(
      page.getByText(/each is reported separately and no pooled verdict/),
    ).toBeVisible();
    const cands = page.locator('[data-field="candidate-row"]');
    await expect(cands).toHaveCount(2);
    await cands.first().locator('input[name="evaluation-candidate"]').check();
    const selReport = page.locator('[data-field="selected-candidate-report"]');
    await expect(selReport).toBeVisible();
    // no bound evidence → honest inconclusive, not a fabricated pass
    await expect(
      selReport.locator('[data-field="metric-row"][data-verdict="inconclusive"]'),
    ).toHaveCount(1);
    await cands.nth(1).locator('input[name="evaluation-candidate"]').check();
    await expect(
      selReport.locator('[data-field="metric-row"][data-verdict="inconclusive"]'),
    ).toHaveCount(1);

    // the reference's recipe stays unknown at the registry — the
    // journey produced functional/analytical similarity only
    await page.goto("/materials");
    await page.getByRole("button", { name: "reference products" }).click();
    const productRow = page
      .getByRole("list", { name: "reference products" })
      .locator("li", { hasText: `${RUN} ref-coat` });
    await expect(productRow.locator(".cs-badge")).toContainText(
      "composition: unknown",
    );
  });

  // ----------------------------------------------------------------
  // journey 3 — discover: target definition, bounded research,
  // eligible candidate + manual feedback; missing method/model stays
  // visibly unresolved
  // ----------------------------------------------------------------

  test("discover: target task → bounded research (model unavailable surfaced) → candidate → manual feedback → closeout", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const RUN = `par10d-${Date.now()}`;
    const token = await apiToken();
    await signInViaUi(page);
    await createProjectViaUi(page, RUN, `PAR-10 discover ${RUN}`);

    // identity for the candidate's bound entity (UI)
    await page.goto("/materials");
    await registerIdentity(page, `${RUN} binder`, "cas", `b-${RUN}`);

    // discover task: target kind + objective (UI)
    await page.goto("/projects");
    await page
      .getByRole("link", { name: `PAR-10 discover ${RUN}` })
      .click();
    const taskForm = page.locator('form[aria-label="create task"]');
    await taskForm.getByLabel("task title").fill(`${RUN} discover task`);
    await taskForm.locator("#mode").selectOption("discover");
    await taskForm.locator("#target-kind").selectOption("formulation");
    await taskForm
      .getByLabel("objective", { exact: true })
      .fill("find a low-VOC binder");
    await taskForm
      .getByRole("button", { name: /Create task/ })
      .click();
    await page.waitForURL(/\/tasks\//);
    const taskUrl = page.url();

    // bounded research: a real session, a real question — and the
    // unavailable model is surfaced honestly, not faked into an answer
    await page
      .locator('nav[aria-label="task sections"]')
      .getByRole("link", { name: "research" })
      .click();
    await page
      .getByRole("button", { name: "start research session" })
      .click();
    await expect(
      page.getByRole("button", { name: "end active session" }),
    ).toBeVisible({ timeout: 15000 });
    await page.locator("summary", { hasText: "stream" }).click();
    const composer = page.locator('form[aria-label="research composer"]');
    await composer
      .getByLabel("ask the research agent")
      .fill("which binder families fit low-VOC coatings?");
    await composer.getByRole("button", { name: "send" }).click();
    await expect(
      page.getByText(/model unavailable — .*question is recorded/),
    ).toBeVisible({ timeout: 20000 });
    await page.getByLabel("raise a question").fill("method for film check?");
    await page.getByRole("button", { name: "raise" }).click();
    await expect(
      page.getByText(/method for film check\?/),
    ).toBeVisible({ timeout: 15000 });

    // contract — a declared unknown makes the freeze VISIBLY refuse
    // until resolved; the method revision stays unbound after freeze
    // (missing method remains visibly unresolved)
    await page
      .locator('nav[aria-label="task sections"]')
      .getByRole("link", { name: "overview" })
      .click();
    await freezeContractViaUi(
      page,
      {
        label: "dry time",
        id: "metric.dry-time",
        operator: "lte",
        target: "60",
      },
      {
        unknowns: ["validated method for dry-time"],
        resolveUnknownsOnFreeze: true,
      },
    );
    const contractReadonly = page.locator(
      '[aria-label="success contract editor"]',
    );
    // a contract revision IS frozen…
    await expect(
      contractReadonly.getByText(/current frozen: rev/),
    ).toBeVisible();
    // …but the unresolved declaration stays visibly unresolved on the
    // working draft — it is not swept away by the freeze, and the
    // freeze refusal remains on screen
    const unknownLi = contractReadonly
      .getByRole("list", { name: "declared unknowns" })
      .locator("li");
    await expect(unknownLi).toHaveCount(1);
    await expect(unknownLi.first()).toContainText(
      "validated method for dry-time",
    );
    await expect(
      contractReadonly
        .getByRole("alert")
        .filter({ hasText: "cannot be frozen" }),
    ).toBeVisible();
    // and the working draft's method revision stays unbound — the
    // missing method remains visibly unresolved
    const methodInput = contractReadonly
      .getByLabel("method revision")
      .first();
    await expect(methodInput).toHaveValue("");

    // eligible candidate bound to the registered identity (UI)
    await acceptCandidateViaUi(page, taskUrl, {
      hypothesis: "bio-binder reduces VOC",
      entityKind: "material",
      entitySearch: `${RUN} binder`,
      entityPick: new RegExp(`${RUN} binder`),
    });

    // manual experimental feedback: approved plan → recorded +
    // reviewed measurement (all UI)
    await approvePlanViaUi(page, {
      title: `${RUN} dry check`,
      candidatePick: /material candidate rev 1 · bio-binder/,
      // the frozen head is the revision the resolve-freeze path produced
      contractPick: /contract rev \d+ · frozen/,
    });
    await recordAcceptedMeasurementViaUi(page, {
      planTitle: `${RUN} dry check`,
      method: "manual-drytime",
      metric: "metric.dry-time",
      value: "45",
    });

    // engine/model-dependent capability stays reported as unavailable —
    // the models registry is honestly empty, never a validation claim
    await page
      .locator('nav[aria-label="task sections"]')
      .getByRole("link", { name: "advanced" })
      .click();
    await page
      .locator('nav[aria-label="section views"]')
      .getByRole("link", { name: "models" })
      .click();
    await expect(
      page.getByText("No model releases registered yet."),
    ).toBeVisible();

    // reviewer activation (API) before the closeout loop
    const discTaskGid = decodeURIComponent(
      taskUrl.split("/tasks/")[1].split("/")[0],
    );
    await transition(token, discTaskGid, "active");

    // closeout: the recorded manual evidence supports the verdict
    await gotoCloseout(page, taskUrl);
    await expect(
      page.locator('text=suggestion: supported_success'),
    ).toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "send to review" }).click();
    await expect(page.locator('[data-field="close-form"]')).toBeVisible({
      timeout: 15000,
    });
    await page.locator("#closure-decision").selectOption("supported_success");
    await page
      .locator("text=I confirm this closure as the human reviewer")
      .click();
    await page.getByRole("button", { name: "close task" }).click();
    await expect(page.locator('[data-field="closed-note"]')).toBeVisible({
      timeout: 15000,
    });
  });
});

// ==================================================================
// adversarial evaluation coverage (PAR-01..05 semantics at e2e level)
//
// These seeds use the API for states the UI cannot author — structured
// absence-gate checks, per-candidate applicability bindings, historical
// executions. The states under test (evaluation report, close gating,
// provenance honesty) are asserted through the real closeout UI AND
// the taskEvaluation read path. Expected outcomes are the honest
// failures: inconclusive / not_evaluated / not eligible — never
// coerced successes.
// ==================================================================

async function seedProject(token: string, slug: string, name: string) {
  const r = await gql(
    token,
    `mutation ($s: String!, $n: String!) { projectCreate(
       input: {slug: $s, name: $n}) {
       project { id } errors { code message } } }`,
    { s: slug, n: name },
  );
  expect(r.data.projectCreate.errors ?? []).toEqual([]);
  return r.data.projectCreate.project.id as string;
}

async function seedTask(token: string, projectId: string, title: string) {
  const r = await gql(
    token,
    `mutation ($p: ID!, $t: String!) { taskCreate(input: {projectId: $p,
       title: $t, mode: "discover", targetKind: "formulation",
       objective: "adversarial fixture"}) {
       task { id } errors { code message } } }`,
    { p: projectId, t: title },
  );
  expect(r.data.taskCreate.errors ?? []).toEqual([]);
  return r.data.taskCreate.task.id as string;
}

/** Frozen contract with an arbitrary payload — needed for the
 * structured `check` objects the editor cannot author (PAR-03). */
async function seedFrozenContract(
  token: string,
  taskId: string,
  payload: Record<string, unknown>,
): Promise<{ revGid: string; revUuid: string }> {
  const d = await gql(
    token,
    `mutation ($t: ID!, $p: JSON!) { contractDraftCreate(
       input: { taskId: $t, payload: $p }) {
       contractRevision { id } errors { code message } } }`,
    { t: taskId, p: payload },
  );
  expect(d.data.contractDraftCreate.errors ?? []).toEqual([]);
  const revGid = d.data.contractDraftCreate.contractRevision.id as string;
  const f = await gql(
    token,
    `mutation ($r: ID!) { contractFreeze(input: { revisionId: $r }) {
       contractRevision { id } errors { code message } } }`,
    { r: revGid },
  );
  expect(f.data.contractFreeze.errors ?? []).toEqual([]);
  return { revGid, revUuid: decodeGlobalId(revGid) };
}

async function seedAcceptedCandidate(
  token: string,
  taskId: string,
  hypothesis: string,
): Promise<{ gid: string; uuid: string }> {
  const c = await gql(
    token,
    `mutation ($t: ID!, $h: String!) { candidates { create(input: {
       taskId: $t, entityKind: "formulation", hypothesis: $h }) {
       candidate { id } errors { code message } } } }`,
    { t: taskId, h: hypothesis },
  );
  expect(c.data.candidates.create.errors ?? []).toEqual([]);
  const gid = c.data.candidates.create.candidate.id as string;
  const sub = await gql(
    token,
    `mutation ($c: ID!) { candidates { submit(input: {candidateId: $c}) {
       candidate { id } errors { code message } } } }`,
    { c: gid },
  );
  expect(sub.data.candidates.submit.errors ?? []).toEqual([]);
  const acc = await gql(
    token,
    `mutation ($c: ID!) { candidates { review(input: {candidateId: $c,
       accept: true}) { candidate { id } errors { code message } } } }`,
    { c: gid },
  );
  expect(acc.data.candidates.review.errors ?? []).toEqual([]);
  return { gid, uuid: decodeGlobalId(gid) };
}

/** Accepted measurement on a historical-import execution — the only
 * execution kind seedable without a plan (allowed: the UI cannot open
 * an execution without the full plan lifecycle). */
async function seedMeasurement(
  token: string,
  taskId: string,
  opts: { method: string; metric: string; value: string },
): Promise<string> {
  const ex = await gql(
    token,
    `mutation ($t: ID!) { lab { measurements { executionHistoricalImport(
       input: {taskId: $t, payload: {source: "e2e-adversarial"}}) {
       execution { id } errors { code message } } } } }`,
    { t: taskId },
  );
  expect(
    ex.data.lab.measurements.executionHistoricalImport.errors ?? [],
  ).toEqual([]);
  const exId = ex.data.lab.measurements.executionHistoricalImport.execution.id;
  const b = await gql(
    token,
    `mutation ($i: ID!) { lab { measurements { batchAdd(
       input: {executionId: $i, label: "A"}) {
       batch { id } errors { code message } } } } }`,
    { i: exId },
  );
  const s = await gql(
    token,
    `mutation ($i: ID!) { lab { measurements { sampleAdd(
       input: {batchId: $i, label: "a1", kind: "aliquot"}) {
       sample { id } errors { code message } } } } }`,
    { i: b.data.lab.measurements.batchAdd.batch.id },
  );
  const rec = await gql(
    token,
    `mutation ($i: MeasurementRecordInput!) { lab { measurements {
       measurementRecord(input: $i) {
       measurement { id } errors { code message } } } } }`,
    {
      i: {
        sampleId: s.data.lab.measurements.sampleAdd.sample.id,
        method: opts.method,
        repeatType: "independent_batch",
        metric: opts.metric,
        value: { kind: "numeric", value: opts.value, unit: "dimensionless" },
      },
    },
  );
  expect(
    rec.data.lab.measurements.measurementRecord.errors ?? [],
  ).toEqual([]);
  const mid = rec.data.lab.measurements.measurementRecord.measurement
    .id as string;
  const rev = await gql(
    token,
    `mutation ($i: MeasurementReviewInput!) { lab { measurements {
       measurementReview(input: $i) {
       measurement { id status } errors { code message } } } } }`,
    { i: { measurementId: mid, decision: "accepted" } },
  );
  expect(
    rev.data.lab.measurements.measurementReview.errors ?? [],
  ).toEqual([]);
  return mid;
}

/** Reviewed measurement→candidate applicability binding (PAR-02 §4) —
 * the state the UI has no authoring surface for. */
async function bindMeasurement(
  token: string,
  measurementGid: string,
  candidateGid: string,
) {
  const r = await gql(
    token,
    `mutation ($i: MeasurementApplicabilityMapInput!) { lab { measurements {
       measurementMapApplicability(input: $i) {
       mappingId errors { code message } } } } }`,
    {
      i: {
        measurementId: measurementGid,
        candidateRevisionId: candidateGid,
        applicable: true,
        rationale: "e2e adversarial binding",
      },
    },
  );
  expect(
    r.data.lab.measurements.measurementMapApplicability.errors ?? [],
  ).toEqual([]);
}

async function transition(token: string, taskId: string, toState: string) {
  const r = await gql(
    token,
    `mutation ($i: TaskTransitionInput!) { taskTransition(input: $i) {
       task { id workflowState } errors { code message } } }`,
    { i: { taskId, toState } },
  );
  expect(r.data.taskTransition.errors ?? []).toEqual([]);
}

async function evaluation(token: string, taskId: string) {
  const r = await gql(
    token,
    `query ($t: ID!) { taskEvaluation(taskId: $t) }`,
    { t: taskId },
  );
  return r.data.taskEvaluation;
}

test.describe("PAR-10 adversarial evaluation (PAR-01..05)", () => {
  // PAR-02 — best-of pooling across accepted candidates must never
  // manufacture a supported_success: each candidate is reported on its
  // own bound evidence only.
  test("PAR-02: candidates are reported separately — spread-out metrics stay supported_failure", async ({
    page,
    context,
  }) => {
    test.setTimeout(120_000);
    const RUN = `par10a2-${Date.now()}`;
    const token = await signIn(context);
    const taskId = await seedTask(
      token,
      await seedProject(token, RUN, `PAR-10 adv ${RUN}`),
      `${RUN} pooling check`,
    );
    await seedFrozenContract(token, taskId, {
      metrics: [
        {
          id: "metric.alpha",
          label: "alpha",
          required: true,
          operator: "gte",
          target_values: ["5"],
          unit: "dimensionless",
          required_evidence: ["lab_measurement"],
          aggregation: "single",
        },
        {
          id: "metric.beta",
          label: "beta",
          required: true,
          operator: "gte",
          target_values: ["5"],
          unit: "dimensionless",
          required_evidence: ["lab_measurement"],
          aggregation: "single",
        },
      ],
      hard_constraints: [],
    });
    const candA = await seedAcceptedCandidate(token, taskId, `${RUN} A`);
    const candB = await seedAcceptedCandidate(token, taskId, `${RUN} B`);
    // A: alpha met + beta failed; B: alpha failed + beta met. Pooled,
    // both metrics would pass — the evaluator must NOT pool them.
    const mA1 = await seedMeasurement(token, taskId, {
      method: "manual-index",
      metric: "metric.alpha",
      value: "7",
    });
    const mA2 = await seedMeasurement(token, taskId, {
      method: "manual-index",
      metric: "metric.beta",
      value: "2",
    });
    const mB1 = await seedMeasurement(token, taskId, {
      method: "manual-index",
      metric: "metric.alpha",
      value: "1",
    });
    const mB2 = await seedMeasurement(token, taskId, {
      method: "manual-index",
      metric: "metric.beta",
      value: "9",
    });
    await bindMeasurement(token, mA1, candA.gid);
    await bindMeasurement(token, mA2, candA.gid);
    await bindMeasurement(token, mB1, candB.gid);
    await bindMeasurement(token, mB2, candB.gid);

    const report = await evaluation(token, taskId);
    expect(report.candidates).toHaveLength(2);
    for (const c of report.candidates) {
      const verdicts = Object.fromEntries(
        c.metrics.map((m: { metricId: string; verdict: string }) => [
          m.metricId,
          m.verdict,
        ]),
      );
      // each candidate misses exactly one required metric on its own
      // bound evidence — pooling would flip both to met
      expect(Object.values(verdicts)).toContain("misses");
      expect(Object.values(verdicts)).toContain("met");
      expect(c.suggestedDecision).toBe("supported_failure");
      expect(c.supportedSuccessEligible).toBe(false);
    }
    expect(report.supportedSuccessEligible).toBe(false);

    // the close command enforces the same gates server-side
    await transition(token, taskId, "active");
    await transition(token, taskId, "awaiting_review");
    // with >1 accepted candidates the close REFUSES to pick one — an
    // explicit candidateRevisionId is required (PAR-02 §6)
    const closeNoCand = await gql(
      token,
      `mutation ($i: TaskCloseInput!) { taskClose(input: $i) {
         task { id } errors { code message } } }`,
      { i: { taskId, closureDecision: "supported_success" } },
    );
    expect(closeNoCand.data.taskClose.errors[0].code).toBe("VALIDATION");
    // and a bound candidate cannot close as supported_success on
    // evidence that fails a required metric
    const close = await gql(
      token,
      `mutation ($i: TaskCloseInput!) { taskClose(input: $i) {
         task { id } errors { code message } } }`,
      {
        i: {
          taskId,
          closureDecision: "supported_success",
          candidateRevisionId: candA.gid,
        },
      },
    );
    expect(close.data.taskClose.errors[0].code).toBe("EVIDENCE_INSUFFICIENT");

    // and the closeout UI says the same: two rows, explicit no-pooling
    // note, per-candidate reports, supported_success disabled for the
    // selected (ineligible) candidate
    await page.goto(
      `/tasks/${encodeURIComponent(taskId)}/decisions?view=closeout`,
    );
    await expect(
      page.getByText(/each is reported separately and no pooled verdict/),
    ).toBeVisible({ timeout: 15000 });
    const rows = page.locator('[data-field="candidate-row"]');
    await expect(rows).toHaveCount(2);
    await expect(
      rows.locator('[data-field="candidate-verdict"]'),
    ).toHaveText(["supported_failure", "supported_failure"]);
    await rows.first().locator('input[name="evaluation-candidate"]').check();
    const sel = page.locator('[data-field="selected-candidate-report"]');
    await expect(
      sel.locator('[data-field="metric-row"][data-verdict="met"]'),
    ).toHaveCount(1);
    await expect(
      sel.locator('[data-field="metric-row"][data-verdict="misses"]'),
    ).toHaveCount(1);

    // task is already awaiting_review → the close form is up; the
    // candidate selector must be bound and success stays disabled
    await expect(page.locator('[data-field="close-form"]')).toBeVisible({
      timeout: 15000,
    });
    await expect(
      page.locator('#closure-decision option[value="supported_success"]'),
    ).toBeDisabled();
  });

  // PAR-03 — a structured ingredient_absent gate on a candidate with
  // no bound composition must report not_evaluated (fail safe), and the
  // close gate refuses supported_success.
  test("PAR-03: absence gate on unbound composition stays not_evaluated — success close refused", async ({
    page,
    context,
  }) => {
    test.setTimeout(120_000);
    const RUN = `par10a3-${Date.now()}`;
    const token = await signIn(context);
    const taskId = await seedTask(
      token,
      await seedProject(token, RUN, `PAR-10 adv ${RUN}`),
      `${RUN} absence gate`,
    );
    const ident = await gql(
      token,
      `mutation ($n: String!) { materials { identityCreate(input: {
         kind: "substance_class", name: $n,
         identifiers: [{scheme: "cas", value: "x-${RUN}"}]}) {
         identity { id } errors { code message } } } }`,
      { n: `${RUN} solvent` },
    );
    expect(ident.data.materials.identityCreate.errors ?? []).toEqual([]);
    const identityUuid = decodeGlobalId(
      ident.data.materials.identityCreate.identity.id as string,
    );
    // structured check — the editor deliberately cannot author this;
    // seeded via API so the evaluaded gate state is under test
    await seedFrozenContract(token, taskId, {
      metrics: [
        {
          id: "metric.synthetic-performance",
          label: "index",
          required: true,
          operator: "gte",
          target_values: ["5"],
          unit: "dimensionless",
          required_evidence: ["lab_measurement"],
          aggregation: "single",
        },
      ],
      hard_constraints: [
        {
          id: "gate.solvent-absent",
          text: "excluded solvent must not be present",
          check: {
            kind: "ingredient_absent",
            materialIdentityId: identityUuid,
          },
        },
      ],
    });
    const cand = await seedAcceptedCandidate(token, taskId, `${RUN} no entity`);
    // a metric that would pass must NOT lift the unproven gate
    const m = await seedMeasurement(token, taskId, {
      method: "manual-index",
      metric: "metric.synthetic-performance",
      value: "7",
    });
    await bindMeasurement(token, m, cand.gid);

    const report = await evaluation(token, taskId);
    const gate = report.candidates[0].gates.find(
      (g: { id: string }) => g.id === "gate.solvent-absent",
    );
    expect(gate.verdict).toBe("not_evaluated");
    expect(report.candidates[0].supportedSuccessEligible).toBe(false);

    await transition(token, taskId, "active");
    await transition(token, taskId, "awaiting_review");
    const close = await gql(
      token,
      `mutation ($i: TaskCloseInput!) { taskClose(input: $i) {
         task { id } errors { code message } } }`,
      { i: { taskId, closureDecision: "supported_success" } },
    );
    expect(close.data.taskClose.errors[0].code).toBe("EVIDENCE_INSUFFICIENT");

    await page.goto(
      `/tasks/${encodeURIComponent(taskId)}/decisions?view=closeout`,
    );
    const sel = page.locator('[data-field="selected-candidate-report"]');
    await expect(
      sel.locator('[data-field="gate-row"][data-verdict="not_evaluated"]'),
    ).toHaveCount(1, { timeout: 15000 });
    // single accepted candidate → auto-selected; close form is up and
    // the success option stays disabled behind the unproven gate
    await expect(
      page.locator('#closure-decision option[value="supported_success"]'),
    ).toBeDisabled();
  });

  // PAR-04 — aggregation "single" means exactly one effective reading:
  // two conflicting accepted readings produce inconclusive, never a
  // silently picked pass.
  test("PAR-04: conflicting readings under aggregation 'single' stay inconclusive", async ({
    page,
    context,
  }) => {
    test.setTimeout(120_000);
    const RUN = `par10a4-${Date.now()}`;
    const token = await signIn(context);
    const taskId = await seedTask(
      token,
      await seedProject(token, RUN, `PAR-10 adv ${RUN}`),
      `${RUN} conflicting readings`,
    );
    await seedFrozenContract(token, taskId, {
      metrics: [
        {
          id: "metric.film-index",
          label: "film index",
          required: true,
          operator: "gte",
          target_values: ["5"],
          unit: "dimensionless",
          required_evidence: ["lab_measurement"],
          aggregation: "single",
        },
      ],
      hard_constraints: [],
    });
    const cand = await seedAcceptedCandidate(token, taskId, `${RUN} cand`);
    // same metric, two accepted readings on opposite sides of the
    // threshold — single aggregation cannot pick a winner
    const pass = await seedMeasurement(token, taskId, {
      method: "manual-index",
      metric: "metric.film-index",
      value: "7",
    });
    const fail = await seedMeasurement(token, taskId, {
      method: "manual-index",
      metric: "metric.film-index",
      value: "2",
    });
    await bindMeasurement(token, pass, cand.gid);
    await bindMeasurement(token, fail, cand.gid);

    const report = await evaluation(token, taskId);
    const metric = report.candidates[0].metrics.find(
      (m: { metricId: string }) => m.metricId === "metric.film-index",
    );
    expect(metric.verdict).toBe("inconclusive");
    expect(metric.findings[0].kind).toBe("conflicting_readings");
    expect(report.candidates[0].suggestedDecision).toBe("inconclusive");
    expect(report.candidates[0].supportedSuccessEligible).toBe(false);

    await transition(token, taskId, "active");
    await transition(token, taskId, "awaiting_review");
    const close = await gql(
      token,
      `mutation ($i: TaskCloseInput!) { taskClose(input: $i) {
         task { id } errors { code message } } }`,
      { i: { taskId, closureDecision: "supported_success" } },
    );
    expect(close.data.taskClose.errors[0].code).toBe("EVIDENCE_INSUFFICIENT");

    await page.goto(
      `/tasks/${encodeURIComponent(taskId)}/decisions?view=closeout`,
    );
    const sel = page.locator('[data-field="selected-candidate-report"]');
    await expect(
      sel.locator('[data-field="metric-row"][data-verdict="inconclusive"]'),
    ).toHaveCount(1, { timeout: 15000 });
    await expect(
      sel.locator('[data-finding-kind="conflicting_readings"]').first(),
    ).toBeVisible();
    await expect(
      page.locator('#closure-decision option[value="supported_success"]'),
    ).toBeDisabled();
  });

  // PAR-05 — adding a real-origin record to a fixture packet makes the
  // composition honest (mixed, fixtureOnly=false) but it must NOT flip
  // validation to "validated": method + independent validation stay
  // missing, and the badge keeps saying "not scientific validation".
  test("PAR-05: a real-origin record yields mixed provenance — never validated", async ({
    page,
    context,
  }) => {
    test.setTimeout(120_000);
    const RUN = `par10a5-${Date.now()}`;
    const token = await signIn(context);
    const taskId = await seedTask(
      token,
      await seedProject(token, RUN, `PAR-10 adv ${RUN}`),
      `${RUN} provenance mix`,
    );
    await seedFrozenContract(token, taskId, {
      metrics: [
        {
          id: "metric.synthetic-performance",
          label: "index",
          required: true,
          operator: "gte",
          target_values: ["5"],
          unit: "dimensionless",
          required_evidence: ["lab_measurement"],
          aggregation: "single",
        },
      ],
      hard_constraints: [],
    });
    const cand = await seedAcceptedCandidate(token, taskId, `${RUN} cand`);
    // fixture-origin reading (name marker) + real-origin reading
    // (historical import, non-fixture method) — both bound to the cand
    const fx = await seedMeasurement(token, taskId, {
      method: "fixture-index",
      metric: "metric.synthetic-performance",
      value: "7",
    });
    const real = await seedMeasurement(token, taskId, {
      method: "manual-index",
      metric: "metric.other-observation",
      value: "9",
    });
    await bindMeasurement(token, fx, cand.gid);
    await bindMeasurement(token, real, cand.gid);

    const report = await evaluation(token, taskId);
    const prov = report.provenance.evidenceOrigin;
    // honest composition: mixed — not flipped to real_only, and
    // validation axes stay missing (no coercion to "validated")
    expect(prov.composition).toBe("mixed");
    expect(prov.counts.synthetic_fixture).toBe(1);
    expect(prov.counts.historical_report).toBe(1);
    expect(report.fixtureOnly).toBe(false);
    expect(report.provenance.methodValidation.status).toBe("missing");
    expect(
      report.provenance.independentValidation.status,
    ).toBe("not_validated");

    await transition(token, taskId, "active");
    await transition(token, taskId, "awaiting_review");
    await page.goto(
      `/tasks/${encodeURIComponent(taskId)}/decisions?view=closeout`,
    );
    await expect(
      page.getByText(/evidence: mixed \([^)]*\) — not scientific validation/),
    ).toBeVisible({ timeout: 15000 });
    // the badge names the real classes — fixture never becomes real
    await expect(page.getByText(/historical report/)).toBeVisible();
    // metric.synthetic-performance met; metric.other-observation isn't
    // a contract metric so the verdict stands met-only for the bound
    // one — success eligibility still requires every required metric
    // met; the fixture+real mix is reported, never upgraded
    const sel = page.locator('[data-field="selected-candidate-report"]');
    await expect(
      sel.locator('[data-field="metric-row"][data-verdict="met"]'),
    ).toHaveCount(1);
    await expect(
      page.locator('text=suggestion: supported_success'),
    ).toBeVisible();
  });
});
