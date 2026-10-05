import { QuantityInput } from "./QuantityInput";

/** One contract metric target — operator is explicit text, not a
 * symbol alone. */
export function MetricTargetEditor({
  metric,
  operator,
  value,
  unit,
  units,
  basis,
  error,
  onChange,
}: {
  metric: string;
  operator: "<=" | ">=" | "target" | "between";
  value: string;
  unit: string;
  units: readonly string[];
  basis?: string;
  error?: string;
  onChange?: (v: { value?: string; unit?: string }) => void;
}) {
  return (
    <div className="cs-metric-target">
      <span className="cs-metric-target__name">{metric}</span>
      <span className="cs-metric-target__op" aria-label={`operator ${operator}`}>
        {operator}
      </span>
      <QuantityInput
        label={`target for ${metric}`}
        value={value}
        unit={unit}
        units={units}
        basis={basis}
        error={error}
        onValueChange={(v) => onChange?.({ value: v })}
        onUnitChange={(u) => onChange?.({ unit: u })}
      />
    </div>
  );
}
