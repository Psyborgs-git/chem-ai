/** Workflow status indicator — the *completion* axis. Distinct
 * component + distinct token family from EvidenceTypeLabel so the
 * two axes can never be conflated (§22.3). */

const STATUSES = {
  draft: "draft",
  active: "active",
  paused: "paused",
  awaiting_review: "awaiting review",
  closed: "closed",
  cancelled: "cancelled",
  running: "running",
  queued: "queued",
  failed: "failed",
  completed: "completed",
  unknown: "unknown",
} as const;

export type WorkflowStatus = keyof typeof STATUSES;

export function StatusIndicator({
  status,
}: {
  status: WorkflowStatus;
}) {
  return (
    <span
      className={`cs-status cs-status--${status}`}
      data-status={status}
      role="status"
    >
      {STATUSES[status]}
    </span>
  );
}
