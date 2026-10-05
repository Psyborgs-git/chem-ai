import { Badge } from "../atoms/Badge";

/** Approval-envelope summary — the four binding fields are explicit
 * text (§7.4), never implied. */
export function ApprovalSummary({
  scope,
  inputsFingerprint,
  expiresAt,
  state,
}: {
  scope: string;
  inputsFingerprint: string;
  expiresAt: string;
  state: "pending" | "approved" | "stale" | "expired" | "revoked";
}) {
  const tone =
    state === "approved"
      ? "success"
      : state === "pending"
        ? "info"
        : "warning";
  return (
    <div className="cs-approval">
      <Badge tone={tone}>{state}</Badge>
      <dl className="cs-approval__fields">
        <div>
          <dt>scope</dt>
          <dd>{scope}</dd>
        </div>
        <div>
          <dt>inputs fingerprint</dt>
          <dd className="cs-mono">{inputsFingerprint}</dd>
        </div>
        <div>
          <dt>expires</dt>
          <dd>{expiresAt}</dd>
        </div>
      </dl>
    </div>
  );
}
