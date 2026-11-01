import { readFileSync, realpathSync } from "node:fs";
import { dirname, extname, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { toString } from "mdast-util-to-string";

export const repositoryRoot = fileURLToPath(new URL("../../../", import.meta.url));
const roots = ["docs/usage/", "docs/development/", "docs/operations/", "docs/reference/"];
const sections = ["usage", "development", "operations", "reference"];
const processor = unified().use(remarkParse).use(remarkGfm).use(remarkMath);

function walk(node, callback) {
  callback(node);
  for (const child of node.children ?? []) walk(child, callback);
}

// Shared by the content validator, article renderer and table of contents.
// Keep letters, numbers, underscores and hyphens; suffix repeated headings.
export function headingSlug(text) {
  return text.toLowerCase().replace(/[^\p{L}\p{N}_\s-]/gu, "").replace(/\s/g, "-") || "section";
}

export function parseArticle(markdown) {
  const tree = processor.parse(markdown);
  const headings = [], links = [], images = [], html = [];
  const definitions = new Map(), counts = new Map();
  walk(tree, (node) => {
    if (node.type === "definition") definitions.set(node.identifier.toLowerCase(), node.url);
  });
  walk(tree, (node) => {
    if (node.type === "heading") {
      const text = toString(node), base = headingSlug(text);
      const count = counts.get(base) ?? 0;
      let id = count ? `${base}-${count}` : base;
      // A literal heading ending in '-1' can collide with a generated suffix.
      let suffix = count;
      while (headings.some((heading) => heading.id === id)) id = `${base}-${++suffix}`;
      counts.set(base, suffix + 1);
      headings.push({ id, text, depth: node.depth, offset: node.position.start.offset });
    }
    if (node.type === "link" || node.type === "image") {
      (node.type === "link" ? links : images).push(node.url);
    }
    if (node.type === "linkReference" || node.type === "imageReference") {
      const url = definitions.get(node.identifier.toLowerCase());
      if (!url) throw new Error(`Unresolved reference: ${node.identifier}`);
      (node.type === "linkReference" ? links : images).push(url);
    }
    // CommonMark treats an unresolved full/collapsed reference as plain text.
    if (node.type === "text") {
      for (const match of node.value.matchAll(/\[([^\]]+)\]\[([^\]]*)\]/g)) {
        const identifier = (match[2] || match[1]).toLowerCase();
        if (!definitions.has(identifier)) throw new Error(`Unresolved reference: ${identifier}`);
      }
    }
    if (node.type === "html") html.push(node.value);
  });
  return { headings, links, images, html, searchText: tree.children.map((node) => toString(node)).join("\n") };
}

function contained(path, root) {
  const rel = relative(root, path);
  return rel !== ".." && !rel.startsWith(`..${sep}`) && !rel.startsWith(sep);
}

function decode(value) {
  try { return decodeURIComponent(value); } catch { throw new Error(`Invalid URL encoding: ${value}`); }
}

export function loadHelpContent(root = repositoryRoot) {
  const manifestPath = resolve(root, "docs/help-manifest.json");
  if (realpathSync(resolve(root, "docs")) !== resolve(realpathSync(root), "docs")) throw new Error("Documentation directory must not be a symlink");
  if (realpathSync(manifestPath) !== resolve(realpathSync(root), "docs/help-manifest.json")) throw new Error("Help manifest must not be a symlink");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  if (manifest.version !== 1 || !Array.isArray(manifest.articles) || !manifest.articles.length) {
    throw new Error("Help manifest must have version 1 and nonempty articles");
  }
  const ids = new Set(), sources = new Set(), orders = new Set(), dependencies = [manifestPath];
  const articles = manifest.articles.map((entry) => {
    const { section, slug, title, summary, source, order } = entry;
    const id = `${section}/${slug}`;
    if (!sections.includes(section) || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug ?? "")) throw new Error(`Invalid help route: ${id}`);
    if (typeof title !== "string" || !title.trim() || typeof summary !== "string" || !summary.trim() || !Number.isInteger(order) || order < 0) throw new Error(`Invalid metadata: ${id}`);
    if (typeof source !== "string" || !roots.some((prefix) => source.startsWith(prefix)) || extname(source) !== ".md" || source.includes("\\") || source.split("/").some((part) => part === ".." || part.startsWith("."))) throw new Error(`Invalid documentation source: ${source}`);
    if (ids.has(id) || sources.has(source) || orders.has(`${section}/${order}`)) throw new Error(`Duplicate help entry: ${id}`);
    ids.add(id); sources.add(source); orders.add(`${section}/${order}`);
    const full = resolve(root, source), real = realpathSync(full);
    const prefix = roots.find((value) => source.startsWith(value));
    const allowedRoot = realpathSync(resolve(root, prefix));
    if (allowedRoot !== resolve(realpathSync(root), prefix) || !contained(real, allowedRoot)) throw new Error(`Documentation escapes allowed directory: ${source}`);
    const markdown = readFileSync(real, "utf8");
    if (!markdown.trim()) throw new Error(`Empty article: ${source}`);
    const parsed = parseArticle(markdown);
    if (parsed.headings.filter((heading) => heading.depth === 1).length !== 1) throw new Error(`Article needs exactly one H1: ${source}`);
    if (parsed.html.length) throw new Error(`Raw HTML is not supported in help: ${source}`);
    // Manuals are text-first. Figures can be added later with explicit asset registration.
    if (parsed.images.length) throw new Error(`Help images require a registered local asset: ${source}`);
    dependencies.push(real);
    return { id, section, slug, title, summary, source, order, markdown, ...parsed };
  });
  const bySource = new Map(articles.map((article) => [article.source, article]));
  const byId = new Map(articles.map((article) => [article.id, article]));
  for (const article of articles) {
    article.linkMap = {};
    for (const href of article.links) {
      if (/^https?:\/\//i.test(href)) {
        const url = new URL(href);
        if (url.username || url.password) throw new Error(`Credentials in documentation link: ${article.source}`);
        article.linkMap[href] = href;
        continue;
      }
      if (/^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("//")) throw new Error(`Unsupported link in ${article.source}: ${href}`);
      const [pathAndQuery, fragment] = href.split("#");
      if (pathAndQuery?.startsWith("/") && (pathAndQuery.includes("\\") || /\/(?:\.\.?)(?:\/|$)/.test(decode(pathAndQuery.split("?")[0])))) throw new Error(`Invalid app route in ${article.source}: ${href}`);
      let target;
      if (!pathAndQuery) target = article;
      else if (pathAndQuery.startsWith("/help/")) target = byId.get(decode(pathAndQuery.slice(6)));
      else if (pathAndQuery === "/help") {
        article.linkMap[href] = href;
        continue;
      } else if (pathAndQuery.startsWith("/")) {
        // Explicit local application routes. Schemes and protocol-relative URLs were rejected above.
        const appRoute = /^\/(?:projects|tasks|runs|materials|imports|evidence|lab|models|learning|notebooks|library\/research|downloads|memory|compute|settings\/providers|privacy\/exports)(?:[/?#]|$)/;
        if (pathAndQuery !== "/" && !appRoute.test(pathAndQuery)) throw new Error(`Unknown app route in ${article.source}: ${href}`);
        article.linkMap[href] = href;
        continue;
      } else {
        if (pathAndQuery.includes("?")) throw new Error(`Use an app route, not an article query: ${article.source}: ${href}`);
        const targetSource = relative(root, resolve(root, dirname(article.source), decode(pathAndQuery))).split(sep).join("/");
        target = bySource.get(targetSource);
      }
      if (!target) throw new Error(`Unregistered article link in ${article.source}: ${href}`);
      if (fragment && !target.headings.some((heading) => heading.id === decode(fragment))) throw new Error(`Missing heading in ${article.source}: ${href}`);
      article.linkMap[href] = `/help/${target.id}${fragment ? `#${fragment}` : ""}`;
    }
    delete article.links;
    delete article.images;
    delete article.html;
  }
  articles.sort((a, b) => sections.indexOf(a.section) - sections.indexOf(b.section) || a.order - b.order);
  return { articles, dependencies };
}

export function helpContentPlugin() {
  const publicId = "virtual:studio-help", resolvedId = `\0${publicId}`;
  return {
    name: "studio-help-content",
    resolveId(id) { if (id === publicId) return resolvedId; },
    load(id) {
      if (id !== resolvedId) return;
      const content = loadHelpContent();
      for (const path of content.dependencies) this.addWatchFile(path);
      return `export const articles = ${JSON.stringify(content.articles)};`;
    },
    buildStart() { loadHelpContent(); },
    configureServer(server) {
      // Reload just the maintained documentation inputs, without exposing a filesystem endpoint.
      const relevant = (path) => path === resolve(repositoryRoot, "docs/help-manifest.json") || roots.some((prefix) => path.startsWith(resolve(repositoryRoot, prefix) + sep));
      server.watcher.add(loadHelpContent().dependencies);
      const changed = (path) => {
        if (!relevant(path)) return;
        const module = server.moduleGraph.getModuleById(resolvedId);
        if (module) server.moduleGraph.invalidateModule(module);
        server.ws.send({ type: "full-reload" });
      };
      server.watcher.on("change", changed);
      server.watcher.on("add", changed);
      server.watcher.on("unlink", changed);
    },
  };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const { articles } = loadHelpContent();
    console.log(`Help documentation valid: ${articles.length} articles, ${articles.reduce((sum, article) => sum + article.headings.length, 0)} headings.`);
  } catch (error) {
    console.error(`Help documentation: ${error.message}`);
    process.exitCode = 1;
  }
}
