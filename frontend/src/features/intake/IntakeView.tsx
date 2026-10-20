import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  deleteCalorieEntry,
  getCalorieDay,
  setCalorieDayDone,
} from "@/shared/api";
import { MEAL_OPTIONS, type CalorieEntry, type DayLog } from "@/shared/types";
import CalorieHero from "./components/CalorieHero";
import DateStrip from "./components/DateStrip";
import DayToggle from "./components/DayToggle";
import FoodPicker from "./components/FoodPicker";
import IntakeSkeleton from "./components/IntakeSkeleton";
import MealGroups from "./components/MealGroups";

interface IntakeViewProps {
  date: string;
  onDateChange: (iso: string) => void;
  onSessionExpired: () => void;
}

export default function IntakeView({
  date,
  onDateChange,
  onSessionExpired,
}: IntakeViewProps) {
  const [log, setLog] = useState<DayLog | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [savingDone, setSavingDone] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setLoadError(null);
    setLog(null);

    getCalorieDay(date)
      .then((day) => {
        if (!cancelled) setLog(day);
      })
      .catch((caught) => {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.status === 401) {
          onSessionExpired();
          return;
        }
        setLoadError(
          "Could not load this day. Make sure the API is running, then try again.",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [date, reloadKey, onSessionExpired]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 2400);
    return () => window.clearTimeout(timer);
  }, [notice]);

  function handleEntryAdded(created: CalorieEntry) {
    setNotice("Entry added");
    setLog((current) =>
      current
        ? {
            ...current,
            entries: [...current.entries, created],
            consumed: current.consumed + (created.calories ?? 0),
            remaining:
              current.goal - (current.consumed + (created.calories ?? 0)),
            protein_consumed_g:
              Math.round(
                (current.protein_consumed_g + (created.protein_g ?? 0)) * 10,
              ) / 10,
            fat_consumed_g:
              Math.round(
                (current.fat_consumed_g + (created.fat_g ?? 0)) * 10,
              ) / 10,
          }
        : current,
    );
  }

  async function handleDelete(entryId: number) {
    setDeletingId(entryId);
    setFormError(null);

    try {
      await deleteCalorieEntry(entryId);
      setNotice("Entry removed");
      setLog((current) => {
        if (!current) return current;
        const entries = current.entries.filter((entry) => entry.id !== entryId);
        const consumed = entries.reduce(
          (sum, entry) => sum + (entry.calories ?? 0),
          0,
        );
        const protein = entries.reduce(
          (sum, entry) => sum + (entry.protein_g ?? 0),
          0,
        );
        const fat = entries.reduce((sum, entry) => sum + (entry.fat_g ?? 0), 0);
        return {
          ...current,
          entries,
          consumed,
          remaining: current.goal - consumed,
          protein_consumed_g: Math.round(protein * 10) / 10,
          fat_consumed_g: Math.round(fat * 10) / 10,
        };
      });
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        onSessionExpired();
        return;
      }
      if (caught instanceof ApiError) {
        setFormError(caught.message);
      } else {
        setFormError("Could not remove that entry. Check your connection.");
      }
    } finally {
      setDeletingId(null);
    }
  }

  async function handleToggleDone() {
    if (!log || savingDone) return;

    setSavingDone(true);
    setFormError(null);

    try {
      const updated = await setCalorieDayDone({ date, done: !log.done });
      setLog(updated);
      setNotice(updated.done ? "Day marked done" : "Day reopened");
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        onSessionExpired();
        return;
      }
      if (caught instanceof ApiError) {
        setFormError(caught.message);
      } else {
        setFormError("Could not update this day. Check your connection.");
      }
    } finally {
      setSavingDone(false);
    }
  }

  const groups = useMemo(() => {
    const entries = log?.entries ?? [];
    return MEAL_OPTIONS.map((option) => {
      const items = entries.filter((entry) => entry.meal === option.value);
      return {
        ...option,
        items,
        total: items.reduce((sum, entry) => sum + (entry.calories ?? 0), 0),
      };
    });
  }, [log]);

  return (
    <>
      <section className="intro intake-intro">
        <div>
          <p className="eyebrow">Daily intake</p>
          <h1>Calories</h1>
          <p className="lede">
            Log each meal and watch the day add up. Everything is saved to your
            account.
          </p>
        </div>
        <DayToggle
          done={Boolean(log?.done)}
          saving={savingDone}
          disabled={!log || savingDone}
          onToggle={handleToggleDone}
        />
      </section>

      <DateStrip date={date} onDateChange={onDateChange} />

      {loading && !log ? (
        <IntakeSkeleton />
      ) : loadError ? (
        <section className="card state-card">
          <span className="state-icon" aria-hidden="true">
            !
          </span>
          <h1>Can't load this day</h1>
          <p>{loadError}</p>
          <button
            type="button"
            className="primary-button"
            onClick={() => setReloadKey((value) => value + 1)}
          >
            Try again
          </button>
        </section>
      ) : (
        <>
          <CalorieHero log={log} />

          {log?.done && (
            <p className="day-lock-note">
              Editing is locked for this day. Toggle “Day complete” off above to
              add or remove food.
            </p>
          )}

          {formError && (
            <div className="banner" role="alert">
              <span className="banner-icon" aria-hidden="true">
                !
              </span>
              <p>{formError}</p>
              <button
                type="button"
                className="icon-button"
                aria-label="Dismiss error"
                onClick={() => setFormError(null)}
              >
                ×
              </button>
            </div>
          )}

          {!log?.done && (
            <FoodPicker
              date={date}
              onAdded={handleEntryAdded}
              onSessionExpired={onSessionExpired}
            />
          )}

          <MealGroups
            groups={groups}
            deletingId={deletingId}
            onDelete={handleDelete}
          />
        </>
      )}

      {notice && (
        <div className="toast" role="status">
          <span className="toast-check" aria-hidden="true">
            ✓
          </span>
          {notice}
        </div>
      )}
    </>
  );
}
