/* @vitest-environment jsdom */
import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getCalorieMonth } from "@/shared/api";
import { todayISO } from "@/shared/lib";
import CalendarView from "./CalendarView";

vi.mock("@/shared/api", () => ({
  ApiError: class ApiError extends Error {
    status: number;

    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  getCalorieMonth: vi.fn(),
}));

const mockedGetCalorieMonth = vi.mocked(getCalorieMonth);

function renderCalendar(overrides?: {
  onMonthChange?: (month: string) => void;
  onOpenDay?: (iso: string) => void;
}) {
  const onMonthChange = overrides?.onMonthChange ?? vi.fn();
  const onOpenDay = overrides?.onOpenDay ?? vi.fn();

  render(
    <CalendarView
      selectedDate="2026-09-15"
      monthKey="2026-09"
      onMonthChange={onMonthChange}
      onOpenDay={onOpenDay}
      onSessionExpired={vi.fn()}
    />,
  );

  return { onMonthChange, onOpenDay };
}

describe("calendar month navigation", () => {
  afterEach(cleanup);

  it("requests adjacent months and today through the router callback", async () => {
    mockedGetCalorieMonth.mockResolvedValue({
      days: [],
      days_logged: 0,
      total_consumed: 0,
      average_consumed: 0,
      days_over_goal: 0,
    } as never);
    const { onMonthChange } = renderCalendar();

    await screen.findByText("September 2026");
    expect(mockedGetCalorieMonth).toHaveBeenCalledWith(2026, 9);

    fireEvent.click(screen.getByRole("button", { name: "Next month" }));
    expect(onMonthChange).toHaveBeenCalledWith("2026-10");

    fireEvent.click(screen.getByRole("button", { name: "Previous month" }));
    expect(onMonthChange).toHaveBeenCalledWith("2026-08");

    fireEvent.click(screen.getByRole("button", { name: "Today" }));
    expect(onMonthChange).toHaveBeenCalledWith(todayISO().slice(0, 7));
  });

  it("opens the selected day through the router callback", async () => {
    mockedGetCalorieMonth.mockResolvedValue({
      days: [],
      days_logged: 0,
      total_consumed: 0,
      average_consumed: 0,
      days_over_goal: 0,
    } as never);
    const { onOpenDay } = renderCalendar();

    await screen.findByText("September 2026");
    fireEvent.click(
      screen.getAllByRole("button", { name: /^Open / })[14],
    );

    expect(onOpenDay).toHaveBeenCalledWith("2026-09-15");
  });
});
