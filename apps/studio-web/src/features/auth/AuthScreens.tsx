import { useState, type FormEvent } from "react";

import { Button } from "../../components/atoms/Button";
import { TextField } from "../../components/atoms/TextField";
import { InlineFinding } from "../../components/molecules/InlineFinding";
import {
  authSetupOwner,
  authSignIn,
  type AuthResult,
} from "../../relay/network";

/** Entry surfaces (§21.2, PAR-06).
 *
 * Loopback single-owner deployment: the only credential bootstrap is
 * this first-run form, shown only while the server reports the
 * workspace has no owner. There is deliberately no public sign-up —
 * after bootstrap, entry is the normal sign-in form.
 *
 * Both forms submit through `relay/network.ts` (the only credentialed
 * transport). Success reloads the page: the reload re-runs the
 * setup/viewer gate and drops every identity-scoped client cache —
 * the simplest correct invalidation (PAR-06). The destination URL is
 * untouched, so a sign-in returns the user to where they were.
 */

type Pending = "idle" | "submitting";

function failureMessage(result: AuthResult & { ok: false }): string {
  if (result.code === "UNAUTHENTICATED") {
    return "Sign-in failed: the login or password is not recognized.";
  }
  if (result.code === "CONFLICT") {
    return "An owner account already exists — use the sign-in form.";
  }
  return result.message;
}

/** Narrow auth chrome — the signed-out surfaces have no navigation
 * because there is nothing a signed-out user may open. */
function AuthFrame({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="cs-shell">
      <a className="cs-skip-link" href="#main">
        Skip to content
      </a>
      <header className="cs-shell__header">
        <span className="cs-shell__brand">Chemistry Studio</span>
      </header>
      <main id="main" tabIndex={-1}>
        <h1>{title}</h1>
        {children}
      </main>
    </div>
  );
}

/** First-run owner bootstrap — the explicitly supported way to create
 * the one owner account on a fresh local install. Rendered only when
 * `/api/auth/setup-needed` reports no owner exists. */
export function FirstRunScreen() {
  const [login, setLogin] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pending, setPending] = useState<Pending>("idle");
  const [errors, setErrors] = useState<string[]>([]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const next: string[] = [];
    if (password.length < 10) {
      next.push("Password must be at least 10 characters.");
    }
    if (password !== confirm) {
      next.push("Passwords do not match.");
    }
    if (next.length > 0) {
      setErrors(next);
      return;
    }
    setErrors([]);
    setPending("submitting");
    void authSetupOwner({ login, displayName, password }).then((res) => {
      if (res.ok) {
        // Setup already issued a session cookie; reload enters the app.
        window.location.assign("/");
        return;
      }
      setPending("idle");
      setErrors([failureMessage(res)]);
    });
  };

  return (
    <AuthFrame title="Set up Chemistry Studio">
      <p>
        This local workspace has no accounts yet. Create the owner
        account to start — it happens once, on this installation only.
      </p>
      <form aria-label="owner setup" onSubmit={submit}>
        <TextField
          label="login"
          value={login}
          onChange={(e) => setLogin(e.target.value)}
          autoComplete="username"
          required
        />
        <TextField
          label="display name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          required
        />
        <TextField
          label="password"
          hint="at least 10 characters"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          required
        />
        <TextField
          label="confirm password"
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          autoComplete="new-password"
          required
        />
        {errors.map((m) => (
          <InlineFinding key={m} severity="error" message={m} />
        ))}
        <Button
          variant="primary"
          type="submit"
          disabled={pending === "submitting"}
        >
          {pending === "submitting" ? "Creating…" : "Create owner account"}
        </Button>
      </form>
    </AuthFrame>
  );
}

/** Normal sign-in for existing installs, and the session-ended
 * surface a mid-session UNAUTHENTICATED failure routes to. */
export function SignInScreen({ expired = false }: { expired?: boolean }) {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState<Pending>("idle");
  const [errors, setErrors] = useState<string[]>([]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setErrors([]);
    setPending("submitting");
    void authSignIn({ login, password }).then((res) => {
      if (res.ok) {
        // Hard reload: the destination URL is preserved, every
        // identity-scoped cache (Relay store included) is dropped.
        window.location.reload();
        return;
      }
      setPending("idle");
      setErrors([failureMessage(res)]);
    });
  };

  return (
    <AuthFrame title="Sign in">
      {expired && (
        <InlineFinding
          severity="info"
          message="Your session ended — sign in again to continue."
        />
      )}
      <form aria-label="sign in" onSubmit={submit}>
        <TextField
          label="login"
          value={login}
          onChange={(e) => setLogin(e.target.value)}
          autoComplete="username"
          required
        />
        <TextField
          label="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />
        {errors.map((m) => (
          <InlineFinding key={m} severity="error" message={m} />
        ))}
        <Button
          variant="primary"
          type="submit"
          disabled={pending === "submitting"}
        >
          {pending === "submitting" ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </AuthFrame>
  );
}
