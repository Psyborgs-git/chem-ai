/** Bounded event stream client (§8): seq-id SSE with resume.
 *
 * EventSource auto-reconnects and sends `Last-Event-ID`; the server
 * resumes after that seq, so a disconnect can never replay a message
 * already delivered. On `open` the client refetches the authoritative
 * snapshot — covering any gap if the browser dropped the cursor. */

export type StreamEvent = {
  seq: number;
  type: string;
  aggregate: string;
  payload: Record<string, unknown>;
  at: string;
};

import { rawUuid } from "../../relay/network";

export function openStream(
  channel: "session" | "task",
  aggregateId: string,
  since: number,
  handlers: {
    onEvent: (ev: StreamEvent) => void;
    onOpen?: () => void;
    onError?: () => void;
  },
): EventSource {
  const params = new URLSearchParams({
    channel,
    id: rawUuid(aggregateId),
    since: String(since),
  });
  const source = new EventSource(`/api/events/stream?${params.toString()}`);
  // liveness watchdog: the server emits a named `heartbeat` frame every
  // poll interval — an established SSE can sit half-open (offline,
  // proxy drop) without ever firing `error`, so staleness is the real
  // disconnect signal, not just the native event
  let lastFrameAt = Date.now();
  const STALE_MS = 2500;
  const watchdog = setInterval(() => {
    if (Date.now() - lastFrameAt > STALE_MS) handlers.onError?.();
  }, 1000);
  const nativeClose = source.close.bind(source);
  source.close = () => {
    clearInterval(watchdog);
    nativeClose();
  };
  const alive = () => {
    lastFrameAt = Date.now();
  };
  source.onopen = () => {
    alive();
    handlers.onOpen?.();
  };
  source.onerror = () => handlers.onError?.();
  source.addEventListener("heartbeat", alive);
  // server sends `event: <type>` — listen broadly via onmessage is not
  // enough for named events; register the known channel families.
  for (const type of [
    "session.message.posted",
    "run.status.changed",
    "run.attempt.enqueued",
    "run.cancel.requested",
    "run.blocked",
  ]) {
    source.addEventListener(type, (m) => {
      alive();
      try {
        handlers.onEvent(JSON.parse((m as MessageEvent).data) as StreamEvent);
      } catch {
        // malformed frame — the snapshot-on-open path covers state
      }
    });
  }
  return source;
}
