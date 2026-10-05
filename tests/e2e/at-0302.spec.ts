import { expect, request, test, type BrowserContext } from "@playwright/test";

const API = "http://127.0.0.1:8790";
const ORIGIN = { origin: "http://127.0.0.1:8790" };

async function signIn(context: BrowserContext): Promise<string> {
  const api = await request.newContext({ baseURL: API });
  const res = await api.post("/api/auth/setup", {
    headers: ORIGIN,
    data: { login: "e2e-owner", display_name: "E2E Owner", password: "e2e-password-10" },
  });
  const res2 = res.ok()
    ? res
    : await api.post("/api/auth/login", {
        headers: ORIGIN,
        data: { login: "e2e-owner", password: "e2e-password-10" },
      });
  expect(res2.ok()).toBeTruthy();
  const token = /studio_session=([^;]+)/.exec(res2.headers()["set-cookie"] ?? "")?.[1];
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
    headers: { ...ORIGIN, cookie: `studio_session=${token}` },
    data: { query, variables },
  });
  return res.json();
}

const CSV = "component,amount\nwater,5%\nsolvent,40\n";

async function seedImport(token: string): Promise<void> {
  const api = await request.newContext({ baseURL: API });
  const init = await api.post("/api/artifacts/uploads", {
    headers: { ...ORIGIN, cookie: `studio_session=${token}` },
    data: { original_name: `recipe-${Date.now()}.csv`, media_type: "text/csv" },
  });
  expect(init.ok()).toBeTruthy();
  const artifactId = (await init.json()).artifactId as string;
  const put = await api.put(`/api/artifacts/uploads/${artifactId}/content`, {
    headers: { ...ORIGIN, cookie: `studio_session=${token}` },
    data: CSV,
  });
  expect(put.ok()).toBeTruthy();
  const fin = await api.post(`/api/artifacts/uploads/${artifactId}/finish`, {
    headers: { ...ORIGIN, cookie: `studio_session=${token}` },
    data: {},
  });
  expect(fin.ok()).toBeTruthy();
  const r = await gql(
    token,
    `mutation ($a: String!) { imports { artifactImport(input: {artifactId: $a}) {
       batch { id status recordCount } deduplicated errors { code message } } } }`,
    { a: artifactId },
  );
  expect(r.data.imports.artifactImport.errors).toEqual([]);
  expect(r.data.imports.artifactImport.batch.status).toBe("parsed");
}

/** AT-0302-1 — ambiguous extraction stays visible and is never
 * accepted automatically. */
test("ambiguous imported fields show flags and stay proposed (AT-0302-1)", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  await seedImport(token);

  await page.goto("/imports");
  await page.getByRole("button", { name: /parsed · \d+ records/i }).click();

  // the '5%' cell carries the percent ambiguity flag and stays proposed
  const row = page.locator("tr", { hasText: "5%" });
  await expect(row).toContainText("percent literal");
  await expect(row).toContainText("proposed");
  await expect(row).not.toContainText("accepted");
  // numeric cell without unit context is flagged too
  const num = page.locator("tr", { hasText: "40" });
  await expect(num).toContainText("unit unresolved");
});

/** AT-0302-3 — selecting the citation shows the exact source locator. */
test("promoted claim shows the exact source locator (AT-0302-3)", async ({
  page,
  context,
}) => {
  const token = await signIn(context);
  await seedImport(token);

  await page.goto("/imports");
  await page.getByRole("button", { name: /parsed · \d+ records/i }).click();
  const row = page.locator("tr", { hasText: "5%" });
  await row.getByRole("button", { name: "promote to claim" }).click();
  await expect(page.getByText(/proposed claim created/)).toBeVisible();

  await page.goto("/evidence");
  const card = page.locator("article").first();
  await expect(card).toContainText("document claim");
  await expect(card).toContainText("proposed");
  // the citation renders the exact row/col locator from the import
  await expect(card).toContainText(/row \d+, col \d+/);
});
