import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { IconButton } from "./IconButton";

it("names the icon action and preserves its non-submitting form behavior", () => {
  const submit = vi.fn((event: React.FormEvent) => event.preventDefault());
  const remove = vi.fn();
  render(<form onSubmit={submit}><IconButton label="Remove constraint" onClick={remove}>×</IconButton></form>);
  fireEvent.click(screen.getByRole("button", { name: "Remove constraint" }));
  expect(remove).toHaveBeenCalledOnce();
  expect(submit).not.toHaveBeenCalled();
});
