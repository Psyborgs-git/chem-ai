import { useEffect, useId, useRef, type ReactNode } from "react";

export function CreateSheet({ open, onClose, title, description, children }: {
  open: boolean; onClose: () => void; title: string; description?: string; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (open && dialog && !dialog.open) {
      dialog.showModal();
      requestAnimationFrame(() => dialog.querySelector<HTMLElement>('input:not([type="radio"]):not([type="checkbox"]),textarea')?.focus());
    } else if (!open && dialog?.open) dialog.close();
  }, [open]);
  return <dialog ref={ref} className="cs-create-sheet" aria-labelledby={titleId}
    onCancel={(event) => { event.preventDefault(); onClose(); }} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="cs-create-sheet__header"><div><p className="cs-kicker">Chemistry Studio</p><h2 id={titleId}>{title}</h2>{description && <p>{description}</p>}</div><button type="button" className="cs-icon-btn" aria-label="Close" onClick={onClose}>×</button></div>
    <div className="cs-create-sheet__body">{open ? children : null}</div>
  </dialog>;
}
