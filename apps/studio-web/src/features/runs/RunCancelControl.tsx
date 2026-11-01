import { useRef, useState } from "react";
import { useMutation } from "react-relay";
import { Button } from "../../components/atoms/Button";
import { RunRequestCancelMutation } from "./operations";
import type { runsRequestCancelMutation } from "../../__generated__/runsRequestCancelMutation.graphql";
import type { RunView } from "./RunResult";

export function canRequestCancellation(status: string) {
  return ["requested", "awaiting_approval", "queued", "running"].includes(status);
}

/** An acknowledgement is a request to stop. The authoritative run
 * stays cancel_requested until the worker confirms a terminal state. */
export function RunCancelControl({ run, onChanged }: { run: RunView; onChanged?: () => void }) {
  const [commit, inFlight] = useMutation<runsRequestCancelMutation>(RunRequestCancelMutation);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pendingRef = useRef(false);
  if (run.status === "cancel_requested") {
    return <p role="status" className="cs-field__hint">Cancellation requested. Waiting for the worker to confirm that execution has stopped.</p>;
  }
  if (!canRequestCancellation(run.status)) return null;
  return (
    <div>
      <Button type="button" variant="danger" disabled={pending || inFlight} aria-label={`cancel ${run.kind} run`} onClick={() => {
        if (pendingRef.current || inFlight) return;
        pendingRef.current = true;
        setPending(true);
        setError(null);
        commit({
          variables: { input: { runId: run.id } },
          onCompleted: (response) => {
            pendingRef.current = false;
            setPending(false);
            const result = response.runs.requestCancel;
            if (result.errors.length) setError(result.errors.map((finding) => finding.message).join("; "));
            else onChanged?.();
          },
          onError: (failure) => {
            pendingRef.current = false;
            setPending(false);
            setError(failure.message);
          },
        });
      }}>{pending || inFlight ? "Requesting cancellation…" : "Cancel run"}</Button>
      {error && <p role="alert">Cancellation was not confirmed: {error}</p>}
    </div>
  );
}
