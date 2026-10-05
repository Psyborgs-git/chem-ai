import { useEffect, useRef, useState } from "react";

import { Badge } from "../../components/atoms/Badge";
import { EmptyState } from "../../components/states/states";
import { fetchEventSnapshot } from "../../relay/network";
import { openStream } from "./stream";

import type { ChannelSnapshot } from "../../relay/network";
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

/** Streamed session view: authoritative snapshot first, then the
 * bounded SSE channel — events dedupe by messageId and reconnect
 * resumes at the last seq (AT-0406-1). */
export function SessionStream({ sessionId }: { sessionId: string }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [live, setLive] = useState(false);
  const seen = useRef<Set<string>>(new Set());
  const lastSeq = useRef(0);

  useEffect(() => {
    let source: EventSource | null = null;
    let cancelled = false;
    seen.current = new Set();
    lastSeq.current = 0;
    setMessages([]);

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

    void fetchEventSnapshot("session", sessionId)
      .then((snap: ChannelSnapshot) => {
        if (cancelled) return;
        for (const m of snap.messages ?? []) append(m as Msg);
        lastSeq.current = snap.maxSeq;
        source = openStream("session", sessionId, snap.maxSeq, {
          onEvent,
          onOpen: () => setLive(true),
          onError: () => setLive(false),
        });
      })
      .catch(() => setLive(false));

    return () => {
      cancelled = true;
      source?.close();
    };
  }, [sessionId]);

  return (
    <section aria-label="session stream">
      <p>
        {live ? (
          <Badge tone="info">live</Badge>
        ) : (
          <Badge tone="neutral">reconnecting…</Badge>
        )}
      </p>
      {messages.length === 0 ? (
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
