import type { RequestParameters, Variables } from "relay-runtime";
import { Network } from "relay-runtime";

/**
 * The ONLY transport layer (§8.2). Components never fetch GraphQL
 * directly; all requests go through this module so credentials,
 * same-origin policy and error shape stay in one place.
 */
async function fetchGraphQL(params: RequestParameters, variables: Variables) {
  const resp = await fetch("/graphql", {
    method: "POST",
    credentials: "same-origin",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query: params.text, variables }),
  });
  return resp.json();
}

export function createNetwork() {
  return Network.create(fetchGraphQL);
}

/** Relay GlobalIDs are `base64(Type:uuid)` — the REST channels use
 * the raw uuid. */
export function rawUuid(globalId: string): string {
  try {
    const decoded = atob(globalId);
    const parts = decoded.split(":");
    return parts[parts.length - 1] ?? globalId;
  } catch {
    return globalId;
  }
}

/** Non-GraphQL transport (session/setup endpoints live on REST). */
export async function fetchSetupNeeded(): Promise<boolean> {
  const resp = await fetch("/api/auth/setup-needed", {
    credentials: "same-origin",
  });
  if (!resp.ok) throw new Error(`status ${resp.status}`);
  const body = (await resp.json()) as { setupNeeded: boolean };
  return body.setupNeeded;
}

export type ChannelSnapshot = {
  maxSeq: number;
  channel: string;
  messages?: Array<{
    id: string;
    role: string;
    kind: string;
    content: string;
    refs: Record<string, unknown>;
  }>;
};

/** Authoritative snapshot for a bounded event channel (§8, CS-0406) —
 * REST transport like the auth endpoints above. */
export async function fetchEventSnapshot(
  channel: "session" | "task",
  aggregateId: string,
): Promise<ChannelSnapshot> {
  const params = new URLSearchParams({ channel, id: rawUuid(aggregateId) });
  const res = await fetch(`/api/events/snapshot?${params.toString()}`, {
    credentials: "same-origin",
  });
  if (!res.ok) throw new Error(`snapshot failed: ${res.status}`);
  return (await res.json()) as ChannelSnapshot;
}
