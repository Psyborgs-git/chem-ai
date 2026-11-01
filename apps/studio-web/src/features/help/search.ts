import type { HelpArticle } from "./types";

export function searchHelp(articles: HelpArticle[], query: string, section = "") {
  const terms = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  return articles.flatMap((article) => {
    if (section && article.section !== section) return [];
    const title = article.title.toLocaleLowerCase(), summary = article.summary.toLocaleLowerCase();
    const text = article.searchText.toLocaleLowerCase();
    if (!terms.every((term) => `${title} ${summary} ${text}`.includes(term))) return [];
    const score = terms.reduce((total, term) => total + (title.includes(term) ? 10 : summary.includes(term) ? 4 : 1), 0);
    const first = terms.length ? Math.max(0, text.indexOf(terms.find((term) => text.includes(term)) ?? "")) : 0;
    const start = Math.max(0, first - 70);
    const snippet = terms.length ? `${start ? "…" : ""}${article.searchText.slice(start, start + 220).replace(/\s+/g, " ")}${text.length > start + 220 ? "…" : ""}` : article.summary;
    return [{ article, score, snippet }];
  }).sort((a, b) => b.score - a.score);
}
