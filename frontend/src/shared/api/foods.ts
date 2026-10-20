import type { FoodDetail, FoodList } from "../types";
import { request } from "./client";

export interface FoodSearchParams {
  q?: string;
  category?: string;
  brand?: string;
  tag?: string;
  limit?: number;
  offset?: number;
}

export function searchFoods(params: FoodSearchParams): Promise<FoodList> {
  const query = new URLSearchParams();
  if (params.q) query.set("q", params.q);
  if (params.category) query.set("category", params.category);
  if (params.brand) query.set("brand", params.brand);
  if (params.tag) query.set("tag", params.tag);
  if (params.limit != null) query.set("limit", String(params.limit));
  if (params.offset != null) query.set("offset", String(params.offset));
  return request<FoodList>(`/foods?${query.toString()}`);
}

export function getFood(foodId: number): Promise<FoodDetail> {
  return request<FoodDetail>(`/foods/${foodId}`);
}

export function resolveBarcode(barcode: string): Promise<FoodDetail> {
  return request<FoodDetail>("/foods/barcode/resolve", {
    method: "POST",
    body: JSON.stringify({ barcode }),
  });
}
