import { useId, useState, type InputHTMLAttributes } from "react";

/** Decimal input — scientific values are decimal *strings* (§6.1);
 * this control keeps the text authoritative, never coerces to float.
 * Heavy validation stays in domain services; the field only mirrors
 * format-level feedback (§22.3). */
const DECIMAL_RE = /^-?\d*(\.\d*)?$/;

export function DecimalField({
  label,
  hint,
  error,
  onValueChange,
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> & {
  label: string;
  hint?: string;
  error?: string;
  value?: string;
  onValueChange?: (value: string) => void;
}) {
  const id = useId();
  const [formatError, setFormatError] = useState<string | null>(null);
  const errId = `${id}-error`;
  const hintId = `${id}-hint`;
  const message = error ?? formatError;
  const describedBy = [hint ? hintId : null, message ? errId : null]
    .filter(Boolean)
    .join(" ");
  return (
    <div className="cs-field">
      <label htmlFor={id} className="cs-field__label">
        {label}
      </label>
      <input
        id={id}
        inputMode="decimal"
        autoComplete="off"
        spellCheck={false}
        {...props}
        aria-invalid={message ? true : undefined}
        aria-describedby={describedBy || undefined}
        className="cs-input cs-input--decimal"
        onChange={(e) => {
          const v = e.target.value;
          if (v !== "" && !DECIMAL_RE.test(v)) {
            setFormatError("Enter a decimal number.");
            return;
          }
          setFormatError(null);
          onValueChange?.(v);
        }}
      />
      {hint && (
        <p id={hintId} className="cs-field__hint">
          {hint}
        </p>
      )}
      {message && (
        <p id={errId} className="cs-field__error" role="alert">
          {message}
        </p>
      )}
    </div>
  );
}
