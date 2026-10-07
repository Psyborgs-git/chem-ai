/**
 * PAR-05 — provenance summary helpers.
 *
 * The backend packet/snapshot manifest carries a `provenance` block
 * derived from the stored record fields:
 *
 *   provenance: {
 *     evidenceOrigin: { composition, counts, classesPresent, records[] },
 *     methodValidation: { status },
 *     independentValidation: { status },
 *     readiness: [...],
 *     missingScientificInputs: [...],
 *   }
 *
 * The UI reads it honestly: evidence origin, method validation and
 * independent validation are three separate axes — a real provenance
 * never upgrades scientific validation.
 */

export type ProvenanceBlock = {
  evidenceOrigin?: {
    composition?: string;
    counts?: Record<string, number>;
    classesPresent?: string[];
    records?: {
      id?: string;
      origin?: string;
      originVia?: string;
      reviewState?: string;
      engineApplicable?: boolean;
    }[];
  };
  methodValidation?: { status?: string };
  independentValidation?: { status?: string };
  readiness?: { axis?: string; status?: string }[];
  missingScientificInputs?: unknown[];
};

export const ORIGIN_LABEL: Record<string, string> = {
  synthetic_fixture: "fixture",
  historical_report: "historical report",
  lab_observation: "lab observation",
  prediction: "prediction",
  unknown: "unknown origin",
};

export function originLabel(origin: string | null | undefined): string {
  if (origin == null || origin === "") return "unknown origin";
  return ORIGIN_LABEL[origin] ?? String(origin).replace(/_/g, " ");
}

/** Per-class counts as readable text, e.g. "1 historical report, 2 fixtures". */
export function originCountsText(prov: ProvenanceBlock | null | undefined): string {
  const counts = prov?.evidenceOrigin?.counts ?? {};
  return Object.entries(counts)
    .map(([origin, n]) => `${n} ${originLabel(origin)}${n === 1 ? "" : "s"}`)
    .join(", ");
}

export type ProvenanceSummary = {
  tone: "info" | "warning" | "success" | "neutral" | "danger";
  text: string;
};

/**
 * One-line provenance badge text, keyed off the packet's derived
 * composition. The all-synthetic case keeps the literal "fixture-only"
 * phrasing the old constant badge used; every other composition names
 * the actual classes present and the validation axes still missing.
 */
export function provenanceSummary(
  prov: ProvenanceBlock | null | undefined,
  fixtureOnly: boolean,
): ProvenanceSummary {
  const composition = prov?.evidenceOrigin?.composition;
  if (composition == null) {
    // pre-PAR-05 packet or no bound evidence — the old honest badge.
    return fixtureOnly
      ? { tone: "info", text: "fixture-only — not scientific validation" }
      : {
          tone: "neutral",
          text: "provenance not established — not scientific validation",
        };
  }
  if (composition === "none" || composition === "synthetic_only") {
    return {
      tone: "info",
      text: "evidence: fixture-only (synthetic) — not scientific validation",
    };
  }
  if (composition === "real_only") {
    return {
      tone: "success",
      text: `evidence: real provenance (${originCountsText(prov)}) — method validation: missing; independent validation: missing`,
    };
  }
  if (composition === "mixed") {
    return {
      tone: "warning",
      text: `evidence: mixed (${originCountsText(prov)}) — not scientific validation`,
    };
  }
  // unknown_only
  return {
    tone: "neutral",
    text: "evidence: origin unknown — not scientific validation",
  };
}
