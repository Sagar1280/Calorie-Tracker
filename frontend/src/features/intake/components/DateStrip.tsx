import { dayLabel, formatLongDate, shiftISO, todayISO } from "@/shared/lib";

interface DateStripProps {
  date: string;
  onDateChange: (iso: string) => void;
}

export default function DateStrip({ date, onDateChange }: DateStripProps) {
  return (
    <section className="date-strip" aria-label="Choose a day">
      <button
        type="button"
        className="date-arrow"
        aria-label="Previous day"
        onClick={() => onDateChange(shiftISO(date, -1))}
      >
        ‹
      </button>
      <div className="date-center">
        <span className="date-relative">{dayLabel(date)}</span>
        <span className="date-full">{formatLongDate(date)}</span>
      </div>
      <button
        type="button"
        className="date-arrow"
        aria-label="Next day"
        onClick={() => onDateChange(shiftISO(date, 1))}
      >
        ›
      </button>
      <button
        type="button"
        className="text-button date-jump"
        onClick={() => onDateChange(todayISO())}
        disabled={date === todayISO()}
      >
        Jump to today
      </button>
    </section>
  );
}
