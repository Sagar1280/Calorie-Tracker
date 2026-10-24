import type {
  AdminBulkAction,
  AdminBulkResult,
  AdminFoodCreateInput,
  AdminFoodReview,
  AdminFoodUpdateInput,
  FoodDetail,
  FoodList,
  FoodStatus,
} from "../types";
import { request } from "./client";

function adminHeaders(password: string): HeadersInit {
  return { "X-Admin-Password": password };
}

export function listReviewFoods(params: {
  q?: string;
  source?: "all" | "off" | "curated" | "user";
  status?: FoodStatus;
  isVerified?: boolean;
  limit?: number;
  offset?: number;
}): Promise<FoodList> {
  const query = new URLSearchParams();
  if (params.status) {
    query.set("status", params.status);
  }
  if (params.isVerified != null) {
    query.set("is_verified", String(params.isVerified));
  }
  if (params.source && params.source !== "all") {
    query.set("source", params.source);
  }
  if (params.q) query.set("q", params.q);
  if (params.limit != null) query.set("limit", String(params.limit));
  if (params.offset != null) query.set("offset", String(params.offset));
  return request<FoodList>(`/admin/foods?${query.toString()}`);
}

export function createReviewFood(
  input: AdminFoodCreateInput,
  password: string,
): Promise<FoodDetail> {
  return request<FoodDetail>("/admin/foods", {
    method: "POST",
    headers: adminHeaders(password),
    body: JSON.stringify(input),
  });
}

export function listFoodReviews(foodId: number): Promise<AdminFoodReview[]> {
  return request<{ items: AdminFoodReview[] }>(
    `/admin/foods/${foodId}/reviews`,
  ).then((payload) => payload.items);
}

export function updateReviewFood(
  foodId: number,
  input: AdminFoodUpdateInput,
  password: string,
): Promise<FoodDetail> {
  return request<FoodDetail>(`/admin/foods/${foodId}`, {
    method: "PUT",
    headers: adminHeaders(password),
    body: JSON.stringify(input),
  });
}

export function bulkReviewFoods(
  input: {
    ids: number[];
    action: AdminBulkAction;
    review_note?: string | null;
  },
  password: string,
): Promise<AdminBulkResult> {
  return request<AdminBulkResult>("/admin/foods/bulk", {
    method: "POST",
    headers: adminHeaders(password),
    body: JSON.stringify(input),
  });
}

export function deleteReviewFood(
  foodId: number,
  password: string,
): Promise<void> {
  return request<void>(`/admin/foods/${foodId}`, {
    method: "DELETE",
    headers: adminHeaders(password),
  });
}
