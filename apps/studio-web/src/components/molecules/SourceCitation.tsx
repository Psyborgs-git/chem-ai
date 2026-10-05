/** Provenance citation — source kind is labeled text, never an
 * icon-only affordance. */
export function SourceCitation({
  sourceId,
  title,
  kind,
  locator,
}: {
  sourceId: string;
  title: string;
  kind: "upload" | "import" | "instrument" | "note" | "reference";
  locator?: string;
}) {
  return (
    <cite className="cs-citation" data-source-id={sourceId}>
      <span className="cs-citation__kind">{kind}</span> {title}
      {locator && <span className="cs-citation__loc"> · {locator}</span>}
    </cite>
  );
}
