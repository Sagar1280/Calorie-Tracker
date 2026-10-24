export type FoodUnit = "g" | "ml";
export type EntryUnit = FoodUnit | "pack";
export type VariantState = "raw" | "cooked" | "as_sold";
export type FoodStatus = "approved" | "pending" | "rejected" | "private";

export interface FoodTag {
  key: string;
  label: string;
  type: string;
}

export interface FoodBrand {
  id: number;
  name: string;
  slug: string;
}

export interface FoodServing {
  id: number;
  label: string;
  amount: number;
  unit: FoodUnit;
  is_default: boolean;
}

export interface FoodVariant {
  id: number;
  state: VariantState;
  label: string;
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  base_amount: number;
  base_unit: FoodUnit;
  is_default: boolean;
  servings: FoodServing[];
}

export interface FoodSummary {
  id: number;
  slug: string;
  name: string;
  category: string;
  subcategory: string | null;
  brand: FoodBrand | null;
  base_unit: FoodUnit;
  region: string | null;
  source: string;
  status: string;
  is_verified: boolean;
  tags: FoodTag[];
  default_variant: FoodVariant | null;
}

export interface FoodBarcode {
  id: number;
  barcode: string;
  pack_amount: number | null;
  pack_unit: FoodUnit | null;
  source: string;
  variant_id: number | null;
}

export interface FoodDetail extends FoodSummary {
  description: string | null;
  variants: FoodVariant[];
  aliases: string[];
  barcodes: FoodBarcode[];
}

export interface FoodList {
  items: FoodSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface BarcodeScanResult {
  barcode: string;
  status: "database" | "review" | "queued";
  food: FoodDetail;
}
