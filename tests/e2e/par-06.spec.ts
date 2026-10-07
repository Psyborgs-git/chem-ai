import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";

/**
 * PAR-06 required regression: from a fresh test installation, the
 * explicitly supported owner bootstrap is the UI first-run form —
 * everything here is driven through the UI (no API helper performs a
 * step under test).
 *
 * Freshness: serve.sh truncates `studio_e2e` once per suite run, but
 * this spec needs a pristine install mid-suite, so it truncates again
 * in beforeAll (same TRUNCATE pattern; infra-only — no domain rows).
 * The owner creds match at-1103-helpers.ts so specs scheduled later
 * still sign in through their API-helper fallback.
 */
function truncateE2eDb() {
  const sql =
    "DO $$ DECLARE r RECORD; BEGIN " +
    "FOR r IN SELECT tablename FROM pg_tables " +
    "WHERE schemaname='public' AND tablename <> 'alembic_version' " +
    "LOOP EXECUTE 'TRUNCATE ' || quote_ident(r.tablename) || ' CASCADE'; " +
    "END LOOP; END $$;";
  execFileSync("docker", [
    "exec",
    "chem-studio-postgres",
    "psql",
    "-U",
    "studio",
    "-d",
    "studio_e2e",
    "-c",
    sql,
  ]);
}

test.beforeAll(() => {
  truncateE2eDb();
});

test("fresh install → bootstrap, sign-in, project + task in each mode, sign-out, re-login", async ({
  page,
  context,
}) => {
  // ── 1. fresh install: the first-run owner bootstrap is the only entry
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Set up Chemistry Studio" }),
  ).toBeVisible();
  await page.getByLabel("login").fill("e2e-owner");
  await page.getByLabel("display name").fill("E2E Owner");
  await page.getByLabel("password", { exact: true }).fill("e2e-password-10");
  await page.getByLabel("confirm password").fill("e2e-password-10");
  await page.getByRole("button", { name: "Create owner account" }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  await expect(page.getByText("Signed in as E2E Owner")).toBeVisible();

  // ── 2. sign out via the shell control → sign-in surface
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in" }),
  ).toBeVisible();

  // ── 3. bad credentials surface an honest error (no crash, no entry)
  await page.getByLabel("login").fill("e2e-owner");
  await page.getByLabel("password").fill("wrong-password-1");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText(/not recognized/)).toBeVisible();

  // ── 4. real sign-in
  await page.getByLabel("password").fill("e2e-password-10");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();

  // ── 5. session gone mid-work → sign-in surface at the same URL,
  //       and signing back in returns to it
  await page.goto("/projects");
  await expect(
    page.getByRole("heading", { name: "Projects" }),
  ).toBeVisible();
  await context.clearCookies();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Sign in" }),
  ).toBeVisible();
  await page.getByLabel("login").fill("e2e-owner");
  await page.getByLabel("password").fill("e2e-password-10");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  await expect(page).toHaveURL(/\/projects/);

  // ── 6. create a project through the UI (create → select is one step)
  await page.getByLabel("project slug").fill("par06-proj");
  await page.getByLabel("project name").fill("PAR-06 Project");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page).toHaveURL(/\/projects\//);
  await expect(
    page.getByRole("heading", { name: "Project" }),
  ).toBeVisible();
  const projectPath = new URL(page.url()).pathname;

  // ── 7. one task in each mode the create form offers
  const modes = [
    { title: "improve run", label: "improve an existing formulation" },
    { title: "match run", label: "match a reference product" },
    { title: "discover run", label: "discover something new" },
  ];
  for (const m of modes) {
    await page.getByLabel("task title").fill(m.title);
    await page.getByLabel("research mode").selectOption({ label: m.label });
    await page
      .getByRole("button", { name: /Create task/ })
      .click();
    await expect(page).toHaveURL(/\/tasks\//);
    await expect(page.getByText(m.title).first()).toBeVisible();
    await page.goto(projectPath);
  }
  await expect(page.getByRole("link", { name: "improve run" })).toBeVisible();
  await expect(page.getByRole("link", { name: "match run" })).toBeVisible();
  await expect(page.getByRole("link", { name: "discover run" })).toBeVisible();

  // ── 8. sign out and sign back in: work is still there
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in" }),
  ).toBeVisible();
  await page.getByLabel("login").fill("e2e-owner");
  await page.getByLabel("password").fill("e2e-password-10");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();

  await page.goto("/projects");
  await page.getByRole("link", { name: "PAR-06 Project" }).click();
  await expect(page).toHaveURL(/\/projects\//);
  await expect(page.getByRole("link", { name: "improve run" })).toBeVisible();
  await expect(page.getByRole("link", { name: "match run" })).toBeVisible();
  await expect(page.getByRole("link", { name: "discover run" })).toBeVisible();
});
