import { useEffect, useMemo, useState } from "react";
import { ApiError, getCalorieMonth } from "@/shared/api";
import {
  dayNumber,
  formatMonthYear,
  formatShortDate,
  monthCells,
  parseISODate,
  todayISO,
  WEEKDAYS,
} from "@/shared/lib";
import type { MonthLog } from "@/shared/types";

interface CalendarViewProps {
  selectedDate: string;
  onOpenDay: (iso: string) => void;
  onSessionExpired: () => void;
}

export default function CalendarView({
  selectedDate,
  onOpenDay,
  onSessionExpired,
}: CalendarViewProps) {
  const initial = parseISODate(selectedDate);
  const [cursor, setCursor] = useState({
    year: initial.getFullYear(),
    month: initial.getMonth() + 1,
  });
  const [log, setLog] = useState<MonthLog | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setLoadError(null);

    getCalorieMonth(cursor.year, cursor.month)
      .then((month) => {
        if (!cancelled) setLog(month);
      })
      .catch((caught) => {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.status === 401) {
          onSessionExpired();
          return;
        }
        setLoadError(
          "Could not load this month. Make sure the API is running, then try again.",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [cursor.year, cursor.month, reloadKey, onSessionExpired]);

  const cells = useMemo(
    () => monthCells(cursor.year, cursor.month),
    [cursor.year, cursor.month],
  );

  const byDate = useMemo(() => {
    const map = new Map<
      string,
      { consumed: number; entries: number; done: boolean }
    >();
    for (const day of log?.days ?? []) {
      map.set(day.date, {
        consumed: day.consumed,
        entries: day.entries,
        done: day.done,
      });
    }
    return map;
  }, [log]);

  const today = todayISO();
  const goal = log?.goal ?? 2000;

  function shiftMonth(delta: number) {
    const next = new Date(cursor.year, cursor.month - 1 + delta, 1, 12);
    setCursor({ year: next.getFullYear(), month: next.getMonth() + 1 });
  }

  function jumpToToday() {
    const now = new Date();
    setCursor({ year: now.getFullYear(), month: now.getMonth() + 1 });
  }

  return (
    <>
      <section className="intro">
        <p className="eyebrow">History</p>
        <h1>Calendar</h1>
        <p className="lede">
          Every logged day at a glance. Tap a date to open it and add food.
        </p>
      </section>

      <section className="card calendar-card">
        <div className="calendar-head">
          <div>
            <p className="eyebrow">Month view</p>
            <h2>{formatMonthYear(cursor.year, cursor.month)}</h2>
          </div>
          <div className="month-nav">
            <button
              type="button"
              className="date-arrow"
              aria-label="Previous month"
              onClick={() => shiftMonth(-1)}
            >
              ‹
            </button>
            <button
              type="button"
              className="today-button"
              onClick={jumpToToday}
            >
              Today
            </button>
            <button
              type="button"
              className="date-arrow"
              aria-label="Next month"
              onClick={() => shiftMonth(1)}
            >
              ›
            </button>
          </div>
        </div>

        {loading ? (
          <div className="calendar-loading">
            <div className="skeleton skeleton-line skeleton-short" />
            <div className="skeleton calendar-skeleton" />
          </div>
        ) : loadError ? (
          <div className="calendar-error">
            <p>{loadError}</p>
            <button
              type="button"
              className="text-button"
              onClick={() => setReloadKey((value) => value + 1)}
            >
              Try again
            </button>
          </div>
        ) : (
          <>
            <div className="month-stats">
              <div className="month-stat">
                <span className="month-stat-label">Days logged</span>
                <strong>{log?.days_logged ?? 0}</strong>
              </div>
              <div className="month-stat">
                <span className="month-stat-label">Total</span>
                <strong>
                  {(log?.total_consumed ?? 0).toLocaleString("en-GB")}
                </strong>
              </div>
              <div className="month-stat">
                <span className="month-stat-label">Daily average</span>
                <strong>
                  {Math.round(log?.average_consumed ?? 0).toLocaleString(
                    "en-GB",
                  )}
                </strong>
              </div>
              <div className="month-stat">
                <span className="month-stat-label">Days over goal</span>
                <strong>{log?.days_over_goal ?? 0}</strong>
              </div>
            </div>

            <div className="weekday-row" aria-hidden="true">
              {WEEKDAYS.map((weekday) => (
                <span key={weekday}>{weekday}</span>
              ))}
            </div>

            <div className="calendar-grid">
              {cells.map((iso, index) => {
                if (!iso) {
                  return (
                    <span
                      key={`blank-${index}`}
                      className="day-cell day-blank"
                      aria-hidden="true"
                    />
                  );
                }

                const day = byDate.get(iso);
                const isToday = iso === today;
                const isSelected = iso === selectedDate;
                const hasEntries = Boolean(day && day.entries > 0);
                const isDone = Boolean(day?.done);
                const isOver = hasEntries && day ? day.consumed > goal : false;

                const classes = [
                  "day-cell",
                  hasEntries ? "is-logged" : "",
                  isOver ? "is-over" : "",
                  isDone ? "is-done" : "",
                  isToday ? "is-today" : "",
                  isSelected ? "is-selected" : "",
                ]
                  .filter(Boolean)
                  .join(" ");

                const label =
                  day && day.entries > 0
                    ? `${formatShortDate(iso)}: ${day.consumed.toLocaleString(
                        "en-GB",
                      )} kcal across ${day.entries} ${
                        day.entries === 1 ? "entry" : "entries"
                      }${isDone ? ", marked done" : ""}`
                    : isDone
                      ? `${formatShortDate(iso)}: marked done`
                      : `${formatShortDate(iso)}: no food logged`;

                return (
                  <button
                    key={iso}
                    type="button"
                    className={classes}
                    title={label}
                    aria-label={`Open ${label}`}
                    onClick={() => onOpenDay(iso)}
                  >
                    <span className="day-num">{dayNumber(iso)}</span>
                    {day && day.entries > 0 ? (
                      <span className="day-kcal">
                        {day.consumed.toLocaleString("en-GB")}
                      </span>
                    ) : (
                      <span className="day-kcal is-empty">—</span>
                    )}
                    {hasEntries && (
                      <span className="day-dot" aria-hidden="true" />
                    )}
                    {isDone && (
                      <span className="day-check" aria-hidden="true">
                        ✓
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            <div className="calendar-legend">
              <span>
                <i className="legend-dot is-logged" aria-hidden="true" />
                Logged
              </span>
              <span>
                <i className="legend-dot is-over" aria-hidden="true" />
                Over goal
              </span>
              <span>
                <i className="legend-dot is-done" aria-hidden="true">
                  ✓
                </i>
                Day done
              </span>
              <span>
                <i className="legend-dot is-today" aria-hidden="true" />
                Today
              </span>
            </div>

            <p className="calendar-hint">
              Goal for this month: {goal.toLocaleString("en-GB")} kcal per day
              {log?.goal_source === "profile"
                ? " — estimated from your profile."
                : " — default target until you complete your profile."}
            </p>
          </>
        )}
      </section>
    </>
  );
}
