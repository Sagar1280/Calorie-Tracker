"""Audit food and variant nutrition data and write a QA report.

Usage:
    python scripts/audit_foods.py
    python scripts/audit_foods.py --db data/calorie_tracker.db --out data/qa_report.csv
    python scripts/audit_foods.py --fail-on-high
"""

import argparse
import csv
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = BACKEND_DIR / "data" / "calorie_tracker.db"
DEFAULT_OUT = BACKEND_DIR / "data" / "qa_report.csv"
FIELDNAMES = [
    "severity",
    "issue",
    "food_id",
    "food_slug",
    "food_name",
    "variant_id",
    "detail",
]


@dataclass(frozen=True)
class Issue:
    severity: str
    issue: str
    food_id: int
    food_slug: str
    food_name: str
    variant_id: int | None
    detail: str

    def to_row(self) -> dict[str, str | int]:
        return {
            "severity": self.severity,
            "issue": self.issue,
            "food_id": self.food_id,
            "food_slug": self.food_slug,
            "food_name": self.food_name,
            "variant_id": self.variant_id or "",
            "detail": self.detail,
        }


def number(value: float | None) -> float:
    return float(value) if value is not None else 0.0


def audit(db_path: Path) -> tuple[list[Issue], Counter[str]]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    issues: list[Issue] = []
    summary: Counter[str] = Counter()

    foods = connection.execute(
        """
        select id, slug, name, name_normalized, category, base_unit, source,
               status, is_verified, brand_id
        from foods
        order by id
        """
    ).fetchall()
    summary["foods"] = len(foods)
    summary["verified"] = sum(1 for food in foods if food["is_verified"])
    summary["unverified"] = len(foods) - summary["verified"]
    for food in foods:
        summary[f"source:{food['source']}"] += 1
        summary[f"status:{food['status']}"] += 1

    variants = connection.execute(
        """
        select id, food_id, state, label, kcal, protein_g, carbs_g, fat_g,
               base_amount, base_unit, is_default
        from food_variants
        order by food_id, id
        """
    ).fetchall()
    summary["variants"] = len(variants)
    variants_by_food: dict[int, list[sqlite3.Row]] = {}
    for variant in variants:
        variants_by_food.setdefault(variant["food_id"], []).append(variant)

    servings = connection.execute(
        """
        select id, variant_id, label, amount, unit, is_default
        from servings
        order by variant_id, id
        """
    ).fetchall()
    summary["servings"] = len(servings)
    servings_by_variant: dict[int, list[sqlite3.Row]] = {}
    for serving in servings:
        servings_by_variant.setdefault(serving["variant_id"], []).append(serving)

    barcodes = connection.execute(
        "select food_id, barcode, pack_amount, pack_unit from food_barcodes"
    ).fetchall()
    summary["barcodes"] = len(barcodes)

    for food in foods:
        food_variants = variants_by_food.get(food["id"], [])
        if not food_variants:
            issues.append(
                Issue(
                    "high",
                    "missing_variant",
                    food["id"],
                    food["slug"],
                    food["name"],
                    None,
                    "Food has no nutrition variant.",
                )
            )
            continue

        defaults = [variant for variant in food_variants if variant["is_default"]]
        if not defaults:
            issues.append(
                Issue(
                    "medium",
                    "missing_default_variant",
                    food["id"],
                    food["slug"],
                    food["name"],
                    None,
                    f"{len(food_variants)} variant(s) but none is default.",
                )
            )
        elif len(defaults) > 1:
            issues.append(
                Issue(
                    "medium",
                    "multiple_default_variants",
                    food["id"],
                    food["slug"],
                    food["name"],
                    None,
                    f"{len(defaults)} variants are marked default.",
                )
            )

        for variant in food_variants:
            variant_id = variant["id"]
            if variant["base_unit"] != food["base_unit"]:
                issues.append(
                    Issue(
                        "high",
                        "base_unit_mismatch",
                        food["id"],
                        food["slug"],
                        food["name"],
                        variant_id,
                        f"Food uses {food['base_unit']}, variant uses {variant['base_unit']}.",
                    )
                )

            if variant["kcal"] is None:
                issues.append(
                    Issue(
                        "high",
                        "missing_calories",
                        food["id"],
                        food["slug"],
                        food["name"],
                        variant_id,
                        "Variant has no calorie value.",
                    )
                )
                continue

            kcal = float(variant["kcal"])
            seasoning = food["category"] == "condiment" or "salt" in food["name_normalized"]
            if kcal <= 0:
                severity = (
                    "low"
                    if food["category"] in {"beverage", "water"} or seasoning
                    else "medium"
                )
                issues.append(
                    Issue(
                        severity,
                        "zero_calories",
                        food["id"],
                        food["slug"],
                        food["name"],
                        variant_id,
                        f"Calories are {kcal:g} per {variant['base_amount']:g}{variant['base_unit']}.",
                    )
                )
            elif kcal > 900:
                issues.append(
                    Issue(
                        "high",
                        "extreme_calories",
                        food["id"],
                        food["slug"],
                        food["name"],
                        variant_id,
                        f"Calories are {kcal:g} per {variant['base_amount']:g}{variant['base_unit']}.",
                    )
                )

            protein = number(variant["protein_g"])
            carbs = number(variant["carbs_g"])
            fat = number(variant["fat_g"])
            macro_total = protein + carbs + fat
            macro_kcal = 4 * protein + 4 * carbs + 9 * fat
            difference = abs(macro_kcal - kcal)
            ratio = difference / max(kcal, 1)
            if macro_total > 105:
                issues.append(
                    Issue(
                        "high",
                        "macro_total_over_100",
                        food["id"],
                        food["slug"],
                        food["name"],
                        variant_id,
                        f"Protein + carbs + fat = {macro_total:.1f}g.",
                    )
                )
            if protein == 0 and carbs == 0 and fat == 0 and kcal > 20:
                issues.append(
                    Issue(
                        "high",
                        "missing_macros",
                        food["id"],
                        food["slug"],
                        food["name"],
                        variant_id,
                        f"{kcal:g} kcal but all macros are zero.",
                    )
                )
            elif difference > 60 and ratio > 0.5:
                issues.append(
                    Issue(
                        "low" if seasoning else "high",
                        "macro_calorie_mismatch",
                        food["id"],
                        food["slug"],
                        food["name"],
                        variant_id,
                        (
                            f"{kcal:g} kcal vs {macro_kcal:.0f} kcal from macros "
                            f"({ratio:.0%} off); check fiber or rounding."
                        ),
                    )
                )
            elif difference > 35 and ratio > 0.25:
                issues.append(
                    Issue(
                        "low" if seasoning else "medium",
                        "macro_calorie_mismatch",
                        food["id"],
                        food["slug"],
                        food["name"],
                        variant_id,
                        (
                            f"{kcal:g} kcal vs {macro_kcal:.0f} kcal from macros "
                            f"({ratio:.0%} off); check fiber or rounding."
                        ),
                    )
                )

            variant_servings = servings_by_variant.get(variant_id, [])
            for serving in variant_servings:
                if serving["amount"] <= 0 or serving["amount"] > 10000:
                    issues.append(
                        Issue(
                            "high",
                            "invalid_serving_amount",
                            food["id"],
                            food["slug"],
                            food["name"],
                            variant_id,
                            f"'{serving['label']}' is {serving['amount']:g}{serving['unit']}.",
                        )
                    )
                if serving["unit"] != variant["base_unit"]:
                    issues.append(
                        Issue(
                            "medium",
                            "serving_unit_mismatch",
                            food["id"],
                            food["slug"],
                            food["name"],
                            variant_id,
                            f"'{serving['label']}' uses {serving['unit']}, variant uses {variant['base_unit']}.",
                        )
                    )

    for barcode in barcodes:
        if barcode["pack_amount"] is None:
            continue
        food = next((item for item in foods if item["id"] == barcode["food_id"]), None)
        if food is None:
            continue
        if barcode["pack_unit"] not in {"g", "ml"}:
            issues.append(
                Issue(
                    "medium",
                    "invalid_pack_unit",
                    food["id"],
                    food["slug"],
                    food["name"],
                    None,
                    f"Barcode {barcode['barcode']} pack unit is {barcode['pack_unit']}.",
                )
            )
        if barcode["pack_amount"] <= 0 or barcode["pack_amount"] > 10000:
            issues.append(
                Issue(
                    "high",
                    "invalid_pack_amount",
                    food["id"],
                    food["slug"],
                    food["name"],
                    None,
                    f"Barcode {barcode['barcode']} pack is {barcode['pack_amount']:g}.",
                )
            )

    names: dict[tuple[str, int | None], list[sqlite3.Row]] = {}
    for food in foods:
        key = (food["name_normalized"], food["brand_id"])
        names.setdefault(key, []).append(food)

    for (_, _), duplicates in names.items():
        if len(duplicates) < 2:
            continue
        for duplicate in duplicates:
            others = ", ".join(
                item["slug"] for item in duplicates if item["id"] != duplicate["id"]
            )
            issues.append(
                Issue(
                    "medium",
                    "duplicate_food_name",
                    duplicate["id"],
                    duplicate["slug"],
                    duplicate["name"],
                    None,
                    f"Same name and brand as: {others}.",
                )
            )

    connection.close()
    return issues, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--fail-on-high", action="store_true")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Database not found: {args.db}", file=sys.stderr)
        return 2

    issues, summary = audit(args.db)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(issue.to_row() for issue in issues)

    counts = Counter(issue.severity for issue in issues)
    issue_counts = Counter(issue.issue for issue in issues)
    print(f"Wrote {len(issues)} findings to {args.out}")
    print(
        "Foods: {foods} ({verified} verified, {unverified} unverified)".format(
            **summary
        )
    )
    print(
        "Variants: {variants}  servings: {servings}  barcodes: {barcodes}".format(
            **summary
        )
    )
    print(
        "Severity: {high} high, {medium} medium, {low} low".format(
            high=counts["high"], medium=counts["medium"], low=counts["low"]
        )
    )
    if issue_counts:
        print("Top findings:")
        for name, count in issue_counts.most_common(8):
            print(f"  {count:4d}  {name}")

    if args.fail_on_high and counts["high"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
