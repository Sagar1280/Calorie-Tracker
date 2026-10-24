import { describe, expect, it } from "vitest";
import type { BarcodeScanResult } from "../types";
import {
  BARCODE_CACHE_TTL_MS,
  BARCODE_QUEUED_TTL_MS,
  type BarcodeCacheEntry,
  readBarcodeCache,
  writeBarcodeCache,
} from "./barcodeCache";

function result(status: BarcodeScanResult["status"]): BarcodeScanResult {
  return {
    barcode: "1234567890123",
    status,
    food: {} as BarcodeScanResult["food"],
  };
}

describe("barcode cache", () => {
  it("returns cached results within the TTL", () => {
    const cache = new Map<string, BarcodeCacheEntry>();
    const database = result("database");
    writeBarcodeCache(cache, "1234567890123", database, 1_000);

    expect(readBarcodeCache(cache, "1234567890123", 1_000)).toBe(database);
    expect(
      readBarcodeCache(
        cache,
        "1234567890123",
        1_000 + BARCODE_CACHE_TTL_MS - 1,
      ),
    ).toBe(database);
  });

  it("expires database results after the standard TTL", () => {
    const cache = new Map<string, BarcodeCacheEntry>();
    writeBarcodeCache(cache, "1234567890123", result("database"), 1_000);

    expect(
      readBarcodeCache(cache, "1234567890123", 1_000 + BARCODE_CACHE_TTL_MS),
    ).toBeUndefined();
    expect(cache.size).toBe(0);
  });

  it("expires queued results after the short TTL", () => {
    const cache = new Map<string, BarcodeCacheEntry>();
    writeBarcodeCache(cache, "1234567890123", result("queued"), 1_000);

    expect(
      readBarcodeCache(
        cache,
        "1234567890123",
        1_000 + BARCODE_QUEUED_TTL_MS - 1,
      )?.status,
    ).toBe("queued");
    expect(
      readBarcodeCache(cache, "1234567890123", 1_000 + BARCODE_QUEUED_TTL_MS),
    ).toBeUndefined();
  });

  it("ignores missing entries and replaces stale ones", () => {
    const cache = new Map<string, BarcodeCacheEntry>();
    expect(readBarcodeCache(cache, "9999999999999", 1_000)).toBeUndefined();

    writeBarcodeCache(cache, "1234567890123", result("queued"), 1_000);
    const review = result("review");
    writeBarcodeCache(cache, "1234567890123", review, 2_000);

    expect(readBarcodeCache(cache, "1234567890123", 2_000)).toBe(review);
  });
});
