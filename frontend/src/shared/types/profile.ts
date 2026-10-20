export type Sex = "male" | "female" | "other";
export type ActivityLevel =
  | "sedentary"
  | "light"
  | "moderate"
  | "active"
  | "very_active";
export type Tone = "green" | "orange" | "red";

export interface Profile {
  id: number;
  name: string;
  age: number;
  sex: Sex;
  height_cm: number;
  weight_kg: number;
  activity_level: ActivityLevel;
  version: number;
  bmi: number;
  category: string;
  tone: Tone;
  healthy_weight_min_kg: number;
  healthy_weight_max_kg: number;
  created_at: string;
  updated_at: string;
}

export interface ProfileEnvelope {
  profile: Profile | null;
}

export interface ProfileInput {
  name: string;
  age: number;
  sex: Sex;
  height_cm: number;
  weight_kg: number;
  activity_level: ActivityLevel;
  version: number;
}

export const SEX_OPTIONS: { value: Sex; label: string }[] = [
  { value: "male", label: "Male" },
  { value: "female", label: "Female" },
  { value: "other", label: "Other" },
];

export const ACTIVITY_OPTIONS: { value: ActivityLevel; label: string }[] = [
  { value: "sedentary", label: "Sedentary - little movement" },
  { value: "light", label: "Light - 1-2 workouts a week" },
  { value: "moderate", label: "Moderate - 3-4 workouts a week" },
  { value: "active", label: "Active - 5-6 workouts a week" },
  { value: "very_active", label: "Very active - daily training" },
];
