import { createRef, useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./select";

function Choice({ container }: { container?: HTMLElement }) {
  const [value, setValue] = useState("first");
  return <Select value={value} onValueChange={setValue}>
    <SelectTrigger aria-label="Example choice"><SelectValue /></SelectTrigger>
    <SelectContent container={container}>
      <SelectItem value="first">First choice</SelectItem>
      <SelectItem value="second">Second choice</SelectItem>
    </SelectContent>
  </Select>;
}

describe("Select portal ownership", () => {
  it("keeps an ordinary select in the body portal and preserves pointer selection", async () => {
    render(<Choice />);
    const trigger = screen.getByRole("combobox", { name: "Example choice" });
    await userEvent.click(trigger);
    const list = await screen.findByRole("listbox");
    expect(list.closest("dialog")).toBeNull();
    await userEvent.click(within(list).getByRole("option", { name: "Second choice" }));
    expect(trigger).toHaveTextContent("Second choice");
    expect(trigger).toHaveFocus();
  });

  it("portals inside the trigger's native dialog so its options stay in that modal", async () => {
    render(<dialog open aria-label="Native sheet"><Choice /></dialog>);
    const dialog = screen.getByRole("dialog", { name: "Native sheet" });
    const trigger = within(dialog).getByRole("combobox", { name: "Example choice" });
    await userEvent.click(trigger);
    const list = await within(dialog).findByRole("listbox");
    expect(list.closest("dialog")).toBe(dialog);
    await userEvent.click(within(list).getByRole("option", { name: "Second choice" }));
    expect(trigger).toHaveTextContent("Second choice");
    expect(trigger).toHaveFocus();
  });

  it("uses the nearest native dialog rather than an outer modal", async () => {
    render(<dialog open aria-label="Outer"><dialog open aria-label="Inner"><Choice /></dialog></dialog>);
    const inner = screen.getByRole("dialog", { name: "Inner" });
    await userEvent.click(within(inner).getByRole("combobox"));
    expect((await within(inner).findByRole("listbox")).closest("dialog")).toBe(inner);
  });

  it("keeps keyboard selection, Escape, and return focus inside the native dialog", async () => {
    const user = userEvent.setup();
    render(<dialog open aria-label="Keyboard sheet"><Choice /></dialog>);
    const dialog = screen.getByRole("dialog", { name: "Keyboard sheet" });
    const trigger = within(dialog).getByRole("combobox");
    trigger.focus();
    await user.keyboard("{ArrowDown}");
    await within(dialog).findByRole("listbox");
    await user.keyboard("{End}{Enter}");
    expect(trigger).toHaveTextContent("Second choice");
    expect(trigger).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    await within(dialog).findByRole("listbox");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(dialog).toHaveAttribute("open");
    expect(trigger).toHaveFocus();
  });

  it("supports an explicit portal container without losing the trigger ref", async () => {
    const target = document.createElement("div");
    target.setAttribute("data-testid", "explicit-portal");
    document.body.appendChild(target);
    const ref = createRef<HTMLButtonElement>();
    try {
      render(<Select defaultValue="first">
        <SelectTrigger ref={ref} aria-label="Ref choice"><SelectValue /></SelectTrigger>
        <SelectContent container={target}><SelectItem value="first">First choice</SelectItem></SelectContent>
      </Select>);
      const trigger = screen.getByRole("combobox", { name: "Ref choice" });
      expect(ref.current).toBe(trigger);
      await userEvent.click(trigger);
      expect(await within(target).findByRole("listbox")).toBeVisible();
      expect(ref.current).toBe(trigger);
    } finally {
      target.remove();
    }
  });
});
