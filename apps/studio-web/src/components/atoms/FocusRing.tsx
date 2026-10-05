import type { ReactNode } from "react";

/** Visible, token-driven focus indicator — applied to every
 * interactive control so keyboard focus is never color-only or
 * invisible (§22.5). */
export function FocusRing({ children }: { children: ReactNode }) {
  return <span className="cs-focus-ring">{children}</span>;
}
