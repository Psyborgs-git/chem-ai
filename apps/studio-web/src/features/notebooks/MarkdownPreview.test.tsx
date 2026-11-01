import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { MarkdownPreview } from "./MarkdownPreview";
import { isStudioHelpLink } from "../help/links";

describe("private research Markdown", () => {
  it("keeps untrusted image destinations inert until a person opens the link", () => {
    render(<MarkdownPreview content={'![A source figure](https://collector.example/image?context=private)\n\n[Paper](https://example.org/paper)'} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View image: A source figure" })).toHaveAttribute("href", "https://collector.example/image?context=private");
    expect(screen.getByRole("link", { name: "Paper" })).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders formulae without enabling raw HTML or script URL execution", () => {
    const { container } = render(<MarkdownPreview content={'Formula: $c=n/V$.\n\n<script>alert(1)</script>\n\n[unsafe](javascript:alert(1))'} />);
    expect(container.querySelector(".katex")).toBeInTheDocument();
    expect(container.querySelector("script")).not.toBeInTheDocument();
    expect(screen.getByText("unsafe").getAttribute("href")).not.toContain("javascript:");
  });

  it("opens agent documentation links inside the studio and calls its panel close handler", () => {
    const opened = vi.fn();
    render(<MemoryRouter><Routes><Route path="/" element={<MarkdownPreview internalHelpLinks onOpenHelp={opened} content="[Start here](/help/usage/chemistry-basics#a-molecule-is-one-structure) and [Paper](https://example.org/paper)" />} /><Route path="/help/usage/chemistry-basics" element={<h1>Chemistry basics</h1>} /></Routes></MemoryRouter>);
    const help = screen.getByRole("link", { name: "Start here" });
    expect(help).not.toHaveAttribute("target");
    expect(screen.getByRole("link", { name: "Paper" })).toHaveAttribute("target", "_blank");
    fireEvent.click(help);
    expect(screen.getByRole("heading", { name: "Chemistry basics" })).toBeVisible();
    expect(opened).toHaveBeenCalledOnce();
  });

  it("preserves notebook external-link behavior and rejects lookalike help paths", () => {
    render(<MarkdownPreview content="[Notebook link](/help/usage/chemistry-basics)" />);
    expect(screen.getByRole("link", { name: "Notebook link" })).toHaveAttribute("target", "_blank");
    for (const href of ["//collector.example/help/usage/chemistry-basics", "https://collector.example/help/usage/chemistry-basics", "/help/../api/auth/logout", "/help/usage/%2e%2e/private", "/help/usage/chemistry-basics?token=private", "javascript:alert(1)"]) expect(isStudioHelpLink(href)).toBe(false);
    expect(isStudioHelpLink("/help/usage/chemistry-basics#a-molecule-is-one-structure")).toBe(true);
  });
});
