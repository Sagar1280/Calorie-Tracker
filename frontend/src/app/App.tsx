import { useCallback, useEffect, useState } from "react";
import { AdminReviewScreen } from "@/features/admin";
import { AuthScreen } from "@/features/auth";
import { ProfileScreen } from "@/features/profile";
import { ApiError, getMe } from "@/shared/api";
import { todayISO } from "@/shared/lib";
import type { AppView, User } from "@/shared/types";
import { Topbar } from "@/shared/ui";
import { AppNav } from "./AppNav";
import TrackerScreen from "./TrackerScreen";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [bootError, setBootError] = useState<string | null>(null);
  const [authNotice, setAuthNotice] = useState<string | null>(null);
  const [bootKey, setBootKey] = useState(0);
  const [view, setView] = useState<AppView>("intake");
  const [selectedDate, setSelectedDate] = useState(todayISO());

  useEffect(() => {
    let cancelled = false;

    setChecking(true);
    setBootError(null);

    getMe()
      .then((me) => {
        if (!cancelled) setUser(me);
      })
      .catch((caught) => {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.status === 401) {
          setUser(null);
        } else {
          setBootError(
            "Could not reach the server. Make sure the API is running, then try again.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setChecking(false);
      });

    return () => {
      cancelled = true;
    };
  }, [bootKey]);

  const handleAuthenticated = useCallback((authenticated: User) => {
    setAuthNotice(null);
    setUser(authenticated);
    setView("intake");
    setSelectedDate(todayISO());
  }, []);

  const handleSessionExpired = useCallback(() => {
    setAuthNotice("Your session expired. Sign in again to keep tracking.");
    setUser(null);
  }, []);

  const handleSignedOut = useCallback(() => {
    setAuthNotice("You've been signed out.");
    setUser(null);
  }, []);

  if (checking) {
    return (
      <div className="app tone-neutral">
        <Topbar right={<span className="step-pill">Session</span>} />
        <main className="page">
          <div className="skeleton skeleton-intro" />
          <section className="card skeleton-card" aria-label="Checking session">
            <div className="skeleton skeleton-line skeleton-short" />
            <div className="skeleton skeleton-input" />
            <div className="skeleton skeleton-input" />
          </section>
          <p className="loading-caption">Checking your session…</p>
        </main>
      </div>
    );
  }

  if (bootError) {
    return (
      <div className="app tone-neutral">
        <Topbar right={<span className="step-pill">Offline</span>} />
        <main className="page">
          <section className="card state-card">
            <span className="state-icon" aria-hidden="true">
              !
            </span>
            <h1>Can't reach the API</h1>
            <p>{bootError}</p>
            <button
              type="button"
              className="primary-button"
              onClick={() => setBootKey((value) => value + 1)}
            >
              Try again
            </button>
          </section>
        </main>
      </div>
    );
  }

  if (!user) {
    return (
      <AuthScreen
        initialNotice={authNotice}
        onAuthenticated={handleAuthenticated}
      />
    );
  }

  const nav = (
    <AppNav
      current={view}
      onChange={setView}
      isAdmin={user.role === "admin"}
    />
  );

  if (view === "review" && user.role === "admin") {
    return (
      <AdminReviewScreen
        user={user}
        nav={nav}
        onSessionExpired={handleSessionExpired}
        onSignedOut={handleSignedOut}
      />
    );
  }

  if (view === "profile") {
    return (
      <ProfileScreen
        user={user}
        nav={nav}
        onSessionExpired={handleSessionExpired}
        onSignedOut={handleSignedOut}
      />
    );
  }

  return (
    <TrackerScreen
      user={user}
      view={view === "calendar" ? "calendar" : "intake"}
      date={selectedDate}
      nav={nav}
      onViewChange={setView}
      onDateChange={setSelectedDate}
      onSessionExpired={handleSessionExpired}
      onSignedOut={handleSignedOut}
    />
  );
}
