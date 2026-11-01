import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownPreview } from "./MarkdownPreview";

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
});
