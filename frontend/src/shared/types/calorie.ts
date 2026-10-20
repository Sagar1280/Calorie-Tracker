import type { EntryUnit, FoodUnit } from "./food";

export type Meal = "breakfast" | "lunch" | "dinner" | "snack";
export type GoalSource = "profile" | "default";

export const MEAL_OPTIONS: { value: Meal; label: string }[] = [
  { value: "breakfast", label: "Breakfast" },
  { value: "lunch", label: "Lunch" },
  { value: "dinner", label: "Dinner" },
  { value: "snack", label: "Snacks" },
];

export interface CalorieEntry {
  id: number;
  date: string;
  meal: Meal;
  name: string;
  calories: number;
  variant_id: number | null;
  quantity: number | null;
  unit: FoodUnit | null;
  protein_g: number | null;
  fat_g: number | null;
  created_at: string;
}

export interface CalorieEntryInput {
  date: string;
  meal: Meal;
  name?: string;
  calories?: number;
  variant_id?: number;
  quantity?: number;
  unit?: EntryUnit;
}

export interface DayLog {
  date: string;
  goal: number;
  goal_source: GoalSource;
  consumed: number;
  remaining: number;
  done: boolean;
  protein_goal_g: number;
  fat_goal_g: number;
  water_goal_ml: number;
  protein_consumed_g: number;
  fat_consumed_g: number;
  entries: CalorieEntry[];
}

export interface DayDoneInput {
  date: string;
  done: boolean;
}

export interface MonthDay {
  date: string;
  consumed: number;
  entries: number;
  done: boolean;
}

export interface MonthLog {
  year: number;
  month: number;
  goal: number;
  goal_source: GoalSource;
  days: MonthDay[];
  total_consumed: number;
  days_logged: number;
  average_consumed: number;
  days_over_goal: number;
}
