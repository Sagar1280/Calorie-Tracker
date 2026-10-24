import { describe, expect, it } from "vitest";
import {
  dayLabel,
  dayNumber,
  formatMonthYear,
  isValidISODate,
  isValidMonthKey,
  monthCells,
  shiftISO,
  toMonthKey,
  todayISO,
} from "./dates";

describe("date helpers", () => {
  it("formats today as an ISO date", () => {
    expect(todayISO()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("shifts across month and year boundaries", () => {
    expect(shiftISO("2026-01-31", 1)).toBe("2026-02-01");
    expect(shiftISO("2026-03-01", -1)).toBe("2026-02-28");
    expect(shiftISO("2026-12-31", 1)).toBe("2027-01-01");
  });

  it("labels relative days", () => {
    expect(dayLabel(todayISO())).toBe("Today");
    expect(dayLabel(shiftISO(todayISO(), -1))).toBe("Yesterday");
    expect(dayLabel(shiftISO(todayISO(), 1))).toBe("Tomorrow");
  });

  it("builds a seven-column month grid", () => {
    const cells = monthCells(2024, 2);
    expect(cells.length % 7).toBe(0);
    expect(cells.filter(Boolean)).toHaveLength(29);
    expect(cells.filter(Boolean)[0]).toBe("2024-02-01");
  });

  it("formats month names and day numbers", () => {
    expect(formatMonthYear(2024, 2)).toContain("February 2024");
    expect(dayNumber("2024-02-29")).toBe(29);
  });

  it("validates URL date and month values", () => {
    expect(isValidISODate("2026-10-24")).toBe(true);
    expect(isValidISODate("2026-02-30")).toBe(false);
    expect(isValidISODate("2026-1-01")).toBe(false);
    expect(isValidISODate(null)).toBe(false);
    expect(isValidMonthKey("2026-10")).toBe(true);
    expect(isValidMonthKey("2026-13")).toBe(false);
    expect(isValidMonthKey("2026-1")).toBe(false);
  });

  it("builds a month key", () => {
    expect(toMonthKey(new Date(2026, 9, 24, 12))).toBe("2026-10");
  });
});
