import type { ReactNode } from "react";

interface MacroMetricProps {
  label: string;
  value?: number;
  target: number;
  unit: string;
  tone: "protein" | "fat" | "water";
  mode?: "progress" | "target";
  children?: ReactNode;
}

export default function MacroMetric({
  label,
  value = 0,
  target,
  unit,
  tone,
  mode = "progress",
  children,
}: MacroMetricProps) {
  const percent = target > 0 ? Math.min(100, (value / target) * 100) : 0;
  return (
    <div className="macro-metric">
      <div className="macro-metric-head">
        <span>{label}</span>
        <strong>
          {mode === "target"
            ? target.toLocaleString("en-GB")
            : value.toLocaleString("en-GB")}
          <small>
            {mode === "target"
              ? ` ${unit} daily target`
              : ` / ${target.toLocaleString("en-GB")} ${unit}`}
          </small>
        </strong>
      </div>
      {mode === "progress" && (
        <div className="macro-track">
          <span
            className={`macro-fill macro-${tone}`}
            style={{ width: `${percent}%` }}
          />
        </div>
      )}
      {children}
    </div>
  );
}
