import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { signIn } from "./at-1103-helpers";

const manifest = JSON.parse(readFileSync(resolve(__dirname, "../../docs/help-manifest.json"), "utf8")) as {
  articles: { section: string; slug: string; title: string }[];
};

test("help is signed in, keeps its destination, and browses without external network", async ({ page, context }) => {
  await signIn(context); // Provision only the disposable browser-test installation.
  await context.clearCookies();
  const external: string[] = [];
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1" && url.hostname !== "localhost") {
      external.push(url.origin);
      await route.abort();
    } else await route.continue();
  });
  await page.goto("/help/usage/notebooks-and-editing");
  await expect(page.getByRole("heading", { name: "Sign in", exact: true })).toBeVisible();
  await page.getByLabel("login").fill("e2e-owner");
  await page.getByLabel("password", { exact: true }).fill("e2e-password-10");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/help\/usage\/notebooks-and-editing$/);
  await expect(page.getByRole("article")).toBeVisible();
  const heading = page.locator(".cs-help-prose h2").first();
  const anchor = await heading.getAttribute("id");
  await page.getByRole("link", { name: `Link to ${await heading.getAttribute("aria-label")}`, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`#${anchor}$`));
  await page.reload();
  await expect(heading).toBeFocused();
  await page.getByRole("link", { name: "All documentation", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Help & documentation", exact: true })).toBeVisible();
  const search = page.getByRole("searchbox", { name: "Search documentation" });
  await search.fill("STUDIO_VAULT_ROOT");
  await expect(page.getByRole("heading", { name: "Search results", exact: true })).toBeVisible();
  await page.locator(".cs-help-results a").first().click();
  await expect(page.getByRole("article")).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Search results", exact: true })).toBeVisible();
  await expect(search).toHaveValue("STUDIO_VAULT_ROOT");
  await search.fill("no-such-article-5ad42");
  await expect(page.getByText(/No matching articles/)).toBeVisible();
  expect(external).toEqual([]);
});

test("every registered article loads in the production build, with readable mobile and dark layouts", async ({ page, context }, testInfo) => {
  test.setTimeout(180_000);
  await signIn(context);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await context.route("**/*", (route) => {
    const { hostname } = new URL(route.request().url());
    return hostname === "127.0.0.1" || hostname === "localhost" ? route.continue() : route.abort();
  });
  await page.goto("/help");
  await expect(page.getByRole("heading", { name: "Help & documentation" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("help-home.png"), fullPage: true });
  for (const item of manifest.articles) {
    await page.goto(`/help/${item.section}/${item.slug}`);
    await expect(page.getByRole("article", { name: item.title })).toBeVisible();
    await expect(page.locator(".cs-help-prose h1")).toBeVisible();
  }
  await page.goto("/help/usage/notebooks-and-editing");
  await expect(page.getByRole("article", { name: "Notebooks and editing" })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("article", { name: "Notebooks and editing" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.locator(".cs-help-prose h1").evaluate((heading) => heading.scrollIntoView({ block: "start" }));
  await page.screenshot({ path: testInfo.outputPath("help-article-mobile-dark.png") });
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await page.goto("/help/reference/does-not-exist");
  await expect(page.getByRole("heading", { name: "Article not found" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("agent documentation citations open the real handbook and close the mobile chat", async ({ page, context }, testInfo) => {
  await signIn(context);
  const now = "2026-11-02T00:00:00Z";
  const thread = {
    id: "documentation-test-thread", title: "Example documentation answer", updatedAt: now,
    messages: [
      { id: "question", role: "user", kind: "message", content: "What is a molecule?", refs: {}, createdAt: now },
      { id: "answer", role: "assistant", kind: "message", content: "A molecule is one defined structure, like a particular model assembled from building blocks. Read [Chemistry basics](/help/usage/chemistry-basics#a-molecule-is-one-structure).", refs: {}, createdAt: now },
    ], runs: [], hasEarlierMessages: false,
  };
  // This fixture verifies citation presentation; no model or provider is called.
  await page.route("**/api/agent-workspace/providers", (route) => route.fulfill({ json: { providers: [] } }));
  await page.route("**/api/learning-workspace/models", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/agent-workspace/threads**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/agent-workspace/threads") return route.fulfill({ json: { threads: [thread], nextOffset: null, query: "", ownerScope: "documentation-browser-fixture" } });
    if (path.endsWith(`/${thread.id}`)) return route.fulfill({ json: thread });
    return route.abort();
  });
  const response = await page.request.get("/api/agent-workspace/tools");
  expect(response.ok()).toBeTruthy();
  const catalog = await response.json();
  expect(catalog.tools.map((tool: { name: string }) => tool.name)).toEqual(expect.arrayContaining(["search_studio_docs", "read_studio_doc"]));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/help");
  await expect(page.getByRole("heading", { name: "Help & documentation" })).toBeVisible();
  await page.getByRole("button", { name: "Open research agent" }).click();
  await page.getByRole("button", { name: "Open chat: Example documentation answer" }).click();
  const link = page.getByRole("link", { name: "Chemistry basics", exact: true });
  await expect(link).toBeVisible();
  await expect(link).not.toHaveAttribute("target");
  await page.screenshot({ path: testInfo.outputPath("agent-documentation-citation-mobile.png") });
  await link.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/help\/usage\/chemistry-basics#a-molecule-is-one-structure$/);
  await expect(page.getByRole("button", { name: "Open research agent" })).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("heading", { name: "A molecule is one structure", exact: true })).toBeFocused();
});
