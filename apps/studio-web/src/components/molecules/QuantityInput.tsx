import { useId } from "react";

import { DecimalField } from "../atoms/DecimalField";
import { UnitSelect } from "../atoms/UnitSelect";

/** Value + unit + basis editing (§22.3: "quantity controls show
 * unit/basis alongside the value"). Validation mirrors domain
 * feedback passed in via `error`; the domain owns the rules. */
export function QuantityInput({
  label,
  value,
  unit,
  units,
  basis,
  error,
  disabled,
  onValueChange,
  onUnitChange,
}: {
  label: string;
  value: string;
  unit: string;
  units: readonly string[];
  /** Shown alongside value+unit; required for fraction/concentration
   * dimensions (§6.1) but displayed whenever present. */
  basis?: string;
  error?: string;
  disabled?: boolean;
  onValueChange?: (v: string) => void;
  onUnitChange?: (u: string) => void;
}) {
  const groupId = useId();
  return (
    <fieldset
      className="cs-quantity"
      aria-labelledby={`${groupId}-legend`}
      aria-describedby={basis ? `${groupId}-basis` : undefined}
    >
      <legend id={`${groupId}-legend`} className="cs-field__label">
        {label}
      </legend>
      <div className="cs-quantity__row">
        <DecimalField
          label="value"
          value={value}
          error={error}
          disabled={disabled}
          onValueChange={onValueChange}
        />
        <UnitSelect
          label="unit"
          units={units}
          value={unit}
          disabled={disabled}
          onValueChange={onUnitChange}
        />
      </div>
      {basis && (
        <p id={`${groupId}-basis`} className="cs-quantity__basis">
          basis: {basis}
        </p>
      )}
    </fieldset>
  );
}
