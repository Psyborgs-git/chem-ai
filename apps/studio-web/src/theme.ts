// Client-local UI preference only — not server state. §8.2 forbids
// persisting Relay/server data in browser storage, so the theme
// choice is kept in a small cookie instead.
export type Theme = "light" | "dark";

const COOKIE = "studio_theme";

export function readTheme(): Theme | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${COOKIE}=(light|dark)\\b`));
  return match ? (match[1] as Theme) : null;
}

export function writeTheme(theme: Theme): void {
  document.cookie = `${COOKIE}=${theme}; path=/; max-age=31536000; samesite=lax`;
}
