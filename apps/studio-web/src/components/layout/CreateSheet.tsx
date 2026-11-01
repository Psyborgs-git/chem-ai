import { useEffect, useId, useRef, type MouseEvent, type PointerEvent, type ReactNode } from "react";

function isBackdrop(event: MouseEvent<HTMLDialogElement> | PointerEvent<HTMLDialogElement>) {
  if (event.target !== event.currentTarget) return false;
  const bounds = event.currentTarget.getBoundingClientRect();
  return event.clientX < bounds.left || event.clientX >= bounds.right ||
    event.clientY < bounds.top || event.clientY >= bounds.bottom;
}

export function CreateSheet({ open, onClose, title, description, children }: {
  open: boolean; onClose: () => void; title: string; description?: string; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const backdropPress = useRef(false);
  const titleId = useId();
  useEffect(() => {
    backdropPress.current = false;
    const dialog = ref.current;
    if (open && dialog && !dialog.open) {
      dialog.showModal();
      requestAnimationFrame(() => dialog.querySelector<HTMLElement>('input:not([type="radio"]):not([type="checkbox"]),textarea')?.focus());
    } else if (!open && dialog?.open) dialog.close();
  }, [open]);
  return <dialog ref={ref} className="cs-create-sheet" aria-labelledby={titleId}
    onCancel={(event) => { event.preventDefault(); onClose(); }}
    onPointerDownCapture={(event) => { backdropPress.current = event.button === 0 && isBackdrop(event); }}
    onPointerCancel={() => { backdropPress.current = false; }}
    onClick={(event) => {
      // Opening a portaled select can move the pointer-up target from its
      // trigger to an option, making the browser retarget click to the dialog.
      // Dismiss only a press and release that both happened on the backdrop.
      const dismiss = backdropPress.current && isBackdrop(event);
      backdropPress.current = false;
      if (dismiss) onClose();
    }}>
    <div className="cs-create-sheet__header"><div><p className="cs-kicker">Chemistry Studio</p><h2 id={titleId}>{title}</h2>{description && <p>{description}</p>}</div><button type="button" className="cs-icon-btn" aria-label="Close" onClick={onClose}>×</button></div>
    <div className="cs-create-sheet__body">{open ? children : null}</div>
  </dialog>;
}
