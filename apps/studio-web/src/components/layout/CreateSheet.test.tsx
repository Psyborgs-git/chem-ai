import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CreateSheet } from "./CreateSheet";

const dialogMethods = ["showModal", "close"] as const;
const originals = dialogMethods.map((name) =>
  Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name));
beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true, writable: true,
    value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true, writable: true,
    value: function (this: HTMLDialogElement) { this.removeAttribute("open"); },
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  dialogMethods.forEach((name, index) => {
    const original = originals[index];
    if (original) Object.defineProperty(HTMLDialogElement.prototype, name, original);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name);
  });
});

function sheet() {
  const closed = vi.fn();
  function Harness() {
    const [open, setOpen] = useState(true);
    return <CreateSheet open={open} onClose={() => { closed(); setOpen(false); }} title="Create example">
      <button type="button">Open options</button>
    </CreateSheet>;
  }
  render(<Harness />);
  const dialog = screen.getByRole("dialog", { name: "Create example" });
  vi.spyOn(dialog, "getBoundingClientRect").mockReturnValue(
    DOMRect.fromRect({ x: 400, y: 0, width: 400, height: 800 }),
  );
  return { dialog, closed };
}

describe("CreateSheet backdrop dismissal", () => {
  it("does not close when opening options retargets a click from the trigger to the dialog", () => {
    const { dialog, closed } = sheet();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Open options" }), {
      button: 0, clientX: 600, clientY: 200,
    });
    fireEvent.click(dialog, { clientX: 600, clientY: 200 });
    expect(closed).not.toHaveBeenCalled();
    expect(dialog).toHaveAttribute("open");
  });

  it("closes for a genuine backdrop press and click", () => {
    const { dialog, closed } = sheet();
    fireEvent.pointerDown(dialog, { button: 0, clientX: 100, clientY: 200 });
    fireEvent.click(dialog, { clientX: 100, clientY: 200 });
    expect(closed).toHaveBeenCalledOnce();
    expect(dialog).not.toHaveAttribute("open");
  });

  it("keeps blank space inside the panel interactive without dismissing", () => {
    const { dialog, closed } = sheet();
    fireEvent.pointerDown(dialog, { button: 0, clientX: 600, clientY: 700 });
    fireEvent.click(dialog, { clientX: 600, clientY: 700 });
    expect(closed).not.toHaveBeenCalled();
  });

  it("does not dismiss a drag starting inside and ending outside", () => {
    const { dialog, closed } = sheet();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Open options" }), {
      button: 0, clientX: 600, clientY: 200,
    });
    fireEvent.click(dialog, { clientX: 100, clientY: 200 });
    expect(closed).not.toHaveBeenCalled();
  });

  it("does not dismiss a press starting outside and ending inside", () => {
    const { dialog, closed } = sheet();
    fireEvent.pointerDown(dialog, { button: 0, clientX: 100, clientY: 200 });
    fireEvent.click(dialog, { clientX: 600, clientY: 200 });
    expect(closed).not.toHaveBeenCalled();
  });

  it("forgets a cancelled backdrop press", () => {
    const { dialog, closed } = sheet();
    fireEvent.pointerDown(dialog, { button: 0, clientX: 100, clientY: 200 });
    fireEvent.pointerCancel(dialog);
    fireEvent.click(dialog, { clientX: 100, clientY: 200 });
    expect(closed).not.toHaveBeenCalled();
  });

  it("preserves the explicit close button", async () => {
    const { dialog, closed } = sheet();
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(closed).toHaveBeenCalledOnce();
    expect(dialog).not.toHaveAttribute("open");
  });
});
