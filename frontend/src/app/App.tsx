import { useCallback, useEffect, useState } from "react";
import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { AdminReviewScreen } from "@/features/admin";
import { AuthScreen } from "@/features/auth";
import { ProfileScreen } from "@/features/profile";
import { ApiError, getMe } from "@/shared/api";
import {
  isValidISODate,
  isValidMonthKey,
  todayISO,
} from "@/shared/lib";
import type { User } from "@/shared/types";
import { Topbar } from "@/shared/ui";
import { AppNav } from "./AppNav";
import TrackerScreen from "./TrackerScreen";

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [bootError, setBootError] = useState<string | null>(null);
  const [authNotice, setAuthNotice] = useState<string | null>(null);
  const [bootKey, setBootKey] = useState(0);
  const [selectedDate, setSelectedDate] = useState(() => {
    const date = new URLSearchParams(location.search).get("date");
    return isValidISODate(date) ? date : todayISO();
  });
  const [calendarMonth, setCalendarMonth] = useState(() => {
    const month = new URLSearchParams(location.search).get("month");
    return isValidMonthKey(month) ? month : selectedDate.slice(0, 7);
  });

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

  useEffect(() => {
    if (location.pathname !== "/intake" && location.pathname !== "/calendar") {
      return;
    }
    const date = new URLSearchParams(location.search).get("date");
    setSelectedDate(isValidISODate(date) ? date : todayISO());
  }, [location.pathname, location.search]);

  useEffect(() => {
    if (location.pathname !== "/calendar") return;
    const month = new URLSearchParams(location.search).get("month");
    setCalendarMonth(
      isValidMonthKey(month) ? month : selectedDate.slice(0, 7),
    );
  }, [location.pathname, location.search, selectedDate]);

  const handleAuthenticated = useCallback((authenticated: User) => {
    setAuthNotice(null);
    setUser(authenticated);
  }, []);

  const handleSessionExpired = useCallback(() => {
    setAuthNotice("Your session expired. Sign in again to keep tracking.");
    setUser(null);
  }, []);

  const handleSignedOut = useCallback(() => {
    setAuthNotice("You've been signed out.");
    setUser(null);
  }, []);

  const handleDateChange = useCallback(
    (iso: string) => {
      setSelectedDate(iso);
      setCalendarMonth(iso.slice(0, 7));
      const params = new URLSearchParams({ date: iso });
      navigate({ pathname: "/intake", search: params.toString() });
    },
    [navigate],
  );

  const handleMonthChange = useCallback(
    (month: string) => {
      setCalendarMonth(month);
      const params = new URLSearchParams({
        month,
        date: selectedDate,
      });
      navigate({ pathname: "/calendar", search: params.toString() });
    },
    [navigate, selectedDate],
  );

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
      selectedDate={selectedDate}
      calendarMonth={calendarMonth}
      isAdmin={user.role === "admin"}
    />
  );

  const intakePath = `/intake?${new URLSearchParams({
    date: selectedDate,
  }).toString()}`;

  return (
    <Routes>
      <Route path="/" element={<Navigate to={intakePath} replace />} />
      <Route
        path="/intake"
        element={
          <TrackerScreen
            user={user}
            view="intake"
            date={selectedDate}
            month={calendarMonth}
            nav={nav}
            onDateChange={handleDateChange}
            onMonthChange={handleMonthChange}
            onSessionExpired={handleSessionExpired}
            onSignedOut={handleSignedOut}
          />
        }
      />
      <Route
        path="/calendar"
        element={
          <TrackerScreen
            user={user}
            view="calendar"
            date={selectedDate}
            month={calendarMonth}
            nav={nav}
            onDateChange={handleDateChange}
            onMonthChange={handleMonthChange}
            onSessionExpired={handleSessionExpired}
            onSignedOut={handleSignedOut}
          />
        }
      />
      <Route
        path="/profile"
        element={
          <ProfileScreen
            user={user}
            nav={nav}
            onSessionExpired={handleSessionExpired}
            onSignedOut={handleSignedOut}
          />
        }
      />
      <Route
        path="/review"
        element={
          user.role === "admin" ? (
            <AdminReviewScreen
              user={user}
              nav={nav}
              onSessionExpired={handleSessionExpired}
              onSignedOut={handleSignedOut}
            />
          ) : (
            <Navigate to={intakePath} replace />
          )
        }
      />
      <Route path="*" element={<Navigate to={intakePath} replace />} />
    </Routes>
  );
}
