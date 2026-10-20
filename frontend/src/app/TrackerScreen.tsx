import { useState, type ReactNode } from "react";
import { CalendarView } from "@/features/calendar";
import { IntakeView } from "@/features/intake";
import { logout } from "@/shared/api";
import type { AppView, User } from "@/shared/types";
import { Topbar } from "@/shared/ui";

interface TrackerScreenProps {
  user: User;
  view: "intake" | "calendar";
  date: string;
  nav: ReactNode;
  onViewChange: (view: AppView) => void;
  onDateChange: (iso: string) => void;
  onSessionExpired: () => void;
  onSignedOut: () => void;
}

export default function TrackerScreen({
  user,
  view,
  date,
  nav,
  onViewChange,
  onDateChange,
  onSessionExpired,
  onSignedOut,
}: TrackerScreenProps) {
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);

  async function handleSignOut() {
    setSigningOut(true);
    setSignOutError(null);
    try {
      await logout();
      onSignedOut();
    } catch {
      setSigningOut(false);
      setSignOutError("Could not sign out. Check your connection and try again.");
    }
  }

  function openDay(iso: string) {
    onDateChange(iso);
    onViewChange("intake");
  }

  return (
    <div className="app">
      <Topbar
        center={nav}
        right={
          <div className="topbar-actions">
            <span className="user-chip" title={`@${user.username}`}>
              @{user.username}
            </span>
            <button
              type="button"
              className="signout-button"
              onClick={handleSignOut}
              disabled={signingOut}
            >
              {signingOut ? "Signing out…" : "Sign out"}
            </button>
          </div>
        }
      />

      <main className="page">
        {signOutError && (
          <div className="banner" role="alert">
            <span className="banner-icon" aria-hidden="true">
              !
            </span>
            <p>{signOutError}</p>
            <button
              type="button"
              className="icon-button"
              aria-label="Dismiss error"
              onClick={() => setSignOutError(null)}
            >
              ×
            </button>
          </div>
        )}

        {view === "intake" ? (
          <IntakeView
            date={date}
            onDateChange={onDateChange}
            onSessionExpired={onSessionExpired}
          />
        ) : (
          <CalendarView
            selectedDate={date}
            onOpenDay={openDay}
            onSessionExpired={onSessionExpired}
          />
        )}
      </main>
    </div>
  );
}
