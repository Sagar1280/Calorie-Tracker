import type { Tone } from "@/shared/types";

export const BMI_SCALE_MIN = 14;
export const BMI_SCALE_MAX = 40;

export type BmiCategory = "Underweight" | "Healthy" | "Overweight" | "Obese";

export interface BmiSummary {
  bmi: number;
  category: BmiCategory;
  tone: Tone;
  healthyMin: number;
  healthyMax: number;
  position: number;
  headline: string;
  detail: string;
}

const round1 = (value: number) => Math.round(value * 10) / 10;

const formatKg = (value: number) => {
  const rounded = round1(Math.max(0, value));
  return rounded < 0.1 ? "0.1" : rounded.toFixed(1);
};

export function summarizeBmi(
  weightKg: number,
  heightCm: number,
): BmiSummary | null {
  if (
    !Number.isFinite(weightKg) ||
    !Number.isFinite(heightCm) ||
    weightKg < 10 ||
    weightKg > 500 ||
    heightCm <= 50 ||
    heightCm > 260
  ) {
    return null;
  }

  const heightM = heightCm / 100;
  const rawBmi = weightKg / (heightM * heightM);
  const bmi = round1(rawBmi);
  const healthyMin = round1(18.5 * heightM * heightM);
  const healthyMax = round1(24.9 * heightM * heightM);

  let category: BmiCategory;
  let tone: Tone;
  let headline: string;
  let detail: string;

  if (rawBmi < 18.5) {
    category = "Underweight";
    tone = "orange";
    headline = "Below the healthy band";
    detail = `You're about ${formatKg(healthyMin - weightKg)} kg below the healthy range. A gradual gain would move you into the green.`;
  } else if (rawBmi < 25) {
    category = "Healthy";
    tone = "green";
    headline = "In the healthy band";
    detail = "You're in the green. Keeping your routine steady is the goal.";
  } else if (rawBmi < 30) {
    category = "Overweight";
    tone = "orange";
    headline = "Above the healthy band";
    detail = `You're about ${formatKg(weightKg - healthyMax)} kg above the healthy range. Small, steady changes go a long way.`;
  } else {
    category = "Obese";
    tone = "red";
    headline = "Well above the healthy band";
    detail = `You're about ${formatKg(weightKg - healthyMax)} kg above the healthy range. Start with one small change you can repeat.`;
  }

  const position = Math.min(
    98.5,
    Math.max(
      1.5,
      ((rawBmi - BMI_SCALE_MIN) / (BMI_SCALE_MAX - BMI_SCALE_MIN)) * 100,
    ),
  );

  return {
    bmi,
    category,
    tone,
    healthyMin,
    healthyMax,
    position,
    headline,
    detail,
  };
}
