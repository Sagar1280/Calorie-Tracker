import type { DayLog } from "@/shared/types";
import MacroMetric from "./MacroMetric";

interface CalorieHeroProps {
  log: DayLog | null;
}

export default function CalorieHero({ log }: CalorieHeroProps) {
  const consumed = log?.consumed ?? 0;
  const goal = log?.goal ?? 2000;
  const remaining = goal - consumed;
  const percent = goal > 0 ? Math.min(100, (consumed / goal) * 100) : 0;
  const over = consumed > goal;
  const proteinGoal = log?.protein_goal_g ?? 60;
  const fatGoal = log?.fat_goal_g ?? 56;
  const waterGoal = log?.water_goal_ml ?? 2000;
  const proteinConsumed = Math.round((log?.protein_consumed_g ?? 0) * 10) / 10;
  const fatConsumed = Math.round((log?.fat_consumed_g ?? 0) * 10) / 10;

  return (
    <section
      className={`calorie-hero${over ? " is-over" : ""}${
        log?.done ? " is-done" : ""
      }`}
    >
      <div className="hero-top">
        <p className="eyebrow">Calories consumed</p>
        <span className="goal-chip">
          {log?.done
            ? "Day done ✓"
            : `${goal.toLocaleString("en-GB")} kcal goal`}
        </span>
      </div>
      <div className="hero-number-row">
        <span className="hero-number">{consumed.toLocaleString("en-GB")}</span>
        <span className="hero-goal">
          / {goal.toLocaleString("en-GB")} kcal
        </span>
      </div>
      <div
        className="progress-track"
        role="progressbar"
        aria-valuenow={consumed}
        aria-valuemin={0}
        aria-valuemax={goal}
        aria-label="Calories consumed toward goal"
      >
        <span className="progress-fill" style={{ width: `${percent}%` }} />
      </div>
      <div className="hero-foot">
        <span>
          {remaining >= 0
            ? `${remaining.toLocaleString("en-GB")} kcal left`
            : `${Math.abs(remaining).toLocaleString("en-GB")} kcal over`}
        </span>
        <span>{Math.round((consumed / goal) * 100)}% of goal</span>
      </div>
      <p className="goal-note">
        {log?.goal_source === "profile"
          ? "Your goal is estimated from the profile details you saved."
          : "Using a default 2,000 kcal goal. Add your profile to get a tailored target."}
      </p>

      <div className="macro-panel">
        <MacroMetric
          label="Protein"
          value={proteinConsumed}
          target={proteinGoal}
          unit="g"
          tone="protein"
        />
        <MacroMetric
          label="Fat"
          value={fatConsumed}
          target={fatGoal}
          unit="g"
          tone="fat"
        />
        <MacroMetric
          label="Water"
          target={waterGoal}
          unit="ml"
          tone="water"
          mode="target"
        >
          <p className="macro-note">Auto-calculated from your BMI</p>
        </MacroMetric>
      </div>
    </section>
  );
}
