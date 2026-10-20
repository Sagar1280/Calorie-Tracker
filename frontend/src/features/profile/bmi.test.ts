import { describe, expect, it } from "vitest";
import { summarizeBmi } from "./bmi";

describe("summarizeBmi", () => {
  it("rejects invalid measurements", () => {
    expect(summarizeBmi(0, 175)).toBeNull();
    expect(summarizeBmi(70, 0)).toBeNull();
    expect(summarizeBmi(Number.NaN, 175)).toBeNull();
    expect(summarizeBmi(70, Number.POSITIVE_INFINITY)).toBeNull();
  });

  it("classifies a healthy BMI", () => {
    const summary = summarizeBmi(70, 175);
    expect(summary).not.toBeNull();
    expect(summary?.category).toBe("Healthy");
    expect(summary?.tone).toBe("green");
    expect(summary?.bmi).toBeCloseTo(22.9, 1);
    expect(summary?.healthyMin).toBeCloseTo(56.7, 1);
    expect(summary?.healthyMax).toBeCloseTo(76.3, 1);
  });

  it("classifies underweight and obese ranges", () => {
    expect(summarizeBmi(50, 175)?.category).toBe("Underweight");
    expect(summarizeBmi(50, 175)?.tone).toBe("orange");
    expect(summarizeBmi(100, 175)?.category).toBe("Obese");
    expect(summarizeBmi(100, 175)?.tone).toBe("red");
  });

  it("keeps the scale marker inside the visible range", () => {
    const low = summarizeBmi(30, 200);
    const high = summarizeBmi(200, 160);
    expect(low?.position).toBeGreaterThanOrEqual(1.5);
    expect(high?.position).toBeLessThanOrEqual(98.5);
  });
});
