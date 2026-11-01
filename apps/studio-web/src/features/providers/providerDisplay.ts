/** Never render upstream exception text: some services echo authorization headers. */
export function providerFailure(code?: string, fieldPath?: string | null): string {
  if (code === "CONFLICT" && fieldPath === "apiKey") return "The secure credential store is unavailable. Unlock your macOS keychain and try again.";
  switch (code) {
    case "FORBIDDEN": return "Your account is not allowed to change these provider settings.";
    case "UNAUTHENTICATED": return "Your session expired. Sign in again before continuing.";
    case "CONFLICT": return "These settings changed elsewhere. Reload them before trying again.";
    case "NOT_FOUND": return "This provider is no longer available. Reload the page to continue.";
    case "INVALID_INPUT": case "VALIDATION": return "The provider details were not accepted. Check the endpoint, model, and API key settings.";
    case "KEYCHAIN_UNAVAILABLE": case "SECRET_STORE_UNAVAILABLE": return "The secure credential store is unavailable. Unlock your macOS keychain and try again.";
    default: return "The operation could not be confirmed. Check the connection and try again.";
  }
}

export function normalizedEndpoint(value: string): string {
  try { return new URL(value.trim()).toString().replace(/\/+$/, ""); }
  catch { return value.trim(); }
}

export function endpointIsLocal(value: string): boolean {
  try { return ["localhost", "127.0.0.1", "[::1]"].includes(new URL(value).hostname); }
  catch { return false; }
}

export function endpointError(value: string): string | undefined {
  if (!value.trim()) return undefined;
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) return "Use an HTTP or HTTPS base URL without credentials, query parameters, or a fragment.";
    if (url.protocol === "http:" && !endpointIsLocal(value)) return "Use HTTPS for a remote provider. HTTP is available only for a loopback endpoint.";
    return undefined;
  } catch { return "Enter a complete base URL, including https:// or a local http:// address."; }
}
