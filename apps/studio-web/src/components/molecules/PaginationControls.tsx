/** Shared pagination footer for pageInfo-driven lists (PAR-09): a
 * failed page load surfaces as an error with a real retry — never a
 * silent truncation and never a fabricated "all loaded" state. */
import { Button } from "../atoms/Button";

export function PaginationControls({
  hasNext,
  loading,
  error,
  onLoadNext,
}: {
  hasNext: boolean;
  loading: boolean;
  error: string | null;
  onLoadNext: () => void;
}) {
  if (!hasNext && !error) return null;
  return (
    <div className="cs-pagination">
      {hasNext && (
        <Button type="button" disabled={loading} onClick={onLoadNext}>
          {loading ? "loading…" : "load more"}
        </Button>
      )}
      {error && (
        <p role="alert" data-field="pagination-error">
          could not load the next page: {error}{" "}
          <Button type="button" onClick={onLoadNext}>
            retry
          </Button>
        </p>
      )}
    </div>
  );
}
