import type {
  PhotoMealAnalyzeInput,
  PhotoMealConfig,
  PhotoMealJob,
} from "../types";
import { request } from "./client";

export function getPhotoMealConfig(): Promise<PhotoMealConfig> {
  return request<PhotoMealConfig>("/photo-meals/config");
}

export function listPhotoMeals(limit = 10): Promise<PhotoMealJob[]> {
  return request<PhotoMealJob[]>(`/photo-meals?limit=${limit}`);
}

export function getPhotoMeal(jobId: number): Promise<PhotoMealJob> {
  return request<PhotoMealJob>(`/photo-meals/${jobId}`);
}

export function analyzePhotoMeal(
  input: PhotoMealAnalyzeInput,
): Promise<PhotoMealJob> {
  const body = new FormData();
  body.set("date", input.date);
  body.set("meal", input.meal);
  body.set("image", input.image, input.image.name || "meal.jpg");
  return request<PhotoMealJob>("/photo-meals/analyze", {
    method: "POST",
    body,
  });
}
