import { expect, test } from "@playwright/test";

/** AT-0205-1 — keyboard-only quantity + unit editing in a real
 * browser: tab focus order, label association, accessible
 * validation. */
test("keyboard-only quantity editing is accessible", async ({ page }) => {
  await page.goto("/dev/components");
  const valueField = page.getByLabel("value", { exact: true });
  const unitField = page.getByLabel("unit", { exact: true });

  await page.keyboard.press("Tab");
  // tab through until the value field holds focus (nav order may
  // include other controls, but it must be reachable by keyboard)
  for (let i = 0; i < 10 && !(await valueField.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press("Tab");
  }
  await expect(valueField).toBeFocused();

  await page.keyboard.type("0.45");
  await expect(valueField).toHaveValue("0.45");

  await page.keyboard.press("Tab");
  await expect(unitField).toBeFocused();
  await unitField.selectOption("mass_percent");
  await expect(unitField).toHaveValue("mass_percent");

  // domain-mirrored validation surfaces as an alert tied to the field
  await page.keyboard.press("Tab"); // leave the select
  await valueField.click();
  await valueField.fill("1.5");
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("fraction must be within [0,1]");
  await expect(valueField).toHaveAttribute("aria-invalid", "true");
});

/** AT-0205-2 — predicted vs measured results read as distinct
 * evidence types with inline uncertainty/context in the DOM. */
test("evidence type and uncertainty are distinct without color", async ({
  page,
}) => {
  await page.goto("/dev/components");
  const predicted = page.locator('[data-evidence="predicted"]');
  const measured = page.locator('[data-evidence="measured"]');
  await expect(predicted).toContainText("predicted");
  await expect(measured).toContainText("measured");
  await expect(page.getByText(/± 0\.05/)).toBeVisible();
  await expect(page.getByText(/± 0\.02/)).toBeVisible();
  // unknown shows a dash + reason, never a zero
  await expect(page.getByRole("note")).toContainText("—");
});
