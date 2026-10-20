import type {
  AdminFoodReview,
  AdminFoodUpdateInput,
  FoodDetail,
  FoodList,
} from "../types";
import { request } from "./client";

export function listReviewFoods(params: {
  q?: string;
  source?: "all" | "off" | "curated";
  limit?: number;
  offset?: number;
}): Promise<FoodList> {
  const query = new URLSearchParams({ is_verified: "false" });
  if (params.source && params.source !== "all") {
    query.set("source", params.source);
  }
  if (params.q) query.set("q", params.q);
  if (params.limit != null) query.set("limit", String(params.limit));
  if (params.offset != null) query.set("offset", String(params.offset));
  return request<FoodList>(`/admin/foods?${query.toString()}`);
}

export function listFoodReviews(foodId: number): Promise<AdminFoodReview[]> {
  return request<{ items: AdminFoodReview[] }>(
    `/admin/foods/${foodId}/reviews`,
  ).then((payload) => payload.items);
}

export function updateReviewFood(
  foodId: number,
  input: AdminFoodUpdateInput,
): Promise<FoodDetail> {
  return request<FoodDetail>(`/admin/foods/${foodId}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}
