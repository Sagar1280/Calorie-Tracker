import { Link, useLocation } from "react-router-dom";

type NavPath = "/intake" | "/calendar" | "/profile" | "/review";

const ITEMS: { path: NavPath; label: string; adminOnly?: boolean }[] = [
  { path: "/intake", label: "Intake" },
  { path: "/calendar", label: "Calendar" },
  { path: "/profile", label: "Profile" },
  { path: "/review", label: "Review", adminOnly: true },
];

interface AppNavProps {
  selectedDate: string;
  calendarMonth: string;
  isAdmin?: boolean;
}

function search(params: Record<string, string>): string {
  return new URLSearchParams(params).toString();
}

export function AppNav({
  selectedDate,
  calendarMonth,
  isAdmin = false,
}: AppNavProps) {
  const location = useLocation();

  function target(path: NavPath): string {
    if (path === "/intake") {
      return `${path}?${search({ date: selectedDate })}`;
    }
    if (path === "/calendar") {
      return `${path}?${search({
        month: calendarMonth,
        date: selectedDate,
      })}`;
    }
    return path;
  }

  return (
    <nav className="app-nav" aria-label="Sections">
      {ITEMS.filter((item) => !item.adminOnly || isAdmin).map((item) => (
        <Link
          key={item.path}
          to={target(item.path)}
          className={location.pathname === item.path ? "active" : ""}
          aria-current={location.pathname === item.path ? "page" : undefined}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
