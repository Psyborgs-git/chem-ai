import type { ButtonHTMLAttributes, ReactNode } from "react";

/** Icon-only button — requires an accessible label so the icon never
 * carries meaning alone. */
export function IconButton({
  label,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      {...props}
      className={`cs-icon-btn ${props.className ?? ""}`.trim()}
    >
      <span aria-hidden="true">{children}</span>
    </button>
  );
}
