import { useCallback, useEffect, useRef, useState } from "react";
import { workspaceRequest } from "../../relay/network";

export function useWorkspace<T>(path: string | null, pollMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const sequence = useRef(0);
  const currentPath = useRef(path);
  currentPath.current = path;
  const refresh = useCallback(async () => {
    if (path !== currentPath.current) return;
    if (!path) { setLoading(false); return; }
    const request = ++sequence.current;
    try {
      const value = await workspaceRequest<T>(path);
      if (request !== sequence.current || path !== currentPath.current) return;
      setData(value); setError(null); setErrorStatus(null);
    } catch (e) {
      if (request === sequence.current && path === currentPath.current) { setError(e instanceof Error ? e.message : "Unable to load your work"); const status = (e as { status?: unknown } | null)?.status; setErrorStatus(typeof status === "number" ? status : null); }
    } finally { if (request === sequence.current && path === currentPath.current) setLoading(false); }
  }, [path]);
  useEffect(() => {
    setData(null); setError(null); setErrorStatus(null); setLoading(true); void refresh();
    const timer = pollMs ? window.setInterval(() => { if (!document.hidden) void refresh(); }, pollMs) : undefined;
    return () => { sequence.current++; if (timer) window.clearInterval(timer); };
  }, [refresh, pollMs]);
  useEffect(() => {
    if (!path || path.startsWith("/api/agent-workspace")) return;
    const update = () => { void refresh(); };
    window.addEventListener("studio-workspace-updated", update);
    return () => window.removeEventListener("studio-workspace-updated", update);
  }, [path, refresh]);
  return { data, error, errorStatus, loading, refresh, setData };
}

export const post = <T,>(path: string, body: unknown = {}) => workspaceRequest<T>(path, { method: "POST", body: JSON.stringify(body) });
export const patch = <T,>(path: string, body: unknown) => workspaceRequest<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const messageOf = (error: unknown) => error instanceof Error ? error.message : "The request could not be completed";
