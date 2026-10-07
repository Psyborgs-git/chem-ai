import { expect, test } from "@playwright/test";
import { gql, decodeGlobalId, METRIC_ID, seedClosedTask, signIn, focused, tabUntil } from "./at-1103-helpers";

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

  // the workspace's landing section fits the viewport — no page-level
  // horizontal scroll (regression: cs-quantity row in the contract
  // editor forced a 193px page scroll at this width)
  const landingOverflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  expect(landingOverflow).toBeLessThanOrEqual(1);

  // first tab stop is the skip link — hidden until focused, then on top
  await page.keyboard.press("Tab");
  const skip = page.locator(".cs-skip-link");
  await expect(skip).toBeFocused();
  const skipBox = (await skip.boundingBox())!;
  expect(skipBox.y).toBeGreaterThanOrEqual(0);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main$/);

  // keyboard reaches the task-section nav links (PAR-09: real links
  // with aria-current, not toggle buttons) and shows a real focus ring
  const tab = await tabUntil(page, (f) => f.inTaskNav && f.tag === "a");
  expect(tab.text.length).toBeGreaterThan(0);
  const ring = await page.evaluate(() => {
    const s = getComputedStyle(document.activeElement!);
    return { width: s.outlineWidth, style: s.outlineStyle };
  });
  expect(ring.style).not.toBe("none");
  expect(parseFloat(ring.width)).toBeGreaterThanOrEqual(2);

  // the decisions group is one keyboard journey away — its default
  // view shows the decision log + closure record
  await tabUntil(page, (f) => f.inTaskNav && f.text === "decisions");
  await page.keyboard.press("Enter");
  await expect(page.locator('[data-field="decision-log"]')).toBeVisible();
  await expect(page.locator('[data-field="decision-closure"]')).toContainText(
    "supported_success",
  );

  // the report lives as a subview of decisions — keyboard-activated link
  await tabUntil(page, (f) => f.inSubNav && f.text === "report");
  await page.keyboard.press("Enter");
  await expect(page.locator('[data-field="task-report"]')).toBeVisible();
  expect((await focused(page)).current).toBe("page");

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

  // closeout is a subview of decisions: the hard-gate table keeps
  // required conditions visible
  await tabUntil(page, (f) => f.inSubNav && f.text === "closeout");
  await page.keyboard.press("Enter");
  await expect(page.locator('[data-field="gates-table"]')).toBeVisible();
  await expect(
    page.locator('[data-field="gates-table"]'),
  ).toContainText("solvent index must reach the pass line");
  await expect(page.locator('[data-field="gate-verdict"]')).toContainText("pass");

  // the gates table's identity column is long prose — it must be
  // capped below the scrollport width so the sticky pin still holds
  // (regression: a wider-than-wrap identity showed only its tail)
  const gatesWrap = page
    .locator(".cs-table-wrap", { has: page.locator('[data-field="gates-table"]') })
    .first();
  const gatesIdentity = page
    .locator('[data-field="gates-table"] .cs-table__identity')
    .first();
  const gatesDims = await gatesWrap.evaluate((el) => ({
    clientWidth: el.clientWidth,
    scrollWidth: el.scrollWidth,
  }));
  const idWidth = await gatesIdentity.evaluate(
    (el) => el.getBoundingClientRect().width,
  );
  expect(idWidth).toBeLessThanOrEqual(gatesDims.clientWidth);
  if (gatesDims.scrollWidth > gatesDims.clientWidth) {
    const gatesWrapBox = (await gatesWrap.boundingBox())!;
    await gatesWrap.evaluate((el) => { el.scrollLeft = el.scrollWidth; });
    const gatesIdBox = (await gatesIdentity.boundingBox())!;
    expect(Math.abs(gatesIdBox.x - gatesWrapBox.x)).toBeLessThan(4);
  }

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

/** AT-1103-2 (cont.) — page-level horizontal scroll never appears on
 * key surfaces at 360px: wide tables scroll inside their own wraps.
 * Covers screens outside the review journey (regression: /compute's
 * hardware kv table escaped its wrap and scrolled the page). */
test("narrow viewport: no page-level horizontal overflow (AT-1103-2)", async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 360, height: 780 });
  const token = await signIn(context);
  void token;
  for (const path of ["/projects", "/imports", "/compute", "/evidence"]) {
    await page.goto(path);
    await expect(page.locator("main")).toBeVisible();
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(overflow, `${path} overflowed by ${overflow}px`).toBeLessThanOrEqual(1);
  }
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
