import { useState, type FormEvent } from "react";
import { ApiError, login, register } from "@/shared/api";
import { USERNAME_PATTERN, type User } from "@/shared/types";
import { Topbar } from "@/shared/ui";

type Mode = "login" | "register";

interface AuthScreenProps {
  initialNotice: string | null;
  onAuthenticated: (user: User) => void;
}

export function AuthScreen({ initialNotice, onAuthenticated }: AuthScreenProps) {
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
    setPassword("");
    setConfirm("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const name = username.trim().toLowerCase();

    if (!USERNAME_PATTERN.test(name)) {
      setError(
        "Username must be 3–32 characters using letters, numbers, dot, dash, or underscore.",
      );
      return;
    }

    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    if (mode === "register" && password !== confirm) {
      setError("Passwords don't match.");
      return;
    }

    setSubmitting(true);

    try {
      const user =
        mode === "register"
          ? await register({ username: name, password })
          : await login({ username: name, password });
      onAuthenticated(user);
    } catch (caught) {
      if (caught instanceof ApiError) {
        if (caught.status === 401) {
          setError("Invalid username or password.");
        } else if (caught.status === 409) {
          setError("That username is already taken.");
        } else if (caught.status === 422) {
          setError("Check your username and password (8+ characters).");
        } else {
          setError(caught.message);
        }
      } else {
        setError("Could not reach the server. Check the API and try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="app tone-neutral">
      <Topbar right={<span className="step-pill">Account</span>} />

      <main className="page">
        <section className="intro">
          <p className="eyebrow">
            {mode === "login" ? "Sign in" : "Get started"}
          </p>
          <h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1>
          <p className="lede">
            Your profile stays tied to this account, across refreshes and
            browser restarts.
          </p>
        </section>

        {initialNotice && (
          <div className="banner info" role="status">
            <span className="banner-icon" aria-hidden="true">
              i
            </span>
            <p>{initialNotice}</p>
          </div>
        )}

        {error && (
          <div className="banner" role="alert">
            <span className="banner-icon" aria-hidden="true">
              !
            </span>
            <p>{error}</p>
            <button
              type="button"
              className="icon-button"
              aria-label="Dismiss error"
              onClick={() => setError(null)}
            >
              ×
            </button>
          </div>
        )}

        <section className="card auth-card">
          <div className="auth-tabs" role="group" aria-label="Authentication mode">
            <button
              type="button"
              className={mode === "login" ? "active" : ""}
              aria-pressed={mode === "login"}
              onClick={() => switchMode("login")}
            >
              Log in
            </button>
            <button
              type="button"
              className={mode === "register" ? "active" : ""}
              aria-pressed={mode === "register"}
              onClick={() => switchMode("register")}
            >
              Create account
            </button>
          </div>

          <form className="auth-form" onSubmit={handleSubmit} noValidate>
            <label className="field">
              <span className="field-label">Username</span>
              <input
                className="text-input"
                type="text"
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                maxLength={32}
                placeholder="yourname"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </label>

            <label className="field">
              <span className="field-label">Password</span>
              <input
                className="text-input"
                type="password"
                name="password"
                autoComplete={
                  mode === "login" ? "current-password" : "new-password"
                }
                maxLength={128}
                placeholder="At least 8 characters"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>

            {mode === "register" && (
              <label className="field">
                <span className="field-label">Confirm password</span>
                <input
                  className="text-input"
                  type="password"
                  name="confirm"
                  autoComplete="new-password"
                  maxLength={128}
                  placeholder="Repeat password"
                  value={confirm}
                  onChange={(event) => setConfirm(event.target.value)}
                />
              </label>
            )}

            <button
              type="submit"
              className="save-button auth-submit"
              disabled={submitting}
            >
              {submitting
                ? "Please wait…"
                : mode === "login"
                  ? "Log in"
                  : "Create account"}
            </button>
          </form>

          <p className="auth-note">
            Sessions stay signed in for 30 days on this device.
          </p>
        </section>
      </main>
    </div>
  );
}
