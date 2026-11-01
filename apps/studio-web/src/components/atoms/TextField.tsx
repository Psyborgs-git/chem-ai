import { useId, type InputHTMLAttributes } from "react";

/** Labeled text field — label association and described-by wiring
 * are mandatory, not optional props. */
export function TextField({
  label,
  hint,
  error,
  id: providedId,
  className,
  "aria-describedby": existingDescription,
  "aria-invalid": existingInvalid,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  error?: string;
}) {
  const generatedId = useId();
  const id = providedId ?? generatedId;
  const hintId = `${id}-hint`;
  const errId = `${id}-error`;
  const describedBy = [existingDescription, hint ? hintId : null, error ? errId : null]
    .filter(Boolean)
    .join(" ");
  return (
    <div className="cs-field">
      <label htmlFor={id} className="cs-field__label">
        {label}
      </label>
      <input
        id={id}
        {...props}
        aria-invalid={error ? true : existingInvalid}
        aria-describedby={describedBy || undefined}
        className={`cs-input ${className ?? ""}`.trim()}
      />
      {hint && (
        <p id={hintId} className="cs-field__hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={errId} className="cs-field__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
