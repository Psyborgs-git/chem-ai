import type { ReactNode } from "react";

/** Neutral completion/status badge — text content is required so
 * meaning never rides on color (§22.5). */
export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: "info" | "success" | "warning" | "danger" | "neutral";
  children: ReactNode;
}) {
  return (
    <span className={`cs-badge cs-badge--${tone}`} role="status">
      {children}
    </span>
  );
}
