#!/usr/bin/env python3
"""Validate the mainland China prefecture-level unit catalog.

The catalog intentionally contains only prefecture-level administrative units:
municipalities, prefecture-level cities, prefectures, autonomous prefectures,
and leagues. Districts, counties, and county-level cities must not be added.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "china_prefecture_units.json"
ALLOWED_CATEGORIES = {"直辖市", "地级市", "地区", "自治州", "盟"}
FORBIDDEN_SUFFIXES = ("县",)


def main() -> int:
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    units = payload["units"]
    names = [unit["name"] for unit in units]
    duplicates = [name for name, count in Counter(names).items() if count > 1]
    if duplicates:
        raise SystemExit(f"Duplicate prefecture units: {duplicates}")
    bad_categories = sorted({unit["category"] for unit in units} - ALLOWED_CATEGORIES)
    if bad_categories:
        raise SystemExit(f"Unsupported categories: {bad_categories}")
    bad_suffixes = [name for name in names if name.endswith(FORBIDDEN_SUFFIXES) or (name.endswith("区") and not name.endswith("地区"))]
    if bad_suffixes:
        raise SystemExit(f"Catalog contains district/county-level names: {bad_suffixes}")
    declared_count = int(payload.get("count", -1))
    if declared_count != len(units):
        raise SystemExit(f"Declared count {declared_count} != actual {len(units)}")
    non_municipality_count = sum(1 for unit in units if unit["category"] != "直辖市")
    if non_municipality_count != 333:
        raise SystemExit(f"Expected 333 non-municipality units, got {non_municipality_count}")
    category_counts = Counter(unit["category"] for unit in units)
    print(f"OK: {len(units)} units; category counts: {dict(sorted(category_counts.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
