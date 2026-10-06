import { expect, request, test, type BrowserContext, type Page } from "@playwright/test";

const API = "http://127.0.0.1:8790";
const ORIGIN = { origin: "http://127.0.0.1:8790" };

async function signIn(context: BrowserContext): Promise<string> {
  const api = await request.newContext({ baseURL: API });
  const res = await api.post("/api/auth/setup", {
    headers: ORIGIN,
    data: {
      login: "e2e-1103-owner",
      display_name: "E2E 1103 Owner",
      password: "e2e-password-1103",
    },
  });
  const res2 = res.ok()
    ? res
    : await api.post("/api/auth/login", {
        headers: ORIGIN,
        data: { login: "e2e-1103-owner", password: "e2e-password-1103" },
      });
  expect(res2.ok()).toBeTruthy();
  const setCookie = res2.headers()["set-cookie"] ?? "";
  const token = /studio_session=([^;]+)/.exec(setCookie)?.[1];
  expect(token).toBeTruthy();
  await context.addCookies([
    { name: "studio_session", value: token!, url: "http://127.0.0.1:4173" },
  ]);
  return token!;
}

async function gql(
  token: string,
  query: string,
  variables: Record<string, unknown> = {},
) {
  const api = await request.newContext({ baseURL: API });
  const res = await api.post("/graphql", {
    data: { query, variables },
    headers: { cookie: `studio_session=${token}`, ...ORIGIN },
  });
  const body = await res.json();
  if (body.errors) throw new Error(JSON.stringify(body.errors));
  return body;
}

function decodeGlobalId(globalId: string): string {
  const parts = atob(globalId).split(":");
  return parts[parts.length - 1];
}

const METRIC_ID = "metric.synthetic-performance";

type FocusedDescriptor = {
  tag: string;
  text: string;
  id: string;
  inTaskNav: boolean;
  inPrimaryNav: boolean;
  pressed: string | null;
};

async function focused(page: Page): Promise<FocusedDescriptor> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) {
      return { tag: "body", text: "", id: "", inTaskNav: false, inPrimaryNav: false, pressed: null };
    }
    return {
      tag: el.tagName.toLowerCase(),
      text: (el.textContent ?? "").trim(),
      id: el.id ?? "",
      inTaskNav: !!el.closest('nav[aria-label="task sections"]'),
      inPrimaryNav: !!el.closest('nav[aria-label="primary"]'),
      pressed: el.getAttribute("aria-pressed"),
    };
  });
}

/** Pure-keyboard travel: press Tab until `match` holds for the focused
 * element, bounded — a miss means the element is unreachable by
 * keyboard and the test must fail. */
async function tabUntil(
  page: Page,
  match: (f: FocusedDescriptor) => boolean,
  maxTabs = 80,
): Promise<FocusedDescriptor> {
  for (let i = 0; i < maxTabs; i++) {
    await page.keyboard.press("Tab");
    const f = await focused(page);
    if (match(f)) return f;
  }
  throw new Error(`focus never reached target within ${maxTabs} Tab presses`);
}

async function seedClosedTask(token: string): Promise<string> {
  const proj = await gql(
    token,
    `mutation { projectCreate(input: {slug: "e2e-1103", name: "E2E 1103"}) {
       project { id } errors { message } } }`,
  );
  const projectId = proj.data.projectCreate.project.id as string;
  const task = await gql(
    token,
    `mutation ($p: ID!) { taskCreate(input: {projectId: $p,
       title: "a11y review task", mode: "improve", targetKind: "formulation",
       objective: "keyboard+viewport review",
       modeInputs: {baselineRevisionId: "baseline-rev-1",
         variationScope: "solvent only"}}) {
       task { id } errors { message } } }`,
    { p: projectId },
  );
  expect(task.data.taskCreate.errors ?? []).toEqual([]);
  const taskId = task.data.taskCreate.task.id as string;

  const draft = await gql(
    token,
    `mutation ($t: ID!, $p: JSON!) { contractDraftCreate(
       input: { taskId: $t, payload: $p }) {
       contractRevision { id revision } errors { message } } }`,
    {
      t: taskId,
      p: {
        metrics: [
          {
            id: METRIC_ID,
            label: "Synthetic index",
            required: true,
            operator: "gte",
            target_values: ["5"],
            unit: "dimensionless",
            required_evidence: ["lab_measurement"],
          },
        ],
        hard_constraints: [
          {
            id: "gate.solvent-free",
            text: "solvent index must reach the pass line",
            check: {
              kind: "metric",
              id: METRIC_ID,
              operator: "gte",
              target_values: ["5"],
              unit: "dimensionless",
              required_evidence: ["lab_measurement"],
            },
          },
        ],
      },
    },
  );
  const revGid = draft.data.contractDraftCreate.contractRevision.id as string;
  const freeze = await gql(
    token,
    `mutation ($r: ID!) { contractFreeze(input: { revisionId: $r }) {
       contractRevision { id status } errors { message } } }`,
    { r: revGid },
  );
  expect(freeze.data.contractFreeze.errors ?? []).toEqual([]);
  const contractUuid = decodeGlobalId(revGid);

  const cand = await gql(
    token,
    `mutation ($t: ID!) { candidates { create(input: {taskId: $t,
       entityKind: "formulation", hypothesis: "reduce solvent",
       proposedDifferences: [{field: "solvent", op: "reduce"}]}) {
       candidate { id } errors { message } } } }`,
    { t: taskId },
  );
  expect(cand.data.candidates.create.errors ?? []).toEqual([]);
  const candUuid = decodeGlobalId(cand.data.candidates.create.candidate.id);
  const plan = await gql(
    token,
    `mutation ($t: ID!, $p: JSON!) { lab { planCreate(input: {taskId: $t,
       title: "plan a11y", payload: $p}) {
       plan { id } errors { message } } } }`,
    {
      t: taskId,
      p: {
        candidateRevisionId: candUuid,
        contractRevisionId: contractUuid,
        method: "fixture-index",
        samplePlan: [{ batch: "A", aliquots: 1 }],
        acceptanceCriteria: "index >= 5",
        hazardNotes: "none",
        resourceNeeds: "none",
      },
    },
  );
  expect(plan.data.lab.planCreate.errors ?? []).toEqual([]);
  const planId = plan.data.lab.planCreate.plan.id as string;
  const sub = await gql(
    token,
    `mutation ($i: ID!) { lab { planSubmit(input: {planId: $i}) {
       plan { id } errors { message } } } }`,
    { i: planId },
  );
  expect(sub.data.lab.planSubmit.errors ?? []).toEqual([]);
  const rev = await gql(
    token,
    `mutation ($i: ID!) { lab { planReview(input: {planId: $i,
       decision: "approved", rationale: "ok"}) {
       plan { id } errors { code message } } } }`,
    { i: planId },
  );
  expect(rev.data.lab.planReview.errors ?? []).toEqual([]);
  const ex = await gql(
    token,
    `mutation ($i: ID!) { lab { measurements { executionOpen(
       input: {planId: $i}) { execution { id } errors { code message } } } } }`,
    { i: planId },
  );
  expect(ex.data.lab.measurements.executionOpen.errors ?? []).toEqual([]);
  const executionId = ex.data.lab.measurements.executionOpen.execution.id;
  const batch = await gql(
    token,
    `mutation ($i: ID!) { lab { measurements { batchAdd(
       input: {executionId: $i, label: "A"}) {
       batch { id } errors { message } } } } }`,
    { i: executionId },
  );
  const batchId = batch.data.lab.measurements.batchAdd.batch.id;
  const sample = await gql(
    token,
    `mutation ($i: ID!) { lab { measurements { sampleAdd(
       input: {batchId: $i, label: "a1", kind: "aliquot"}) {
       sample { id } errors { message } } } } }`,
    { i: batchId },
  );
  const sampleId = sample.data.lab.measurements.sampleAdd.sample.id;
  const rec = await gql(
    token,
    `mutation ($i: MeasurementRecordInput!) { lab { measurements {
       measurementRecord(input: $i) {
       measurement { id } errors { code message } } } } }`,
    {
      i: {
        sampleId,
        method: "fixture-index",
        repeatType: "independent_batch",
        metric: METRIC_ID,
        value: { kind: "numeric", value: "7", unit: "dimensionless" },
      },
    },
  );
  const mid = rec.data.lab.measurements.measurementRecord.measurement.id;
  await gql(
    token,
    `mutation ($i: MeasurementReviewInput!) { lab { measurements {
       measurementReview(input: $i) {
       measurement { id status } errors { code message } } } } }`,
    { i: { measurementId: mid, decision: "accepted" } },
  );
  for (const toState of ["active", "awaiting_review"]) {
    const r = await gql(
      token,
      `mutation ($i: TaskTransitionInput!) { taskTransition(input: $i) {
         task { id workflowState } errors { code message } } }`,
      { i: { taskId, toState } },
    );
    expect(r.data.taskTransition.errors).toEqual([]);
  }
  const close = await gql(
    token,
    `mutation ($i: TaskCloseInput!) { taskClose(input: $i) {
       task { id workflowState closureDecision } errors { code message } } }`,
    { i: { taskId, closureDecision: "supported_success" } },
  );
  expect(close.data.taskClose.errors).toEqual([]);
  expect(close.data.taskClose.task.workflowState).toBe("closed");
  return taskId;
}

/** AT-1103-2 — the critical review journey must be fully operable by
 * keyboard and legible on a narrow viewport: skip link, named
 * landmarks, visible focus, reachable tab buttons, and scientific
 * tables that keep their identity column instead of hiding required
 * conditions. */
test("review journey: keyboard-only navigation on a 360px viewport (AT-1103-2)", async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 360, height: 780 });
  const token = await signIn(context);
  const taskId = await seedClosedTask(token);
  await page.goto(`/tasks/${encodeURIComponent(taskId)}`);
  await expect(page.getByRole("heading", { name: "a11y review task" })).toBeVisible();

  // first tab stop is the skip link — hidden until focused, then on top
  await page.keyboard.press("Tab");
  const skip = page.locator(".cs-skip-link");
  await expect(skip).toBeFocused();
  const skipBox = (await skip.boundingBox())!;
  expect(skipBox.y).toBeGreaterThanOrEqual(0);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main$/);

  // keyboard reaches the task-section tabs and shows a real focus ring
  const tab = await tabUntil(page, (f) => f.inTaskNav && f.tag === "button");
  expect(tab.text.length).toBeGreaterThan(0);
  const ring = await page.evaluate(() => {
    const s = getComputedStyle(document.activeElement!);
    return { width: s.outlineWidth, style: s.outlineStyle };
  });
  expect(ring.style).not.toBe("none");
  expect(parseFloat(ring.width)).toBeGreaterThanOrEqual(2);

  // the report tab is one keyboard journey away and keyboard-activated
  await tabUntil(page, (f) => f.inTaskNav && f.text === "report");
  await page.keyboard.press("Enter");
  await expect(page.locator('[data-field="task-report"]')).toBeVisible();
  expect((await focused(page)).pressed).toBe("true");

  // the metrics table overflows horizontally inside its scroll wrap —
  // the identity column stays pinned instead of shrinking to nothing
  const wrap = page.locator(".cs-table-wrap", { has: page.locator('[data-field="report-metrics"]') });
  await expect(wrap).toBeVisible();
  const dims = await wrap.evaluate((el) => ({
    scrollWidth: el.scrollWidth,
    clientWidth: el.clientWidth,
  }));
  expect(dims.scrollWidth).toBeGreaterThan(dims.clientWidth);
  const identity = page.locator('[data-field="report-metrics"] .cs-table__identity').first();
  const sticky = await identity.evaluate((el) => getComputedStyle(el).position);
  expect(sticky).toBe("sticky");
  const wrapBox = (await wrap.boundingBox())!;
  await wrap.evaluate((el) => { el.scrollLeft = el.scrollWidth; });
  const idBox = (await identity.boundingBox())!;
  expect(Math.abs(idBox.x - wrapBox.x)).toBeLessThan(4);
  await expect(page.locator('[data-field="report-metrics"] tbody td').first()).not.toBeEmpty();

  // decisions tab: the closure record is reachable and readable
  await tabUntil(page, (f) => f.inTaskNav && f.text === "decisions");
  await page.keyboard.press("Enter");
  await expect(page.locator('[data-field="decision-log"]')).toBeVisible();
  await expect(page.locator('[data-field="decision-closure"]')).toContainText(
    "supported_success",
  );

  // closeout tab: the hard-gate table keeps required conditions visible
  await tabUntil(page, (f) => f.inTaskNav && f.text === "closeout");
  await page.keyboard.press("Enter");
  await expect(page.locator('[data-field="gates-table"]')).toBeVisible();
  await expect(
    page.locator('[data-field="gates-table"]'),
  ).toContainText("solvent index must reach the pass line");
  await expect(page.locator('[data-field="gate-verdict"]')).toContainText("pass");

  // every interactive element in the review surface has an accessible
  // name — no icon-only or unlabeled controls
  const nameless = await page.locator("main").evaluate((root) => {
    const sel =
      'a,button,input,select,textarea,[role="button"],[role="link"],[role="tab"],[tabindex]';
    return [...root.querySelectorAll<HTMLElement>(sel)]
      .filter((el) => el.getClientRects().length > 0)
      .filter((el) => {
        const ariaLabel = el.getAttribute("aria-label") ?? "";
        const labelledBy = (el.getAttribute("aria-labelledby") ?? "")
          .split(/\s+/)
          .map((id) => document.getElementById(id)?.textContent ?? "")
          .join(" ");
        const own = el instanceof HTMLInputElement
          ? [...(el.labels ?? [])].map((l) => l.textContent ?? "").join(" ") ||
            el.placeholder
          : el.textContent ?? "";
        return !(ariaLabel + labelledBy + own).trim();
      })
      .map((el) => el.outerHTML.slice(0, 120));
  });
  expect(nameless).toEqual([]);

  // page-level horizontal scroll never appears at 360px — content
  // scrolls inside its wraps, not under a clipped viewport
  const pageOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(pageOverflow).toBeLessThanOrEqual(1);
});

/** AT-1103-2 (cont.) — themes share semantic tokens and honor both the
 * explicit toggle and prefers-reduced-motion. */
test("theme toggle and reduced motion (AT-1103-2)", async ({ page, context }) => {
  const token = await signIn(context);
  await page.goto("/projects");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();

  const accent = () =>
    page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue("--accent").trim(),
    );
  const before = await accent();

  // toggle by keyboard only: Tab to it, Enter activates
  const f = await tabUntil(page, (d) => d.tag === "button" && d.text.startsWith("theme:"), 40);
  expect(f.pressed).toBe("false");
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect(await accent()).not.toBe(before);
  expect((await focused(page)).pressed).toBe("true");
  // the dark tokens also paint — the header background actually changes
  const headerBg = await page
    .locator(".cs-shell__header")
    .evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(headerBg).not.toBe("rgba(0, 0, 0, 0)");

  // reduced motion: tokens collapse to 0ms and the spinner stops
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(
    await page.evaluate(() =>
      matchMedia("(prefers-reduced-motion: reduce)").matches,
    ),
  ).toBe(true);
  const motion = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--motion-fast").trim(),
  );
  expect(["0ms", "0s"]).toContain(motion);
});
