/** Evidence-type label — the *provenance* axis (§22.3: evidence
 * badges must be distinct from completion badges). Each kind has a
 * text label and a distinct leading shape marker, so the meaning
 * survives without color and without icons alone. */

const KINDS = {
  measured: { label: "measured", marker: "●" },
  predicted: { label: "predicted", marker: "◐" },
  computed: { label: "computed", marker: "◆" },
  imported: { label: "imported", marker: "◈" },
  unknown: { label: "unknown", marker: "○" },
} as const;

export type EvidenceKind = keyof typeof KINDS;

export function EvidenceTypeLabel({ kind }: { kind: EvidenceKind }) {
  const k = KINDS[kind];
  return (
    <span
      className={`cs-evidence cs-evidence--${kind}`}
      data-evidence={kind}
      role="status"
    >
      <span aria-hidden="true" className="cs-evidence__marker">
        {k.marker}
      </span>
      {k.label}
    </span>
  );
}
