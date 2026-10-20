"""Import curated food data from CSV files.

Expected files in the seed directory:
    foods.csv
    variants.csv
    aliases.csv
    barcodes.csv
    servings.csv

Usage:
    python scripts/import_foods.py
    python scripts/import_foods.py --dir data/seed --dry-run
"""

import argparse
import asyncio
import csv
import re
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import delete, select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import (  # noqa: E402
    Brand,
    Food,
    FoodAlias,
    FoodBarcode,
    FoodTag,
    FoodVariant,
    Serving,
    Tag,
    utc_now,
)
from app.seed import seed_default_tags  # noqa: E402
from app.text import normalize_text, slugify, split_pipe  # noqa: E402

VALID_STATES = {"raw", "cooked", "as_sold"}
VALID_UNITS = {"g", "ml"}
VALID_SOURCES = {"curated", "off", "user"}
VALID_STATUSES = {"approved", "pending", "rejected", "private"}
BARCODE_PATTERN = re.compile(r"^\d{6,14}$")
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ImportErrorWithContext(Exception):
    pass


def read_rows(path: Path, *, optional: bool = False) -> list[dict[str, str]]:
    if not path.exists():
        if optional:
            return []
        raise ImportErrorWithContext(f"Missing file: {path}")

    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, str]] = []
        for line_number, raw in enumerate(reader, start=2):
            if raw is None:
                continue
            row: dict[str, str] = {}
            for key, value in raw.items():
                key = (key or "").strip()
                if not key:
                    raise ImportErrorWithContext(
                        f"{path.name} line {line_number}: row has more columns than the header"
                    )
                if isinstance(value, list):
                    value = ",".join(value)
                row[key] = (value or "").strip()
            if not any(row.values()):
                continue
            row["_line"] = str(line_number)
            rows.append(row)
    return rows


def row_context(row: dict[str, str]) -> str:
    return f"line {row.get('_line', '?')} ({row.get('slug') or row.get('name') or row.get('food_slug') or 'row'})"


def required(row: dict[str, str], field: str) -> str:
    value = row.get(field, "")
    if not value:
        raise ImportErrorWithContext(f"{row_context(row)}: '{field}' is required")
    return value


def parse_float(
    row: dict[str, str], field: str, *, required_value: bool = False
) -> float | None:
    value = row.get(field, "")
    if not value:
        if required_value:
            raise ImportErrorWithContext(
                f"{row_context(row)}: '{field}' is required"
            )
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ImportErrorWithContext(
            f"{row_context(row)}: '{field}' must be a number, got '{value}'"
        ) from exc


def parse_int(
    row: dict[str, str], field: str, *, required_value: bool = False
) -> int | None:
    value = row.get(field, "")
    if not value:
        if required_value:
            raise ImportErrorWithContext(
                f"{row_context(row)}: '{field}' is required"
            )
        return None
    try:
        number = float(value)
    except ValueError as exc:
        raise ImportErrorWithContext(
            f"{row_context(row)}: '{field}' must be a number, got '{value}'"
        ) from exc
    if number != int(number):
        raise ImportErrorWithContext(
            f"{row_context(row)}: '{field}' must be a whole number"
        )
    return int(number)


def parse_bool(row: dict[str, str], field: str, default: bool = False) -> bool:
    value = row.get(field, "").lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "y"}:
        return True
    if value in {"0", "false", "no", "n"}:
        return False
    raise ImportErrorWithContext(
        f"{row_context(row)}: '{field}' must be true/false"
    )


def normalized_slug(row: dict[str, str]) -> str:
    slug = row.get("slug") or slugify(required(row, "name"))
    if not SLUG_PATTERN.match(slug):
        raise ImportErrorWithContext(
            f"{row_context(row)}: slug '{slug}' must use lowercase letters, numbers and hyphens"
        )
    return slug


def load_foods(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    foods: dict[str, dict[str, Any]] = {}
    for row in rows:
        slug = normalized_slug(row)
        if slug in foods:
            raise ImportErrorWithContext(f"{row_context(row)}: duplicate food slug")

        name = required(row, "name")
        category = normalize_text(required(row, "category"))
        base_unit = normalize_text(row.get("base_unit") or "g")
        source = normalize_text(row.get("source") or "curated")
        status = normalize_text(row.get("status") or "approved")

        if base_unit not in VALID_UNITS:
            raise ImportErrorWithContext(
                f"{row_context(row)}: base_unit must be g or ml"
            )
        if source not in VALID_SOURCES:
            raise ImportErrorWithContext(
                f"{row_context(row)}: source must be curated, off or user"
            )
        if status not in VALID_STATUSES:
            raise ImportErrorWithContext(
                f"{row_context(row)}: invalid status '{status}'"
            )

        foods[slug] = {
            "slug": slug,
            "name": name,
            "name_normalized": normalize_text(name),
            "category": category,
            "subcategory": row.get("subcategory") or None,
            "brand": row.get("brand") or None,
            "base_unit": base_unit,
            "region": row.get("region") or None,
            "description": row.get("description") or None,
            "source": source,
            "source_ref": row.get("source_ref") or None,
            "status": status,
            "is_verified": parse_bool(row, "is_verified"),
            "aliases": split_pipe(row.get("aliases")),
            "tags": [normalize_text(tag) for tag in split_pipe(row.get("tags"))],
        }
    return foods


def load_variants(
    rows: list[dict[str, str]], foods: dict[str, dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {slug: [] for slug in foods}
    seen: set[tuple[str, str, str]] = set()

    for row in rows:
        food_slug = required(row, "food_slug")
        if food_slug not in foods:
            raise ImportErrorWithContext(
                f"{row_context(row)}: unknown food_slug '{food_slug}'"
            )

        state = normalize_text(required(row, "state"))
        label = row.get("label") or ""
        if state not in VALID_STATES:
            raise ImportErrorWithContext(
                f"{row_context(row)}: state must be raw, cooked or as_sold"
            )

        key = (food_slug, state, label)
        if key in seen:
            raise ImportErrorWithContext(
                f"{row_context(row)}: duplicate variant {state} '{label}'"
            )
        seen.add(key)

        base_unit = normalize_text(row.get("base_unit") or foods[food_slug]["base_unit"])
        if base_unit not in VALID_UNITS:
            raise ImportErrorWithContext(
                f"{row_context(row)}: base_unit must be g or ml"
            )

        base_amount = parse_float(row, "base_amount")
        if base_amount is None:
            base_amount = 100
        if base_amount <= 0:
            raise ImportErrorWithContext(
                f"{row_context(row)}: base_amount must be positive"
            )

        grouped[food_slug].append(
            {
                "state": state,
                "label": label,
                "kcal": parse_int(row, "kcal", required_value=True),
                "protein_g": parse_float(row, "protein_g", required_value=True),
                "carbs_g": parse_float(row, "carbs_g", required_value=True),
                "fat_g": parse_float(row, "fat_g", required_value=True),
                "base_amount": base_amount,
                "base_unit": base_unit,
                "is_default": parse_bool(row, "is_default"),
            }
        )

    for food_slug, variants in grouped.items():
        if not variants:
            raise ImportErrorWithContext(
                f"Food '{food_slug}' has no variants; add at least one variant row"
            )
        defaults = [variant for variant in variants if variant["is_default"]]
        if len(defaults) > 1:
            raise ImportErrorWithContext(
                f"Food '{food_slug}' has more than one default variant"
            )
        if not defaults:
            variants[0]["is_default"] = True

    return grouped


def load_aliases(
    rows: list[dict[str, str]], foods: dict[str, dict[str, Any]]
) -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {
        slug: list(data["aliases"]) for slug, data in foods.items()
    }
    seen: set[tuple[str, str]] = {
        (slug, normalize_text(alias))
        for slug, values in aliases.items()
        for alias in values
    }

    for row in rows:
        food_slug = required(row, "food_slug")
        if food_slug not in foods:
            raise ImportErrorWithContext(
                f"{row_context(row)}: unknown food_slug '{food_slug}'"
            )
        alias = required(row, "alias")
        normalized = normalize_text(alias)
        if not normalized:
            raise ImportErrorWithContext(
                f"{row_context(row)}: alias cannot be blank"
            )
        key = (food_slug, normalized)
        if key in seen:
            continue
        seen.add(key)
        aliases[food_slug].append(alias)

    return aliases


def load_servings(
    rows: list[dict[str, str]],
    foods: dict[str, dict[str, Any]],
    variants: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    servings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    variants_by_key = {
        food_slug: {
            (variant["state"], variant["label"]) for variant in variant_rows
        }
        for food_slug, variant_rows in variants.items()
    }

    for row in rows:
        food_slug = required(row, "food_slug")
        if food_slug not in foods:
            raise ImportErrorWithContext(
                f"{row_context(row)}: unknown food_slug '{food_slug}'"
            )

        state = normalize_text(row.get("variant_state") or "as_sold")
        variant_label = row.get("variant_label") or ""
        if (state, variant_label) not in variants_by_key[food_slug]:
            raise ImportErrorWithContext(
                f"{row_context(row)}: variant {state} '{variant_label}' does not exist for {food_slug}"
            )

        label = required(row, "label")
        amount = parse_float(row, "amount", required_value=True)
        if amount <= 0:
            raise ImportErrorWithContext(
                f"{row_context(row)}: amount must be positive"
            )

        unit = normalize_text(required(row, "unit"))
        if unit not in VALID_UNITS:
            raise ImportErrorWithContext(
                f"{row_context(row)}: unit must be g or ml"
            )

        key = (food_slug, state, variant_label, label)
        if key in seen:
            raise ImportErrorWithContext(
                f"{row_context(row)}: duplicate serving '{label}'"
            )
        seen.add(key)

        servings.append(
            {
                "food_slug": food_slug,
                "state": state,
                "variant_label": variant_label,
                "label": label,
                "amount": amount,
                "unit": unit,
                "is_default": parse_bool(row, "is_default"),
            }
        )

    return servings


def load_barcodes(
    rows: list[dict[str, str]],
    foods: dict[str, dict[str, Any]],
    variants: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    barcodes: list[dict[str, Any]] = []
    seen: set[str] = set()

    variants_by_key = {
        food_slug: {
            (variant["state"], variant["label"]): variant
            for variant in variant_rows
        }
        for food_slug, variant_rows in variants.items()
    }

    for row in rows:
        food_slug = required(row, "food_slug")
        if food_slug not in foods:
            raise ImportErrorWithContext(
                f"{row_context(row)}: unknown food_slug '{food_slug}'"
            )

        barcode = required(row, "barcode")
        if not BARCODE_PATTERN.match(barcode):
            raise ImportErrorWithContext(
                f"{row_context(row)}: barcode must be 6-14 digits"
            )
        if barcode in seen:
            raise ImportErrorWithContext(
                f"{row_context(row)}: duplicate barcode '{barcode}'"
            )
        seen.add(barcode)

        state = normalize_text(row.get("variant_state") or "as_sold")
        label = row.get("variant_label") or ""
        if (state, label) not in variants_by_key[food_slug]:
            raise ImportErrorWithContext(
                f"{row_context(row)}: variant {state} '{label}' does not exist for {food_slug}"
            )

        pack_unit = normalize_text(row.get("pack_unit") or "") or None
        if pack_unit and pack_unit not in VALID_UNITS:
            raise ImportErrorWithContext(
                f"{row_context(row)}: pack_unit must be g or ml"
            )

        source = normalize_text(row.get("source") or "curated")
        if source not in VALID_SOURCES:
            raise ImportErrorWithContext(
                f"{row_context(row)}: source must be curated, off or user"
            )

        barcodes.append(
            {
                "food_slug": food_slug,
                "state": state,
                "label": label,
                "barcode": barcode,
                "pack_amount": parse_float(row, "pack_amount"),
                "pack_unit": pack_unit,
                "source": source,
            }
        )

    return barcodes


async def apply_import(
    foods: dict[str, dict[str, Any]],
    variants: dict[str, list[dict[str, Any]]],
    aliases: dict[str, list[str]],
    servings: list[dict[str, Any]],
    barcodes: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    counts = {
        "foods_created": 0,
        "foods_updated": 0,
        "variants_created": 0,
        "variants_updated": 0,
        "servings_created": 0,
        "servings_updated": 0,
        "aliases": 0,
        "barcodes_created": 0,
        "barcodes_updated": 0,
        "tags": 0,
    }

    async with SessionLocal() as session:
        tags = {
            tag.key: tag
            for tag in (
                await session.execute(select(Tag))
            ).scalars().all()
        }
        for slug, food_data in foods.items():
            missing = [tag for tag in food_data["tags"] if tag not in tags]
            if missing:
                raise ImportErrorWithContext(
                    f"Food '{slug}' uses unknown tags: {', '.join(missing)}"
                )

        brand_slugs = sorted(
            {
                slugify(food_data["brand"])
                for food_data in foods.values()
                if food_data["brand"]
            }
        )
        brands = {
            brand.slug: brand
            for brand in (
                await session.execute(select(Brand).where(Brand.slug.in_(brand_slugs)))
            ).scalars().all()
        } if brand_slugs else {}

        food_rows = {
            food.slug: food
            for food in (
                await session.execute(
                    select(Food).where(Food.slug.in_(list(foods.keys())))
                )
            ).scalars().all()
        }

        variant_cache: dict[tuple[int, str, str], FoodVariant] = {}
        if food_rows:
            existing_variants = (
                await session.execute(
                    select(FoodVariant).where(
                        FoodVariant.food_id.in_(
                            [food.id for food in food_rows.values()]
                        )
                    )
                )
            ).scalars().all()
            variant_cache = {
                (variant.food_id, variant.state, variant.label): variant
                for variant in existing_variants
            }

        barcode_cache = {
            barcode.barcode: barcode
            for barcode in (
                await session.execute(
                    select(FoodBarcode).where(
                        FoodBarcode.barcode.in_(
                            [row["barcode"] for row in barcodes]
                        )
                    )
                )
            ).scalars().all()
        } if barcodes else {}

        for slug, data in foods.items():
            brand = None
            if data["brand"]:
                brand_slug = slugify(data["brand"])
                brand = brands.get(brand_slug)
                if brand is None:
                    brand = Brand(name=data["brand"], slug=brand_slug)
                    session.add(brand)
                    await session.flush()
                    brands[brand_slug] = brand

            food = food_rows.get(slug)
            if food is not None and food.source == "user" and food.created_by_user_id:
                raise ImportErrorWithContext(
                    f"Food '{slug}' belongs to a user; refusing to overwrite it"
                )

            if food is None:
                food = Food(
                    slug=slug,
                    name=data["name"],
                    name_normalized=data["name_normalized"],
                    category=data["category"],
                    subcategory=data["subcategory"],
                    base_unit=data["base_unit"],
                    region=data["region"],
                    description=data["description"],
                    source=data["source"],
                    source_ref=data["source_ref"],
                    status=data["status"],
                    is_verified=data["is_verified"],
                )
                session.add(food)
                food_rows[slug] = food
                counts["foods_created"] += 1
            else:
                food.name = data["name"]
                food.name_normalized = data["name_normalized"]
                food.category = data["category"]
                food.subcategory = data["subcategory"]
                food.base_unit = data["base_unit"]
                food.region = data["region"]
                food.description = data["description"]
                food.source = data["source"]
                food.source_ref = data["source_ref"]
                food.status = data["status"]
                food.is_verified = data["is_verified"]
                food.updated_at = utc_now()
                counts["foods_updated"] += 1

            food.brand_id = brand.id if brand else None
            await session.flush()

            for variant_data in variants[slug]:
                key = (food.id, variant_data["state"], variant_data["label"])
                variant = variant_cache.get(key)
                if variant is None:
                    variant = FoodVariant(food_id=food.id, **variant_data)
                    session.add(variant)
                    await session.flush()
                    variant_cache[key] = variant
                    counts["variants_created"] += 1
                else:
                    variant.kcal = variant_data["kcal"]
                    variant.protein_g = variant_data["protein_g"]
                    variant.carbs_g = variant_data["carbs_g"]
                    variant.fat_g = variant_data["fat_g"]
                    variant.base_amount = variant_data["base_amount"]
                    variant.base_unit = variant_data["base_unit"]
                    variant.is_default = variant_data["is_default"]
                    counts["variants_updated"] += 1

            await session.execute(
                delete(FoodTag).where(FoodTag.food_id == food.id)
            )
            for tag_key in dict.fromkeys(data["tags"]):
                session.add(FoodTag(food_id=food.id, tag_id=tags[tag_key].id))
                counts["tags"] += 1

            await session.execute(
                delete(FoodAlias).where(FoodAlias.food_id == food.id)
            )
            for alias in aliases.get(slug, []):
                session.add(
                    FoodAlias(
                        food_id=food.id,
                        alias=alias,
                        alias_normalized=normalize_text(alias),
                    )
                )
                counts["aliases"] += 1

        existing_servings = (
            (
                await session.execute(
                    select(Serving).where(
                        Serving.variant_id.in_(
                            [variant.id for variant in variant_cache.values()]
                        )
                    )
                )
            ).scalars().all()
            if variant_cache
            else []
        )
        serving_cache = {
            (serving.variant_id, serving.label): serving
            for serving in existing_servings
        }

        for serving_data in servings:
            food = food_rows.get(serving_data["food_slug"])
            variant = (
                variant_cache.get(
                    (
                        food.id,
                        serving_data["state"],
                        serving_data["variant_label"],
                    )
                )
                if food is not None
                else None
            )
            if variant is None:
                raise ImportErrorWithContext(
                    f"Serving '{serving_data['label']}': variant no longer exists"
                )

            existing = serving_cache.get((variant.id, serving_data["label"]))
            if existing is None:
                existing = Serving(
                    variant_id=variant.id,
                    label=serving_data["label"],
                    amount=serving_data["amount"],
                    unit=serving_data["unit"],
                    is_default=serving_data["is_default"],
                )
                session.add(existing)
                serving_cache[(variant.id, serving_data["label"])] = existing
                counts["servings_created"] += 1
            else:
                existing.amount = serving_data["amount"]
                existing.unit = serving_data["unit"]
                existing.is_default = serving_data["is_default"]
                counts["servings_updated"] += 1

        for barcode_data in barcodes:
            food = food_rows.get(barcode_data["food_slug"])
            if food is None:
                food = (
                    await session.execute(
                        select(Food).where(Food.slug == barcode_data["food_slug"])
                    )
                ).scalar_one()
            variant = variant_cache.get(
                (food.id, barcode_data["state"], barcode_data["label"])
            )
            if variant is None:
                raise ImportErrorWithContext(
                    f"Barcode {barcode_data['barcode']}: variant no longer exists"
                )

            existing = barcode_cache.get(barcode_data["barcode"])
            if existing is not None and existing.food_id != food.id:
                raise ImportErrorWithContext(
                    f"Barcode {barcode_data['barcode']} already belongs to another food"
                )

            if existing is None:
                existing = FoodBarcode(
                    food_id=food.id,
                    variant_id=variant.id,
                    barcode=barcode_data["barcode"],
                    pack_amount=barcode_data["pack_amount"],
                    pack_unit=barcode_data["pack_unit"],
                    source=barcode_data["source"],
                )
                session.add(existing)
                barcode_cache[barcode_data["barcode"]] = existing
                counts["barcodes_created"] += 1
            else:
                existing.variant_id = variant.id
                existing.pack_amount = barcode_data["pack_amount"]
                existing.pack_unit = barcode_data["pack_unit"]
                existing.source = barcode_data["source"]
                counts["barcodes_updated"] += 1

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    return counts


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dir",
        default=str(BACKEND_DIR / "data" / "seed"),
        help="Directory containing foods.csv, variants.csv, aliases.csv, barcodes.csv",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the CSV files without writing to the database",
    )
    args = parser.parse_args()

    seed_dir = Path(args.dir)
    await init_db()
    await seed_default_tags()

    foods = load_foods(read_rows(seed_dir / "foods.csv"))
    variants = load_variants(read_rows(seed_dir / "variants.csv"), foods)
    aliases = load_aliases(
        read_rows(seed_dir / "aliases.csv", optional=True), foods
    )
    servings = load_servings(
        read_rows(seed_dir / "servings.csv", optional=True), foods, variants
    )
    barcodes = load_barcodes(
        read_rows(seed_dir / "barcodes.csv", optional=True), foods, variants
    )

    print(
        f"Validated {len(foods)} foods, "
        f"{sum(len(items) for items in variants.values())} variants, "
        f"{sum(len(items) for items in aliases.values())} aliases, "
        f"{len(servings)} servings, "
        f"{len(barcodes)} barcodes."
    )

    counts = await apply_import(
        foods, variants, aliases, servings, barcodes, dry_run=args.dry_run
    )
    print(
        "Dry run complete; no rows committed."
        if args.dry_run
        else "Import complete."
    )
    for key, value in counts.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except ImportErrorWithContext as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
