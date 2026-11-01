import { test, expect } from "@playwright/test";
import { mkdirSync, writeFileSync, unlinkSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(__dirname, "../..");
const marker = "private-runtime-probe-must-never-reach-a-browser";
const probes = [".runtime/dev-server-privacy-probe.json", ".runtime/vault/dev-server-privacy-probe.txt"];

test.beforeAll(() => {
  mkdirSync(resolve(root, ".runtime/vault"), { recursive: true });
  for (const name of probes) writeFileSync(resolve(root, name), marker);
});
test.afterAll(() => {
  for (const name of probes) unlinkSync(resolve(root, name));
});

for (const name of probes) {
  test(`development server denies ${name} and transformed variants`, async ({ request }) => {
    for (const query of ["", "?raw", "?import"]) {
      const response = await request.get(`/@fs/${root}/${name}${query}`);
      const body = await response.text();
      // Vite may turn a non-code ?import into an inert URL module.
      // The referenced private file itself must remain denied.
      if (query === "?import" && response.status() === 200) {
        expect(response.headers()["content-type"]).toContain("javascript");
        expect(body).toContain("export default");
        expect(body).toContain("/@fs/");
      } else {
        expect(response.status()).toBe(403);
      }
      expect(body).not.toContain(marker);
      expect(body).not.toContain(Buffer.from(marker).toString("base64"));
    }
  });
}

test("application source still loads with private filesystem paths denied", async ({ request }) => {
  const response = await request.get("/src/main.tsx");
  expect(response.ok()).toBeTruthy();
  expect(await response.text()).toContain("createRoot");
});

test("bundled help includes only registered manuals and excludes private runtime probes", async ({ request }) => {
  const response = await request.get("/@id/__x00__virtual:studio-help");
  expect(response.ok()).toBeTruthy();
  const body = await response.text();
  expect(body).toContain("docs/usage/getting-started.md");
  expect(body).not.toContain(marker);
  expect(body).not.toContain(Buffer.from(marker).toString("base64"));
  expect(body).not.toContain("mulberry-silk-pilot-2026-11-01.md");
});
