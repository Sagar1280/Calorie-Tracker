import type { BarcodeScanResult } from "../types";

export const BARCODE_CACHE_TTL_MS = 5 * 60 * 1000;
export const BARCODE_QUEUED_TTL_MS = 30 * 1000;

export interface BarcodeCacheEntry {
  at: number;
  result: BarcodeScanResult;
}

export type BarcodeCache = Map<string, BarcodeCacheEntry>;

export function readBarcodeCache(
  cache: BarcodeCache,
  barcode: string,
  now = Date.now(),
): BarcodeScanResult | undefined {
  const entry = cache.get(barcode);
  if (!entry) return undefined;

  const ttl =
    entry.result.status === "queued"
      ? BARCODE_QUEUED_TTL_MS
      : BARCODE_CACHE_TTL_MS;
  if (now - entry.at >= ttl) {
    cache.delete(barcode);
    return undefined;
  }
  return entry.result;
}

export function writeBarcodeCache(
  cache: BarcodeCache,
  barcode: string,
  result: BarcodeScanResult,
  now = Date.now(),
): void {
  cache.set(barcode, { at: now, result });
}
