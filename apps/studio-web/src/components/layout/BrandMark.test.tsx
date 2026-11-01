import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BrandMark } from "./BrandMark";

describe("BrandMark", () => {
  it("names a standalone mark and keeps the decorative version out of the accessibility tree", () => {
    const { container } = render(<><BrandMark label="Chemistry Studio" /><BrandMark /></>);
    expect(screen.getByRole("img", { name: "Chemistry Studio" })).toBeVisible();
    expect(screen.getAllByRole("img")).toHaveLength(1);
    expect(container.querySelector("svg[aria-hidden='true']")).toHaveAttribute("focusable", "false");
  });

  it("keeps SVG paint references local when several marks share a page", () => {
    const { container } = render(<><BrandMark /><BrandMark /></>);
    const marks = [...container.querySelectorAll("svg")];
    const firstIds = [...marks[0].querySelectorAll("[id]")].map((node) => node.id);
    const secondIds = [...marks[1].querySelectorAll("[id]")].map((node) => node.id);
    expect(firstIds.some((id) => secondIds.includes(id))).toBe(false);
    for (const mark of marks) {
      for (const node of mark.querySelectorAll("[fill^='url('], [stroke^='url(']")) {
        const reference = node.getAttribute("fill")?.startsWith("url(") ? node.getAttribute("fill") : node.getAttribute("stroke");
        expect(mark.querySelector(`[id='${reference?.slice(5, -1)}']`)).not.toBeNull();
      }
    }
  });
});
