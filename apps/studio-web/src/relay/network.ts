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

/* ---- auth + session (§21.2, PAR-06) ----
 *
 * Passwords travel only in POST bodies over the loopback origin:
 * never in URLs, never persisted client-side (the `studio_session`
 * cookie is httponly and server-managed — this module never reads
 * it). Authorization stays server-side; these calls only establish
 * or end the session.
 */

export type AuthResult =
  | { ok: true }
  | { ok: false; code: string; message: string };

/** Server error body is `{errors: [{code, message, fieldPath, …}]}`
 * (the FastAPI DomainError handler); fall back to the status. */
function authFailure(status: number, body: unknown): AuthResult {
  const errors = (body as { errors?: unknown } | null)?.errors;
  const first = Array.isArray(errors)
    ? (errors[0] as Record<string, unknown> | undefined)
    : undefined;
  return {
    ok: false,
    code: typeof first?.code === "string" ? first.code : "UNKNOWN",
    message:
      typeof first?.message === "string"
        ? first.message
        : `request failed (${status})`,
  };
}

async function postAuth(
  path: string,
  body: Record<string, unknown> | null,
): Promise<AuthResult> {
  let resp: Response;
  try {
    resp = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : null,
    });
  } catch {
    return {
      ok: false,
      code: "NETWORK",
      message: "could not reach the server — is the API running?",
    };
  }
  if (resp.ok) return { ok: true };
  return authFailure(resp.status, await resp.json().catch(() => null));
}

/** First-run owner bootstrap (§21.2): succeeds only while the
 * workspace has no owner; CONFLICT means normal sign-in applies. */
export function authSetupOwner(input: {
  login: string;
  displayName: string;
  password: string;
}): Promise<AuthResult> {
  return postAuth("/api/auth/setup", {
    login: input.login,
    display_name: input.displayName,
    password: input.password,
  });
}

export function authSignIn(input: {
  login: string;
  password: string;
}): Promise<AuthResult> {
  return postAuth("/api/auth/login", {
    login: input.login,
    password: input.password,
  });
}

/** Server revokes the session row and clears the cookie; safe to
 * call even when the session is already gone. */
export async function authSignOut(): Promise<AuthResult> {
  return postAuth("/api/auth/logout", null);
}

export type ViewerProbe =
  | { kind: "signed_in"; displayName: string }
  | { kind: "signed_out" }
  | { kind: "error"; message: string };

/** Signed-in probe via the GraphQL viewer field — the same single
 * transport as every other query. UNAUTHENTICATED → signed_out;
 * transport/unexpected failures surface honestly as `error` (never
 * masquerade as signed-out, which would mislead a signed-in user). */
export async function probeViewer(): Promise<ViewerProbe> {
  try {
    const body = await fetchGraphQL(
      { text: "query { viewer { id displayName } }" } as RequestParameters,
      {},
    );
    const viewer = (body as { data?: { viewer?: { displayName?: unknown } } })
      ?.data?.viewer;
    if (viewer && typeof viewer.displayName === "string") {
      return { kind: "signed_in", displayName: viewer.displayName };
    }
    const codes = new Set(
      ((body as { errors?: { extensions?: { code?: unknown } }[] })?.errors ?? [])
        .map((e) => e?.extensions?.code)
        .filter((c): c is string => typeof c === "string"),
    );
    if (codes.has("UNAUTHENTICATED")) return { kind: "signed_out" };
    return { kind: "error", message: "unexpected viewer response" };
  } catch (err) {
    return {
      kind: "error",
      message: err instanceof Error ? err.message : "unknown error",
    };
  }
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
