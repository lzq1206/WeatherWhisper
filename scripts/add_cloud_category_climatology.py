#!/usr/bin/env python3
"""Add WeatherSpark-style five-band cloud climatology to published city files.

Inputs:
  - public/data/prefecture-*.json
  - cached NASA POWER responses in --cache-dir/power

Outputs:
  - patched public/data/prefecture-*.json
  - matching data/processed/prefecture-*.json when present
  - audits/cloud_category_distribution_20260717/summary.json
  - audits/cloud_category_distribution_20260717/city_cloud_category_audit.csv

The script preserves all existing temperature, precipitation, station selection,
and tourism fields. It only derives cloud-category frequencies from the frozen
1991-2020 NASA POWER daily cloud-cover cache.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from build_climate_normals import (
    CLOUD_CATEGORY_KEYS,
    CLOUD_CATEGORY_LABELS,
    aggregate_power,
    circular_smooth,
    rounded_distribution,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--cache-dir", default="/tmp/weatherwhisper_climate_normals_cache")
    return parser.parse_args()


def cache_path_for(payload_path: Path, payload: dict[str, Any], cache_dir: Path) -> Path:
    metadata = payload["metadata"]
    if str(metadata.get("admin_coordinate_source", "catalog")) == "catalog":
        candidate = cache_dir / "power" / payload_path.name
    else:
        candidate = cache_dir / "power" / f"{payload_path.stem}_{float(metadata['lat']):.4f}_{float(metadata['lon']):.4f}.json"
    if not candidate.exists():
        matches = sorted((cache_dir / "power").glob(f"{payload_path.stem}*.json"))
        if len(matches) == 1:
            return matches[0]
        raise FileNotFoundError(f"No unambiguous NASA POWER cache for {payload_path.stem}: {matches}")
    return candidate


def patch_city(payload: dict[str, Any], era: dict[str, Any] | None) -> None:
    daily = payload.get("daily_climatology", [])
    if len(daily) != 365:
        raise ValueError(f"Expected 365 daily climatology points, found {len(daily)}")
    expanded = all("cloud_categories" in point for point in daily)
    if expanded:
        distributions = [rounded_distribution({
            key: float(point["cloud_categories"].get(key, 0))
            for key in CLOUD_CATEGORY_KEYS
        }) for point in daily]
    else:
        if era is None:
            raise ValueError("NASA POWER cache aggregation is required when expanded cloud categories are absent")
        category_profiles = {
            key: circular_smooth(era["profiles"]["cloud_categories"][key], 15)
            for key in CLOUD_CATEGORY_KEYS
        }
        distributions = [rounded_distribution({
            key: float(category_profiles[key][index] or 0)
            for key in CLOUD_CATEGORY_KEYS
        }) for index in range(365)]
    for point in daily:
        point.pop("cloud_categories", None)
    payload["cloud_category_climatology"] = {
        key: ",".join(f"{distribution[key]:.1f}" for distribution in distributions)
        for key in CLOUD_CATEGORY_KEYS
    }

    if not expanded:
        for month in range(1, 13):
            distribution = rounded_distribution({
                key: float(era["monthly"][month]["cloud_categories"][key] or 0)
                for key in CLOUD_CATEGORY_KEYS
            })
            payload["monthly"][str(month)]["cloud_categories"] = {
                key: {"label": CLOUD_CATEGORY_LABELS[key], "pct": distribution[key]}
                for key in CLOUD_CATEGORY_KEYS
            }

    payload.setdefault("methodology", {}).setdefault("climate_normals", {})["cloud_categories"] = (
        "Daily mean sky cover classified as clear 0-<20%, mostly clear 20-<40%, "
        "partly cloudy 40-<60%, mostly cloudy 60-<80%, and overcast 80-100%; "
        "category frequencies use a 15-day centered circular window across 1991-2020."
    )
    payload["yearly"]["method_note"] = (
        "Daily curves are 15-day circular-smoothed 1991-2020 day-of-year normals. "
        "Cloud categories classify each historical day's mean sky cover into five "
        "20-percentage-point bands before calculating day-of-year frequencies. "
        "Rainfall is a centered rolling 31-day climatological accumulation. The hourly "
        "month-by-hour heatmap remains a separately labelled OneBuilding TMY reference."
    )


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    cache_dir = Path(args.cache_dir)
    audit_dir = root / "audits" / "cloud_category_distribution_20260717"
    audit_dir.mkdir(parents=True, exist_ok=True)
    paths = sorted((root / "public" / "data").glob("prefecture-*.json"))
    audits: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for index, path in enumerate(paths, 1):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            source_cache = cache_path_for(path, payload, cache_dir)
            expanded = all("cloud_categories" in point for point in payload.get("daily_climatology", []))
            era = None if expanded else aggregate_power(json.loads(source_cache.read_text(encoding="utf-8")))
            patch_city(payload, era)
            encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
            path.write_text(encoded, encoding="utf-8")
            processed = root / "data" / "processed" / path.name
            if processed.exists():
                processed.write_text(encoded, encoding="utf-8")
            daily_failures = sum(
                abs(sum(float(payload["cloud_category_climatology"][key].split(",")[point_index]) for key in CLOUD_CATEGORY_KEYS) - 100) > 0.11
                for point_index in range(365)
            )
            monthly_failures = sum(
                abs(sum(float(payload["monthly"][str(month)]["cloud_categories"][key]["pct"]) for key in CLOUD_CATEGORY_KEYS) - 100) > 0.11
                for month in range(1, 13)
            )
            audits.append({
                "catalog_id": path.stem,
                "city": payload["metadata"].get("city"),
                "cache_file": source_cache.name,
                "daily_points": len(payload["daily_climatology"]),
                "daily_sum_failures": daily_failures,
                "monthly_sum_failures": monthly_failures,
            })
            print(f"[{index}/{len(paths)}] {path.stem}", flush=True)
        except Exception as exc:
            errors.append({"catalog_id": path.stem, "error": str(exc)})
            print(f"ERROR {path.stem}: {exc}", flush=True)

    fieldnames = ["catalog_id", "city", "cache_file", "daily_points", "daily_sum_failures", "monthly_sum_failures"]
    with (audit_dir / "city_cloud_category_audit.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(audits)
    summary = {
        "period": "1991-2020",
        "category_thresholds_pct": [0, 20, 40, 60, 80, 100],
        "requested_cities": len(paths),
        "completed_cities": len(audits),
        "errors": errors,
        "daily_point_failures": [row["catalog_id"] for row in audits if row["daily_points"] != 365],
        "daily_sum_failures": [row["catalog_id"] for row in audits if row["daily_sum_failures"]],
        "monthly_sum_failures": [row["catalog_id"] for row in audits if row["monthly_sum_failures"]],
    }
    (audit_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors or summary["daily_point_failures"] or summary["daily_sum_failures"] or summary["monthly_sum_failures"]:
        raise SystemExit(f"Cloud-category patch failed validation: {summary}")


if __name__ == "__main__":
    main()
