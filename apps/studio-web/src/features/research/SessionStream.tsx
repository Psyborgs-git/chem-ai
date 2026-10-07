import { useEffect, useRef, useState } from "react";

import { Badge } from "../../components/atoms/Badge";
import { EmptyState } from "../../components/states/states";
import { fetchEventSnapshot } from "../../relay/network";
import {
  classifySnapshotError,
  openStream,
  retryDelayMs,
  streamClosed,
} from "./stream";

import type { StreamEvent } from "./stream";

type Msg = {
  id: string;
  role: string;
  kind: string;
  content: string;
  refs: Record<string, unknown>;
};

function parseJson(text: string): Record<string, unknown> | null {
  try {
    const v = JSON.parse(text) as unknown;
    return v && typeof v === "object" ? (v as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** One streamed message (§10.1/§8). Action state comes from the
 * tool_result row — never from assistant prose claiming success
 * (AT-0406-2). */
function MessageView({ msg }: { msg: Msg }) {
  if (msg.kind === "tool_call") {
    const call = parseJson(msg.content);
    const name = String(call?.tool ?? "tool");
    return (
      <li data-kind="tool_call" data-tool={name}>
        <Badge tone="info">action requested</Badge>{" "}
        <code>{name}</code>{" "}
        {call?.arguments != null && (
          <small>{JSON.stringify(call.arguments).slice(0, 200)}</small>
        )}
      </li>
    );
  }
  if (msg.kind === "tool_result") {
    const result = parseJson(msg.content);
    const ok = result?.ok === true;
    const tool = String(msg.refs?.tool ?? "tool");
    if (!ok) {
      const code = String((result?.error as Record<string, unknown>)?.code ?? "error");
      return (
        <li data-kind="tool_result" data-ok="false">
          <Badge tone="danger">action failed</Badge>{" "}
          <code>{tool}</code> <small>{code}</small>
        </li>
      );
    }
    return (
      <li data-kind="tool_result" data-ok="true">
        <Badge tone="success">action completed</Badge>{" "}
        <code>{tool}</code>
        {result?.untrusted === true && <Badge tone="warning">untrusted output</Badge>}
      </li>
    );
  }
  if (msg.kind === "proposal") {
    return (
      <li data-kind="proposal">
        <Badge tone="warning">proposal — needs human review</Badge>
        <p data-role={msg.role}>{msg.content}</p>
      </li>
    );
  }
  if (msg.kind === "rationale") {
    return (
      <li data-kind="rationale">
        <Badge tone="neutral">rationale</Badge>
        <p data-role={msg.role}>{msg.content}</p>
      </li>
    );
  }
  return (
    <li data-kind="message">
      <p data-role={msg.role}>
        {msg.role === "assistant" ? <Badge tone="info">assistant</Badge> : null}{" "}
        {msg.content}
      </p>
    </li>
  );
}

type StreamStatus =
  | "connecting"
  | "live"
  | "reconnecting"
  | "unavailable"
  | "unauthenticated"
  | "forbidden"
  | "not_found";

const STATUS_BADGE: Record<StreamStatus, { tone: "info" | "neutral" | "warning" | "danger"; label: string }> = {
  connecting: { tone: "neutral", label: "connecting…" },
  live: { tone: "info", label: "live" },
  reconnecting: { tone: "neutral", label: "reconnecting…" },
  unavailable: { tone: "warning", label: "snapshot unavailable — retrying" },
  unauthenticated: { tone: "warning", label: "sign-in required" },
  forbidden: { tone: "danger", label: "access revoked" },
  not_found: { tone: "neutral", label: "session not found" },
};

const TERMINAL_EMPTY: Partial<Record<StreamStatus, string>> = {
  unauthenticated: "sign in to view this session",
  forbidden: "access to this session was revoked",
  not_found: "this session no longer exists",
};

/** Streamed session view: authoritative snapshot first, then the
 * bounded SSE channel — events dedupe by messageId and reconnect
 * resumes at the last seq (AT-0406-1). Recovery is a reconcile loop
 * (PAR-08a): every (re)connect and every permanent socket close
 * refetches the snapshot — EventSource reports HTTP errors opaquely,
 * so the probe classifies 401/403/404 as terminal (sign-in required /
 * access revoked / not found, content cleared) and everything else as
 * transient with bounded backoff retry. */
export function SessionStream({ sessionId }: { sessionId: string }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const seen = useRef<Set<string>>(new Set());
  const lastSeq = useRef(0);

  useEffect(() => {
    let source: EventSource | null = null;
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    seen.current = new Set();
    lastSeq.current = 0;
    setMessages([]);
    setStatus("connecting");

    const append = (msg: Msg) => {
      if (seen.current.has(msg.id)) return;
      seen.current.add(msg.id);
      setMessages((prev) => [...prev, msg]);
    };

    const onEvent = (ev: StreamEvent) => {
      if (ev.seq > lastSeq.current) lastSeq.current = ev.seq;
      if (ev.type !== "session.message.posted") return;
      const p = ev.payload as Record<string, unknown>;
      append({
        id: String(p.messageId),
        role: String(p.role),
        kind: String(p.kind),
        content: String(p.content ?? ""),
        refs: (p.refs as Record<string, unknown>) ?? {},
      });
    };

    function closeSource() {
      source?.close();
      source = null;
    }

    function scheduleRetry() {
      if (cancelled || retryTimer != null) return;
      attempt += 1;
      retryTimer = setTimeout(() => {
        retryTimer = null;
        void reconcile();
      }, retryDelayMs(attempt));
    }

    async function reconcile() {
      try {
        const snap = await fetchEventSnapshot("session", sessionId);
        if (cancelled) return;
        attempt = 0;
        for (const m of snap.messages ?? []) append(m as Msg);
        if (snap.maxSeq > lastSeq.current) lastSeq.current = snap.maxSeq;
        // (re)open the socket only when none is live — a healthy stream
        // resumes from Last-Event-ID on its own and must not churn.
        if (source == null || streamClosed(source)) {
          closeSource();
          source = openStream("session", sessionId, lastSeq.current, {
            onEvent,
            onOpen: () => {
              if (cancelled) return;
              setStatus("live");
              // authoritative refetch on connect — covers a cursor the
              // browser dropped or a gap that opened while offline
              void reconcile();
            },
            onError: () => {
              if (cancelled) return;
              setStatus("reconnecting");
              // Network drops auto-retry inside EventSource; a non-2xx
              // (401/403/404) closes it for good — probe the snapshot
              // to classify terminal vs transient instead of guessing.
              if (source != null && streamClosed(source)) {
                closeSource();
                void reconcile();
              }
            },
          });
        }
      } catch (err) {
        if (cancelled) return;
        const kind = classifySnapshotError(err);
        if (kind === "transient") {
          setStatus("unavailable");
          scheduleRetry();
          return;
        }
        // terminal: revoked/expired/gone — stop retrying and clear the
        // rendered stream so stale content isn't shown as live state
        closeSource();
        seen.current = new Set();
        setMessages([]);
        setStatus(kind);
      }
    }

    void reconcile();

    return () => {
      cancelled = true;
      if (retryTimer != null) clearTimeout(retryTimer);
      closeSource();
    };
  }, [sessionId]);

  const badge = STATUS_BADGE[status];
  const terminalEmpty = TERMINAL_EMPTY[status];
  return (
    <section aria-label="session stream">
      <p>
        <Badge tone={badge.tone}>{badge.label}</Badge>
      </p>
      {terminalEmpty != null ? (
        <EmptyState title={terminalEmpty} />
      ) : messages.length === 0 ? (
        <EmptyState title="no messages yet" />
      ) : (
        <ul aria-label="session messages">
          {messages.map((m) => (
            <MessageView key={m.id} msg={m} />
          ))}
        </ul>
      )}
    </section>
  );
}
