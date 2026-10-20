import math
import os
import re
import threading
import time
from dataclasses import dataclass

import httpx

OFF_PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
OFF_FIELDS = (
    "code,product_name,generic_name,brands,quantity,"
    "product_quantity,product_quantity_unit,nutriments"
)
OFF_USER_AGENT = "CalorieTracker/0.2 (local development)"
OFF_TIMEOUT_SECONDS = float(os.getenv("OFF_TIMEOUT_SECONDS", "8"))
OFF_CACHE_TTL_SECONDS = int(os.getenv("OFF_CACHE_TTL_SECONDS", "600"))
OFF_NEGATIVE_CACHE_TTL_SECONDS = int(
    os.getenv("OFF_NEGATIVE_CACHE_TTL_SECONDS", "300")
)

_MISSING = object()
_off_cache: dict[str, tuple[float, "OffProduct | None"]] = {}
_off_cache_lock = threading.Lock()

_MULTIPACK_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b",
    re.IGNORECASE,
)
_SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b", re.IGNORECASE)


class OpenFoodFactsError(Exception):
    pass


@dataclass(frozen=True)
class OffProduct:
    barcode: str
    name: str
    brand: str | None
    kcal: int
    protein_g: float
    carbs_g: float
    fat_g: float
    pack_amount: float | None = None
    pack_unit: str | None = None


def _number(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _macro(nutriments: dict[str, object], key: str) -> float:
    value = _number(nutriments.get(key))
    if value is None:
        return 0.0
    return round(min(value, 1000.0), 1)


def _energy_kcal(nutriments: dict[str, object]) -> int | None:
    kcal = _number(nutriments.get("energy-kcal_100g"))
    if kcal is None:
        kilojoules = _number(nutriments.get("energy-kj_100g"))
        if kilojoules is None:
            kilojoules = _number(nutriments.get("energy_100g"))
        if kilojoules is not None:
            kcal = kilojoules / 4.184
    if kcal is None or kcal <= 0 or kcal > 1000:
        return None
    return round(kcal)


def _convert_size(amount: float, unit: str) -> tuple[float, str] | None:
    normalized = unit.lower()
    if normalized == "kg":
        amount, normalized = amount * 1000, "g"
    elif normalized == "l":
        amount, normalized = amount * 1000, "ml"
    if normalized not in {"g", "ml"}:
        return None
    if amount <= 0 or amount > 10000:
        return None
    return amount, normalized


def _parse_size(value: object) -> tuple[float, str] | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None

    multipack = _MULTIPACK_RE.search(text)
    if multipack:
        count = _number(multipack.group(1))
        amount = _number(multipack.group(2))
        if count is not None and amount is not None:
            converted = _convert_size(count * amount, multipack.group(3))
            if converted is not None:
                return converted

    single = _SIZE_RE.search(text)
    if single:
        amount = _number(single.group(1))
        if amount is not None:
            return _convert_size(amount, single.group(2))
    return None


def _pack_size(product: dict[str, object]) -> tuple[float, str] | None:
    amount = _number(product.get("product_quantity"))
    unit = str(product.get("product_quantity_unit") or "").lower()
    if amount is not None and unit in {"g", "ml"}:
        converted = _convert_size(amount, unit)
        if converted is not None:
            return converted
    return _parse_size(product.get("quantity"))


def _clean_text(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _brand_name(value: object) -> str | None:
    text = _clean_text(value, 160)
    if not text:
        return None
    return _clean_text(text.split(",")[0], 80) or None


def _cache_get(barcode: str) -> "OffProduct | None | object":
    now = time.monotonic()
    with _off_cache_lock:
        cached = _off_cache.get(barcode)
        if cached is None:
            return _MISSING
        expires_at, product = cached
        if expires_at <= now:
            _off_cache.pop(barcode, None)
            return _MISSING
        return product


def _cache_put(barcode: str, product: "OffProduct | None") -> None:
    ttl = OFF_CACHE_TTL_SECONDS if product else OFF_NEGATIVE_CACHE_TTL_SECONDS
    if ttl <= 0:
        return
    with _off_cache_lock:
        _off_cache[barcode] = (time.monotonic() + ttl, product)


def clear_off_cache() -> None:
    with _off_cache_lock:
        _off_cache.clear()


async def lookup_off_product(barcode: str) -> OffProduct | None:
    cached = _cache_get(barcode)
    if cached is not _MISSING:
        return cached
    product = await _fetch_off_product(barcode)
    _cache_put(barcode, product)
    return product


async def _fetch_off_product(barcode: str) -> OffProduct | None:
    url = OFF_PRODUCT_URL.format(barcode=barcode)
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(OFF_TIMEOUT_SECONDS, connect=3.0),
            follow_redirects=True,
            headers={"User-Agent": OFF_USER_AGENT},
        ) as client:
            response = await client.get(url, params={"fields": OFF_FIELDS})
    except httpx.HTTPError as exc:
        raise OpenFoodFactsError("Open Food Facts could not be reached.") from exc

    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise OpenFoodFactsError(
            f"Open Food Facts returned status {response.status_code}."
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise OpenFoodFactsError("Open Food Facts returned invalid JSON.") from exc

    if not isinstance(payload, dict):
        return None
    if str(payload.get("status")) != "1":
        return None

    product = payload.get("product")
    if not isinstance(product, dict):
        return None

    brand = _brand_name(product.get("brands"))
    product_name = _clean_text(product.get("product_name"), 160)
    generic_name = _clean_text(product.get("generic_name"), 160)
    name = product_name or generic_name
    if brand and generic_name and len(product_name.split()) <= 1:
        name = _clean_text(f"{brand} {generic_name}", 160)
    if not name:
        return None

    nutriments = product.get("nutriments")
    if not isinstance(nutriments, dict):
        return None

    kcal = _energy_kcal(nutriments)
    if kcal is None:
        return None

    pack = _pack_size(product)

    return OffProduct(
        barcode=barcode,
        name=name,
        brand=brand,
        kcal=kcal,
        protein_g=_macro(nutriments, "proteins_100g"),
        carbs_g=_macro(nutriments, "carbohydrates_100g"),
        fat_g=_macro(nutriments, "fat_100g"),
        pack_amount=pack[0] if pack else None,
        pack_unit=pack[1] if pack else None,
    )
