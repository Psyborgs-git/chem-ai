import { useCallback, useEffect, useState } from "react";

export type SaveState =
  | "unsaved"
  | "saving"
  | "saved"
  | "conflict"
  | "read_only_revision";

/** Honest save-state machine (§22.4): 'unsaved' stays until the
 * mutation confirms a durable write — a failed request returns to
 * 'unsaved' with the error surfaced, never a false 'saved'. */
export function useSaveState() {
  const [state, setState] = useState<SaveState>("unsaved");
  const [lastError, setLastError] = useState<string | null>(null);

  const markDirty = useCallback(() => {
    setState("unsaved");
    setLastError(null);
  }, []);

  const attemptSave = useCallback(async (fn: () => Promise<boolean>) => {
    setState("saving");
    setLastError(null);
    try {
      const ok = await fn();
      setState(ok ? "saved" : "unsaved");
      if (!ok) setLastError("the server reported an error — changes not saved");
      return ok;
    } catch (e) {
      setState("unsaved");
      setLastError(
        `save failed — API unreachable or rejected; not persisted (${
          e instanceof Error ? e.message : "unknown error"
        })`,
      );
      return false;
    }
  }, []);

  // warn before navigation while dirty (§22.4)
  useEffect(() => {
    if (state !== "unsaved") return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [state]);

  return { state, lastError, markDirty, attemptSave };
}
