import { afterEach, test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { loadHelpContent, parseArticle } from "./help-content.mjs";

const temporary = [];
afterEach(() => { for (const root of temporary.splice(0)) rmSync(root, { recursive: true, force: true }); });
const entry = (slug = "start", section = "usage") => ({ section, slug, source: `docs/${section}/${slug}.md`, title: slug, summary: "A complete guide", order: 1 });
function fixture(entries = [entry()], markdown = "# Start\n\n## Saving\n\nA saved revision.") {
  const root = mkdtempSync(join(tmpdir(), "studio-help-"));
  temporary.push(root);
  for (const section of ["usage", "development", "operations", "reference"]) mkdirSync(join(root, "docs", section), { recursive: true });
  writeFileSync(join(root, "docs/help-manifest.json"), JSON.stringify({ version: 1, articles: entries }));
  for (const item of entries) if (item.source.startsWith(`docs/${item.section}/`) && !item.source.includes("..")) writeFileSync(join(root, item.source), markdown);
  return root;
}

test("bundles only registered articles and maps Markdown and heading links", () => {
  const root = fixture([entry(), entry("recovery", "operations")]);
  writeFileSync(join(root, "docs/usage/start.md"), "# Start\n\n[Recovery](../operations/recovery.md#saving) and [Saving](#saving).\n\n## Saving\n\n[Notebook](/notebooks?new=notebook) and [Reference](https://example.org/paper).");
  writeFileSync(join(root, "docs/usage/private-unregistered.md"), "# Never bundle this marker");
  const { articles } = loadHelpContent(root);
  assert.equal(articles.length, 2);
  assert.equal(articles[0].linkMap["../operations/recovery.md#saving"], "/help/operations/recovery#saving");
  assert.equal(articles[0].linkMap["#saving"], "/help/usage/start#saving");
  assert.equal(articles[0].linkMap["/notebooks?new=notebook"], "/notebooks?new=notebook");
  assert.ok(!JSON.stringify(articles).includes("Never bundle this marker"));
});

test("supports reference-style links, fenced examples, tables and duplicate heading IDs", () => {
  const parsed = parseArticle("# Start\n\n## Save\n\n## Save\n\n## Save-1\n\n[Other][guide]\n\n[guide]: next.md\n\n```sh\necho '<placeholder>'\n```\n\n| A | B |\n| - | - |\n| 1 | 2 |\n");
  assert.deepEqual(parsed.headings.map((heading) => heading.id), ["start", "save", "save-1", "save-1-1"]);
  assert.deepEqual(parsed.links, ["next.md"]);
  assert.equal(parsed.html.length, 0);
  assert.ok(parsed.searchText.includes("placeholder"));
});

test("rejects duplicate routes, sources, and section order values", () => {
  for (const second of [entry(), { ...entry("other"), source: entry().source }, entry("other")]) {
    assert.throws(() => loadHelpContent(fixture([entry(), second])), /Duplicate/);
  }
});

test("rejects traversal and sources outside registered manual roots", () => {
  for (const source of ["docs/usage/../../.runtime/secrets.md", "/tmp/secret.md", "docs/research/experiment.md", "docs/usage/..\\secret.md"]) {
    assert.throws(() => loadHelpContent(fixture([{ ...entry(), source }])), /Invalid documentation source/);
  }
});

test("rejects symlink escapes even when the manifest source looks valid", () => {
  const root = fixture(), outside = mkdtempSync(join(tmpdir(), "studio-help-outside-"));
  temporary.push(outside);
  writeFileSync(join(outside, "secret.md"), "# External secret");
  rmSync(join(root, "docs/usage/start.md"));
  symlinkSync(join(outside, "secret.md"), join(root, "docs/usage/start.md"));
  assert.throws(() => loadHelpContent(root), /escapes allowed/);
});

test("rejects manual-root symlinks into unregistered documentation", () => {
  const root = fixture();
  mkdirSync(join(root, "docs/research"));
  writeFileSync(join(root, "docs/research/start.md"), "# Research report");
  rmSync(join(root, "docs/usage"), { recursive: true });
  symlinkSync(join(root, "docs/research"), join(root, "docs/usage"));
  assert.throws(() => loadHelpContent(root), /escapes allowed/);
});

test("rejects broken files, anchors, reference links and unsupported URL schemes", () => {
  for (const markdown of ["# Start\n\n[Missing](absent.md)", "# Start\n\n[Missing](#no-such-heading)", "# Start\n\n[Reference][unknown]", "# Start\n\n[Unsafe](javascript:alert)", "# Start\n\n[Private](file:///tmp/secret)", "# Start\n\n[Unknown](/settings/not-a-route)", "# Start\n\n[Traversal](/notebooks/%2e%2e/.runtime/probe)"]) {
    assert.throws(() => loadHelpContent(fixture(undefined, markdown)), /Unregistered|Missing heading|Unresolved reference|Unsupported link|Unknown app route|Invalid app route/);
  }
});

test("rejects raw HTML, external images and credential-bearing links", () => {
  for (const markdown of ["# Start\n\n<script>alert('x')</script>", "# Start\n\n![Remote image](https://example.org/track)", "# Start\n\n[Private](https://owner:secret@example.org)"]) {
    assert.throws(() => loadHelpContent(fixture(undefined, markdown)), /Raw HTML|images require|Credentials/);
  }
});

test("rejects missing titles and invalid or empty metadata", () => {
  assert.throws(() => loadHelpContent(fixture(undefined, "A document without a heading")), /exactly one H1/);
  assert.throws(() => loadHelpContent(fixture([{ ...entry(), summary: "" }])), /Invalid metadata/);
  assert.throws(() => loadHelpContent(fixture(undefined, "")), /Empty article/);
});
