import type { ReactNode } from "react";

import { Button } from "../atoms/Button";

/** Shared screen states (§22.4). Every data screen renders exactly
 * one of these instead of ad-hoc blank/error text. Titles are
 * semantic text — never icon-only or color-only. */

export function LoadingState({ label }: { label: string }) {
  return (
    <div className="cs-state cs-state--loading" role="status" aria-live="polite">
      <span aria-hidden="true" className="cs-state__spinner" />
      {label}
    </div>
  );
}

export function EmptyState({
  title,
  action,
}: {
  title: string;
  action?: ReactNode;
}) {
  return (
    <div className="cs-state cs-state--empty">
      <p className="cs-state__title">{title}</p>
      {action}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  detail,
  onRetry,
}: {
  title?: string;
  detail?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="cs-state cs-state--error" role="alert">
      <p className="cs-state__title">{title}</p>
      {detail && <p>{detail}</p>}
      {onRetry && <Button onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function ForbiddenState() {
  return (
    <div className="cs-state cs-state--forbidden" role="alert">
      <p className="cs-state__title">Not permitted</p>
      <p>You don't have the capability required for this view.</p>
    </div>
  );
}

export function UnavailableCapabilityState({
  capability,
}: {
  capability: string;
}) {
  return (
    <div className="cs-state cs-state--unavailable" role="status">
      <p className="cs-state__title">Capability unavailable</p>
      <p>
        <strong>{capability}</strong> is not installed on this deployment.
        This is an honest limitation, not an error.
      </p>
    </div>
  );
}

/** Editable-screen save state (§22.4): 'unsaved' is honest — nothing
 * claims durable persistence it didn't get. 'conflict' is a
 * revision-conflict, not a generic error. */
export function SaveStatus({
  state,
}: {
  state:
    | "unsaved"
    | "saving"
    | "saved"
    | "conflict"
    | "read_only_revision";
}) {
  const text = {
    unsaved: "unsaved changes — not persisted",
    saving: "saving…",
    saved: "saved",
    conflict: "revision conflict — another revision won; reload required",
    read_only_revision: "read-only — accepted revisions are immutable",
  }[state];
  return (
    <span
      className={`cs-save cs-save--${state}`}
      data-save-state={state}
      role="status"
      aria-live="polite"
    >
      {text}
    </span>
  );
}
