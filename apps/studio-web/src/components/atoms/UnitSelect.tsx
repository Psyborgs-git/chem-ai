import { useId } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
const EMPTY_UNIT = "__studio_empty_unit__";

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
      <Select value={value || (units.includes("") ? EMPTY_UNIT : "")} disabled={disabled} onValueChange={(unit) => onValueChange?.(unit === EMPTY_UNIT ? "" : unit)}>
        <SelectTrigger id={id} className="w-full"><SelectValue placeholder="Choose a unit" /></SelectTrigger>
        <SelectContent>
        {units.map((u) => (
          <SelectItem key={u} value={u || EMPTY_UNIT}>
            {u || "Not specified"}
          </SelectItem>
        ))}
        </SelectContent>
      </Select>
    </div>
  );
}
