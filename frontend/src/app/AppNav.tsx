import type { AppView } from "@/shared/types";

const ITEMS: { value: AppView; label: string }[] = [
  { value: "intake", label: "Intake" },
  { value: "calendar", label: "Calendar" },
  { value: "profile", label: "Profile" },
  { value: "review", label: "Review" },
];

interface AppNavProps {
  current: AppView;
  onChange: (view: AppView) => void;
  isAdmin?: boolean;
}

export function AppNav({ current, onChange, isAdmin = false }: AppNavProps) {
  const items = ITEMS.filter(
    (item) => item.value !== "review" || isAdmin,
  );

  return (
    <nav className="app-nav" aria-label="Sections">
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          className={current === item.value ? "active" : ""}
          aria-current={current === item.value ? "page" : undefined}
          onClick={() => onChange(item.value)}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
}
