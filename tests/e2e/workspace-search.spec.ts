import { expect, test } from "@playwright/test";
import { signIn } from "./at-1103-helpers";

test.use({ reducedMotion: "reduce" });

for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
  test(`workspace search keeps its geometry and readable results at ${viewport.width}px`, async ({ page, context }, testInfo) => {
    await signIn(context);
    await page.setViewportSize(viewport);
    await page.route("**/api/library/search?**", (route) => route.fulfill({ json: { results: [] } }));
    await page.goto("/help");
    const trigger = page.getByRole("button", { name: "Find your work", exact: true });
    if (viewport.width > 1000) {
      // Search is portaled outside the shell: opening chat must not hide its labels.
      await page.getByRole("button", { name: "Open research agent" }).click();
    } else await page.getByRole("button", { name: "Switch to dark theme" }).click();
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "Find your work" });
    const input = dialog.getByRole("combobox", { name: "Search your workspace" });
    await expect(input).toBeFocused();
    await expect(dialog.getByRole("option", { name: "Find papers", exact: true })).toBeVisible();
    // Measure settled geometry, including the shared dialog's entrance effect.
    await dialog.evaluate(async (element) => {
      await Promise.all(element.getAnimations().map((animation) => animation.finished.catch(() => {})));
    });
    const initial = await dialog.boundingBox();
    expect(initial).not.toBeNull();
    expect(initial!.width).toBeGreaterThan(viewport.width > 1000 ? 600 : 350);
    expect(initial!.x).toBeGreaterThanOrEqual(12);
    expect(initial!.y).toBeGreaterThanOrEqual(16);
    expect(initial!.y + initial!.height).toBeLessThanOrEqual(viewport.height - 15);
    const header = await input.boundingBox();
    const close = await dialog.getByRole("button", { name: "Close", exact: true }).boundingBox();
    expect(header!.height).toBe(44);
    expect(header!.width).toBeGreaterThan(viewport.width > 1000 ? 500 : 250);
    expect(header!.x + header!.width).toBeLessThanOrEqual(close!.x);
    const row = await dialog.getByRole("option", { name: "Find papers", exact: true }).boundingBox();
    expect(row!.height).toBeGreaterThanOrEqual(44);
    expect(row!.y).toBeGreaterThanOrEqual(header!.y + header!.height);
    await page.screenshot({ path: testInfo.outputPath(`search-${viewport.width}.png`) });
    await input.fill("no-such-work-9b713");
    await expect(dialog.getByText("No matching work. Try a task, paper, notebook, or destination.")).toBeVisible();
    const empty = await dialog.boundingBox();
    expect(empty!.width).toBe(initial!.width);
    expect(empty!.height).toBe(initial!.height);
    expect(empty!.y).toBe(initial!.y);
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();
    await trigger.click();
    await input.fill("Help");
    await expect(dialog.getByRole("option", { name: "Help & documentation", exact: true })).toBeVisible();
    await input.press("ArrowDown");
    await input.press("Enter");
    await expect(dialog).not.toBeVisible();
    await expect(page).toHaveURL(/\/help$/);
    if (viewport.width < 1000) {
      await page.setViewportSize({ width: viewport.width, height: 480 });
      await trigger.click();
      await dialog.evaluate(async (element) => {
        await Promise.all(element.getAnimations().map((animation) => animation.finished.catch(() => {})));
      });
      const compact = await dialog.boundingBox();
      expect(compact!.y + compact!.height).toBeLessThanOrEqual(464);
      await expect(input).toBeFocused();
      await page.screenshot({ path: testInfo.outputPath("search-short-viewport.png") });
    }
  });
}
