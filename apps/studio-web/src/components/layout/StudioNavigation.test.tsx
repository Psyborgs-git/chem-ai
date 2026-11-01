import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceNavigation } from "./StudioLayout";

describe("focused workspace navigation", () => {
  it("starts with five essential destinations and reveals every secondary route on request", async () => {
    const onNavigate = vi.fn();
    render(<MemoryRouter><WorkspaceNavigation pathname="/" onNavigate={onNavigate} /></MemoryRouter>);
    expect(screen.getAllByRole("link")).toHaveLength(5);
    for (const name of ["Home", "Projects", "Notebooks", "Research library", "Local learning"]) expect(screen.getByRole("link", { name })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Downloads" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "More" }));
    expect(screen.getAllByRole("link")).toHaveLength(15);
    expect(screen.getByRole("link", { name: "Help & documentation" })).toHaveAttribute("href", "/help");
    await userEvent.click(screen.getByRole("link", { name: "Providers" }));
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });
  it("reveals and highlights a directly opened secondary destination", async () => {
    const view = render(<MemoryRouter><WorkspaceNavigation pathname="/compute/fallback/run-one" onNavigate={() => {}} /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "More" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Compute" })).toHaveAttribute("aria-current", "page");
    await userEvent.click(screen.getByRole("button", { name: "More" }));
    view.rerender(<MemoryRouter><WorkspaceNavigation pathname="/settings/providers" onNavigate={() => {}} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Providers" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Providers" })).toHaveAttribute("aria-current", "page");
  });
  it("keeps project navigation current while a research task is open", () => {
    render(<MemoryRouter><WorkspaceNavigation pathname="/tasks/task-one/decisions" onNavigate={() => {}} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Projects" })).toHaveAttribute("aria-current", "page");
  });
});
