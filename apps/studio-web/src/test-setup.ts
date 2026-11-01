import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Browser primitives used by the shared Radix controls, absent in JSDOM.
if (!globalThis.PointerEvent) globalThis.PointerEvent = MouseEvent as typeof PointerEvent;
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
for (const [name, implementation] of Object.entries({
  hasPointerCapture: (): boolean => false,
  setPointerCapture: (): void => {},
  releasePointerCapture: (): void => {},
  scrollIntoView: (): void => {},
})) {
  if (!(name in Element.prototype)) {
    Object.defineProperty(Element.prototype, name, {
      value: implementation, configurable: true, writable: true,
    });
  }
}

afterEach(cleanup);
