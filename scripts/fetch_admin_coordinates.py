#!/usr/bin/env python3
"""Fill missing prefecture coordinates with audited Nominatim geocoding.

Input: data/prefecture_city_catalog/prefecture_admin_unit_station_matches_20260716v2.csv
Output: data/prefecture_city_catalog/admin_unit_coordinates_20260716.csv

Existing catalog coordinates are retained. Only missing coordinates are queried,
at one request per second in line with the public Nominatim usage policy.
"""

from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "prefecture_city_catalog" / "prefecture_admin_unit_station_matches_20260716v2.csv"
OUTPUT = ROOT / "data" / "prefecture_city_catalog" / "admin_unit_coordinates_20260716.csv"
CACHE = Path("/tmp/weatherwhisper_nominatim_admin_coordinates.json")


def geocode(query: str) -> dict:
    params = urllib.parse.urlencode({"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "cn", "addressdetails": 1})
    request = urllib.request.Request(
        "https://nominatim.openstreetmap.org/search?" + params,
        headers={"User-Agent": "WeatherWhisper/1.0 admin-coordinate-audit (github.com/lzq1206/WeatherWhisper)"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        results = json.loads(response.read())
    if not results:
        raise RuntimeError(f"No geocoding result for {query}")
    return results[0]


def main() -> None:
    rows = list(csv.DictReader(INPUT.open(encoding="utf-8-sig")))
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    output = []
    for row in rows:
        if row["lat"] and row["lon"]:
            lat, lon, source, display = row["lat"], row["lon"], "catalog", ""
        else:
            query = f"{row['city_zh']}, {row['province_zh']}, 中国"
            if query not in cache:
                cache[query] = geocode(query)
                CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
                time.sleep(1.05)
            result = cache[query]
            lat, lon, source, display = result["lat"], result["lon"], "OpenStreetMap Nominatim", result.get("display_name", "")
        output.append({
            "catalog_id": row["catalog_id"],
            "division_code": row["division_code"],
            "province_zh": row["province_zh"],
            "city_zh": row["city_zh"],
            "lat": lat,
            "lon": lon,
            "coordinate_source": source,
            "geocoder_display_name": display,
        })
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    print(f"Wrote {len(output)} coordinates; geocoded {sum(r['coordinate_source'] != 'catalog' for r in output)} missing rows")


if __name__ == "__main__":
    main()
