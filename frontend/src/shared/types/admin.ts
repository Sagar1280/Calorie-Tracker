import type { FoodStatus, FoodUnit } from "./food";

export interface AdminVariantUpdateInput {
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  base_amount: number;
  base_unit: FoodUnit;
}

export interface AdminFoodUpdateInput {
  name: string;
  category: string;
  subcategory: string | null;
  brand_name: string | null;
  description: string | null;
  status: FoodStatus;
  is_verified: boolean;
  review_note: string | null;
  variant: AdminVariantUpdateInput;
}

export type AdminReviewAction = "updated" | "approved" | "rejected";

export interface AdminFoodReview {
  id: number;
  action: AdminReviewAction;
  status: string;
  is_verified: boolean;
  note: string | null;
  reviewer_username: string | null;
  created_at: string;
}
