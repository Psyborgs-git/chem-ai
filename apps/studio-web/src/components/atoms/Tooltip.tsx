import { useId, useState, type ReactNode } from "react";

/** Keyboard-reachable tooltip — opens on focus as well as hover;
 * content is linked via aria-describedby. */
export function Tooltip({
  content,
  children,
}: {
  content: string;
  children: ReactNode;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  return (
    <span
      className="cs-tooltip"
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <span aria-describedby={id}>{children}</span>
      <span role="tooltip" id={id} hidden={!open} className="cs-tooltip__pop">
        {content}
      </span>
    </span>
  );
}
