export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const MONTH_KEY_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

export function toISODate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function toMonthKey(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  return `${year}-${month}`;
}

export function todayISO(): string {
  return toISODate(new Date());
}

export function isValidISODate(value: string | null | undefined): value is string {
  if (!value || !ISO_DATE_PATTERN.test(value)) return false;
  return toISODate(parseISODate(value)) === value;
}

export function isValidMonthKey(
  value: string | null | undefined,
): value is string {
  return Boolean(value && MONTH_KEY_PATTERN.test(value));
}

export function parseISODate(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day, 12);
}

export function shiftISO(iso: string, days: number): string {
  const date = parseISODate(iso);
  date.setDate(date.getDate() + days);
  return toISODate(date);
}

export function dayLabel(iso: string): string {
  const today = todayISO();
  if (iso === today) return "Today";
  if (iso === shiftISO(today, -1)) return "Yesterday";
  if (iso === shiftISO(today, 1)) return "Tomorrow";
  return parseISODate(iso).toLocaleDateString("en-GB", {
    weekday: "long",
  });
}

export function formatLongDate(iso: string): string {
  return parseISODate(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function formatShortDate(iso: string): string {
  return parseISODate(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
  });
}

export function formatMonthYear(year: number, month: number): string {
  return new Date(year, month - 1, 1, 12).toLocaleDateString("en-GB", {
    month: "long",
    year: "numeric",
  });
}

export function monthCells(year: number, month: number): (string | null)[] {
  const first = new Date(year, month - 1, 1, 12);
  const offset = (first.getDay() + 6) % 7;
  const daysInMonth = new Date(year, month, 0, 12).getDate();

  const cells: (string | null)[] = Array.from({ length: offset }, () => null);
  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push(toISODate(new Date(year, month - 1, day, 12)));
  }
  while (cells.length % 7 !== 0) cells.push(null);

  return cells;
}

export function dayNumber(iso: string): number {
  return parseISODate(iso).getDate();
}
