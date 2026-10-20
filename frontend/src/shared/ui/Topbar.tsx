import type { ReactNode } from "react";

interface TopbarProps {
  right?: ReactNode;
  center?: ReactNode;
}

export function Topbar({ right, center }: TopbarProps) {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          CT
        </span>
        <span className="brand-name">Calorie Tracker</span>
      </div>
      {center}
      {right}
    </header>
  );
}
