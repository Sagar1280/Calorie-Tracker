import type {
  CalorieEntry,
  CalorieEntryInput,
  DayDoneInput,
  DayLog,
  MonthLog,
} from "../types";
import { request } from "./client";

export function getCalorieDay(date: string): Promise<DayLog> {
  return request<DayLog>(`/calories/day?date=${encodeURIComponent(date)}`);
}

export function getCalorieMonth(year: number, month: number): Promise<MonthLog> {
  return request<MonthLog>(`/calories/month?year=${year}&month=${month}`);
}

export function setCalorieDayDone(input: DayDoneInput): Promise<DayLog> {
  return request<DayLog>("/calories/day/done", {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function addCalorieEntry(
  input: CalorieEntryInput,
): Promise<CalorieEntry> {
  return request<CalorieEntry>("/calories/entries", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function deleteCalorieEntry(entryId: number): Promise<void> {
  return request<void>(`/calories/entries/${entryId}`, { method: "DELETE" });
}
