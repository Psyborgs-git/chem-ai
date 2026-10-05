import { EvidenceTypeLabel, type EvidenceKind } from "../atoms/EvidenceTypeLabel";

/** Read-side quantity + uncertainty + conditions at the point of
 * display (§22.3: uncertainty and conditions shown where a result
 * is rendered, not hidden in a modal). A dash means *unknown* and
 * carries an accessible reason — never a silent zero. */
export function QuantityDisplay({
  value,
  unit,
  basis,
  uncertainty,
  conditions,
  evidence,
}: {
  /** decimal string; render "-" via `unknownReason` instead when the
   * value is unknown. */
  value?: string;
  unit?: string;
  basis?: string;
  uncertainty?: string;
  conditions?: string;
  evidence?: EvidenceKind;
  unknownReason?: string;
}) {
  return (
    <span className="cs-qdisplay">
      {evidence && <EvidenceTypeLabel kind={evidence} />}
      <span className="cs-qdisplay__value">
        {value !== undefined ? (
          <>
            {value}
            {unit && <span className="cs-qdisplay__unit"> {unit}</span>}
          </>
        ) : (
          <span
            className="cs-qdisplay__unknown"
            role="note"
            aria-label="value unknown"
          >
            —<span className="cs-qdisplay__unknown-reason"> (unknown)</span>
          </span>
        )}
      </span>
      {uncertainty && <span className="cs-qdisplay__ctx"> ± {uncertainty}</span>}
      {basis && <span className="cs-qdisplay__ctx"> · {basis}</span>}
      {conditions && <span className="cs-qdisplay__ctx"> · {conditions}</span>}
    </span>
  );
}
