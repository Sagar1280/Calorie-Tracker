import type { CalorieEntry, Meal } from "@/shared/types";

export interface MealGroup {
  value: Meal;
  label: string;
  items: CalorieEntry[];
  total: number;
}

interface MealGroupsProps {
  groups: MealGroup[];
  deletingId: number | null;
  onDelete: (entryId: number) => void;
}

export default function MealGroups({
  groups,
  deletingId,
  onDelete,
}: MealGroupsProps) {
  return (
    <div className="meal-groups">
      {groups.map((group) => (
        <section className="meal-card" key={group.value}>
          <header className="meal-head">
            <div className="meal-title">
              <span
                className={`meal-dot meal-dot-${group.value}`}
                aria-hidden="true"
              />
              <h3>{group.label}</h3>
            </div>
            <span className="meal-total">
              {group.total.toLocaleString("en-GB")} kcal
            </span>
          </header>

          {group.items.length === 0 ? (
            <p className="meal-empty">Nothing logged yet.</p>
          ) : (
            <ul className="entry-list">
              {group.items.map((entry: CalorieEntry) => (
                <li className="entry-row" key={entry.id}>
                  <span className="entry-name">{entry.name}</span>
                  <span className="entry-cal">
                    {(entry.calories ?? 0).toLocaleString("en-GB")} kcal
                  </span>
                  <button
                    type="button"
                    className="entry-delete"
                    aria-label={`Delete ${entry.name ?? "entry"}`}
                    onClick={() => onDelete(entry.id)}
                    disabled={deletingId === entry.id}
                  >
                    {deletingId === entry.id ? "…" : "×"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}
