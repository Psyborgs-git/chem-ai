import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SessionStream } from "./SessionStream";
import {
  classifySnapshotError,
  openStream,
  retryDelayMs,
  streamClosed,
} from "./stream";
import { fetchEventSnapshot } from "../../relay/network";

vi.mock("../../relay/network", () => ({
  fetchEventSnapshot: vi.fn(),
  rawUuid: (id: string) => id,
}));

type Handlers = {
  onEvent: (ev: { seq: number; type: string; payload: Record<string, unknown> }) => void;
  onOpen?: () => void;
  onError?: () => void;
};

class FakeSource {
  handlers: Handlers;
  readyState = 0;
  closed = false;
  constructor(h: Handlers) {
    this.handlers = h;
    fakeSources.push(this);
  }
  addEventListener() {}
  close() {
    this.closed = true;
    this.readyState = 2;
  }
  open() {
    this.readyState = 1;
    this.handlers.onOpen?.();
  }
  error() {
    this.handlers.onError?.();
  }
  closePermanently() {
    this.readyState = 2;
    this.handlers.onError?.();
  }
  message(id: string, seq: number, content = `msg ${id}`) {
    this.handlers.onEvent({
      seq,
      type: "session.message.posted",
      payload: { messageId: id, role: "assistant", kind: "message", content, refs: {} },
    });
  }
}

const fakeSources: FakeSource[] = [];

vi.mock("./stream", async (importOriginal) => {
  const mod = await importOriginal<typeof import("./stream")>();
  return {
    ...mod,
    openStream: vi.fn(
      (_c: string, _id: string, _since: number, h: Handlers) =>
        new FakeSource(h) as unknown as EventSource,
    ),
  };
});

type SnapshotMsg = {
  id: string;
  role: string;
  kind: string;
  content: string;
  refs: Record<string, unknown>;
};

const snap = (messages: SnapshotMsg[] = [], maxSeq = 0) => ({
  maxSeq,
  channel: "session" as const,
  messages,
});

const msg = (id: string, content = `from snapshot ${id}`): SnapshotMsg => ({
  id,
  role: "user",
  kind: "message",
  content,
  refs: {},
});

beforeEach(() => {
  fakeSources.length = 0;
  vi.mocked(fetchEventSnapshot).mockReset();
  vi.mocked(openStream).mockClear();
});

describe("classifySnapshotError", () => {
  it("maps status codes to failure classes", () => {
    expect(classifySnapshotError(new Error("snapshot failed: 401"))).toBe("unauthenticated");
    expect(classifySnapshotError(new Error("snapshot failed: 403"))).toBe("forbidden");
    expect(classifySnapshotError(new Error("snapshot failed: 404"))).toBe("not_found");
    expect(classifySnapshotError(new Error("snapshot failed: 500"))).toBe("transient");
    expect(classifySnapshotError(new Error("network down"))).toBe("transient");
  });
});

describe("retryDelayMs", () => {
  it("is bounded exponential backoff capped at 30s", () => {
    expect(retryDelayMs(1)).toBe(500);
    expect(retryDelayMs(2)).toBe(1000);
    expect(retryDelayMs(7)).toBe(30_000);
    expect(retryDelayMs(60)).toBe(30_000);
  });
});

describe("streamClosed", () => {
  it("detects permanently closed sockets", () => {
    const src = new FakeSource({} as Handlers);
    expect(streamClosed(src as unknown as EventSource)).toBe(false);
    src.closePermanently();
    expect(streamClosed(src as unknown as EventSource)).toBe(true);
  });
});

describe("SessionStream recovery", () => {
  it("renders snapshot messages then goes live on stream open", async () => {
    vi.mocked(fetchEventSnapshot).mockResolvedValue(snap([msg("m1")], 5));
    render(<SessionStream sessionId="s-1" />);
    await screen.findByText("from snapshot m1");
    const src = fakeSources[0];
    expect(openStream).toHaveBeenCalledWith("session", "s-1", 5, expect.any(Object));
    src.open();
    await screen.findByText("live");
  });

  it("retries a transient initial snapshot failure with backoff, then connects", async () => {
    vi.mocked(fetchEventSnapshot)
      .mockRejectedValueOnce(new Error("snapshot failed: 503"))
      .mockResolvedValue(snap([msg("m1")], 0));
    render(<SessionStream sessionId="s-1" />);
    await screen.findByText("snapshot unavailable — retrying");
    // first retry lands at 500ms — real timers keep the test honest
    await screen.findByText("from snapshot m1", undefined, { timeout: 3000 });
    const src = fakeSources[0];
    src.open();
    await screen.findByText("live");
    expect(vi.mocked(fetchEventSnapshot).mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("treats a 403 snapshot as terminal: revoked state, cleared content, no retry", async () => {
    vi.mocked(fetchEventSnapshot).mockRejectedValue(new Error("snapshot failed: 403"));
    render(<SessionStream sessionId="s-1" />);
    await screen.findByText("access revoked");
    await screen.findByText("access to this session was revoked");
    expect(openStream).not.toHaveBeenCalled();
    await new Promise((r) => setTimeout(r, 1200));
    expect(vi.mocked(fetchEventSnapshot)).toHaveBeenCalledTimes(1);
  });

  it("dedupes messages arriving via both snapshot overlap and stream replay", async () => {
    vi.mocked(fetchEventSnapshot).mockResolvedValue(snap([msg("m1")], 3));
    render(<SessionStream sessionId="s-1" />);
    await screen.findByText("from snapshot m1");
    const src = fakeSources[0];
    src.open();
    await screen.findByText("live");
    src.message("m1", 4, "dup of m1"); // same id, later seq — never double-renders
    src.message("m2", 5);
    src.message("m2", 5);
    await waitFor(() =>
      expect(
        document.querySelectorAll('ul[aria-label="session messages"] li[data-kind="message"]')
          .length,
      ).toBe(2),
    );
  });

  it("re-probes the snapshot and reopens when the socket closes permanently", async () => {
    vi.mocked(fetchEventSnapshot).mockResolvedValue(snap([msg("m1")], 1));
    render(<SessionStream sessionId="s-1" />);
    await waitFor(() => expect(openStream).toHaveBeenCalled());
    await screen.findByText("from snapshot m1");
    const src = fakeSources[0];
    src.open();
    await screen.findByText("live");

    // non-2xx close: EventSource cannot distinguish 403 from a network
    // drop — the component must probe the snapshot to classify
    vi.mocked(fetchEventSnapshot).mockResolvedValue(snap([msg("m1"), msg("m2")], 9));
    src.closePermanently();
    await screen.findByText("from snapshot m2");
    await waitFor(() => expect(fakeSources.length).toBe(2));
    fakeSources[1].open();
    await screen.findByText("live");
    expect(openStream).toHaveBeenLastCalledWith("session", "s-1", 9, expect.any(Object));
  });

  it("stays terminal after a closed socket probes 403", async () => {
    vi.mocked(fetchEventSnapshot).mockResolvedValue(snap([], 0));
    render(<SessionStream sessionId="s-1" />);
    await waitFor(() => expect(openStream).toHaveBeenCalled());
    const src = fakeSources[0];
    src.open();
    await screen.findByText("live");
    vi.mocked(fetchEventSnapshot).mockRejectedValue(new Error("snapshot failed: 403"));
    src.closePermanently();
    await screen.findByText("access revoked");
    expect(fakeSources.length).toBe(1); // never reopened
  });
});
