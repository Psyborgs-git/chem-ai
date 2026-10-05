/** Budget summary — estimates are labeled as estimates, never
 * actuals (§23.3). */
export function ResourceBudget({
  label,
  estimated,
  actual,
  cap,
}: {
  label: string;
  estimated?: string;
  actual?: string;
  cap?: string;
}) {
  return (
    <div className="cs-budget">
      <span className="cs-budget__label">{label}</span>
      <span>
        estimate <strong>{estimated ?? "—"}</strong>
      </span>
      <span>
        actual <strong>{actual ?? "—"}</strong>
      </span>
      {cap && (
        <span>
          cap <strong>{cap}</strong>
        </span>
      )}
    </div>
  );
}
