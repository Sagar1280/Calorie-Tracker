import type { Meal } from "./calorie";

export type PhotoMealStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed";

export interface PhotoMealItem {
  name: string;
  portion_g: number;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  confidence: number;
  matched: boolean;
  food_id: number | null;
}

export interface PhotoMealJob {
  id: number;
  date: string;
  meal: Meal;
  status: PhotoMealStatus;
  items: PhotoMealItem[];
  entry_ids: number[];
  error: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface PhotoMealConfig {
  enabled: boolean;
  model: string;
}

export interface PhotoMealAnalyzeInput {
  date: string;
  meal: Meal;
  image: File;
}
