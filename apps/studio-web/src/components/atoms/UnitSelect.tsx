import { useId } from "react";

/** Unit picker — options arrive with their dimension context from
 * domain services; the control is presentation only (§22.3). */
export function UnitSelect({
  label,
  units,
  value,
  onValueChange,
  disabled,
}: {
  label: string;
  units: readonly string[];
  value: string;
  onValueChange?: (unit: string) => void;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="cs-field cs-field--unit">
      <label htmlFor={id} className="cs-field__label">
        {label}
      </label>
      <select
        id={id}
        className="cs-select"
        value={value}
        disabled={disabled}
        onChange={(e) => onValueChange?.(e.target.value)}
      >
        {units.map((u) => (
          <option key={u} value={u}>
            {u}
          </option>
        ))}
      </select>
    </div>
  );
}
