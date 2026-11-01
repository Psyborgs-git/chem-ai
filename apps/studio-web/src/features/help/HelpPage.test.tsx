import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import { articles } from "virtual:studio-help";
import { HelpPage } from "./HelpPage";
import { HelpMarkdown } from "./HelpMarkdown";
import { searchHelp } from "./search";
import type { HelpArticle } from "./types";

function open(path = "/help") {
  return render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/help" element={<HelpPage />} /><Route path="/help/:section/:article" element={<HelpPage />} /><Route path="/help/*" element={<HelpPage />} /></Routes></MemoryRouter>);
}

describe("bundled studio help", () => {
  it("browses sections and searches the real maintained content locally", () => {
    open();
    expect(screen.getByRole("heading", { name: "Help & documentation" })).toBeVisible();
    fireEvent.click(screen.getByRole("link", { name: /Using the studio.*articles/ }));
    expect(screen.getByRole("heading", { name: "Using the studio" })).toBeVisible();
    fireEvent.change(screen.getByRole("searchbox", { name: "Search documentation" }), { target: { value: "notebook" } });
    expect(screen.getByRole("heading", { name: "Search results" })).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent(/articles? matching/);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "no-results-9a37b" } });
    expect(screen.getByText(/No matching articles/)).toBeVisible();
  });

  it("renders direct article links, title focus, contents and unknown routes", () => {
    const article = articles.find((item) => item.id === "usage/notebooks-and-editing")!;
    const view = open(`/help/${article.id}`);
    const heading = screen.getByRole("heading", { name: article.headings[0].text });
    expect(heading).toHaveFocus();
    expect(screen.getByLabelText("On this page")).toBeInTheDocument();
    view.unmount();
    open("/help/usage/unknown");
    expect(screen.getByRole("heading", { name: "Article not found" })).toBeVisible();
  });

  it("indexes operation names and configuration options as well as guide titles", () => {
    expect(searchHelp(articles, "STUDIO_VAULT_ROOT").some((hit) => hit.article.section === "reference")).toBe(true);
    expect(searchHelp(articles, "contractFreeze").some((hit) => hit.article.section === "reference")).toBe(true);
    expect(searchHelp(articles, "notebook", "usage").every((hit) => hit.article.section === "usage")).toBe(true);
  });

  it("renders heading anchors and safe internal/external links without raw HTML", () => {
    const markdown = "# Example\n\n## Save\n\n[Guide](next.md) and [External](https://example.org).\n\n<script>unsafe()</script>\n\n```sh\necho example\n```";
    const article: HelpArticle = { id: "usage/example", section: "usage", slug: "example", title: "Example", summary: "Example", source: "docs/usage/example.md", order: 0, markdown, searchText: "", headings: [{ id: "example", text: "Example", depth: 1, offset: 0 }, { id: "save", text: "Save", depth: 2, offset: 11 }], linkMap: { "next.md": "/help/usage/next", "https://example.org": "https://example.org" } };
    const { container } = render(<MemoryRouter><HelpMarkdown article={article} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Save" })).toHaveAttribute("id", "save");
    expect(screen.getByRole("link", { name: "Guide" })).toHaveAttribute("href", "/help/usage/next");
    expect(screen.getByRole("link", { name: /External/ })).toHaveAttribute("rel", "noopener noreferrer");
    expect(container.querySelector("script")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy code" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Code example" })).toHaveAttribute("tabindex", "0");
  });
});
