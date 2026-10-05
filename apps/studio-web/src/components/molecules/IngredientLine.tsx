import { QuantityInput } from "./QuantityInput";

/** One ingredient row — identity text + quantity; duplicates are a
 * *finding* surfaced by the domain, never auto-summed (§6.2). */
export function IngredientLine({
  name,
  value,
  unit,
  units,
  basis,
  role,
  finding,
  onChange,
}: {
  name: string;
  value: string;
  unit: string;
  units: readonly string[];
  basis?: string;
  role?: string;
  /** domain-surfaced finding text (e.g. duplicate identity) */
  finding?: string;
  onChange?: (v: { value?: string; unit?: string }) => void;
}) {
  return (
    <div className="cs-ingredient" data-finding={finding ? "true" : undefined}>
      <span className="cs-ingredient__name">{name}</span>
      {role && <span className="cs-ingredient__role">{role}</span>}
      <QuantityInput
        label={`amount of ${name}`}
        value={value}
        unit={unit}
        units={units}
        basis={basis}
        onValueChange={(v) => onChange?.({ value: v })}
        onUnitChange={(u) => onChange?.({ unit: u })}
      />
      {finding && (
        <p className="cs-ingredient__finding" role="note">
          {finding}
        </p>
      )}
    </div>
  );
}
