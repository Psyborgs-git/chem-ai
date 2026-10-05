/** A domain validation finding rendered inline at its field/row —
 * severity is text + tone, not color alone. */
export function InlineFinding({
  severity,
  message,
}: {
  severity: "info" | "warning" | "error";
  message: string;
}) {
  return (
    <p
      className={`cs-finding cs-finding--${severity}`}
      role={severity === "error" ? "alert" : "note"}
      data-severity={severity}
    >
      <span className="cs-finding__sev">{severity}:</span> {message}
    </p>
  );
}
