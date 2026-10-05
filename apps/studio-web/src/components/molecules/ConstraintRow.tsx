import { IconButton } from "../atoms/IconButton";

/** One editable constraint line — remove control is labeled. */
export function ConstraintRow({
  description,
  severity,
  onRemove,
}: {
  description: string;
  severity?: "hard" | "soft";
  onRemove?: () => void;
}) {
  return (
    <div className="cs-constraint">
      <span className="cs-constraint__sev" data-severity={severity ?? "hard"}>
        {severity ?? "hard"} constraint
      </span>
      <span className="cs-constraint__desc">{description}</span>
      {onRemove && <IconButton label="remove constraint" onClick={onRemove}>×</IconButton>}
    </div>
  );
}
