#!/usr/bin/env python3
"""Build 1991-2020 daily climate normals for every published city.

Inputs:
  - public/data/prefecture-*.json (city/station coordinates and existing schema)
  - NASA POWER daily point API (MERRA-2 based daily values)
  - NOAA NCEI Global Summary of the Day (station temperature/dew point)

Outputs:
  - patched public/data/prefecture-*.json
  - matching data/processed/prefecture-*.json when present
  - audits/climate_normals_1991_2020_20260717/summary.json
  - audits/climate_normals_1991_2020_20260717/city_source_audit.csv

The raw API cache defaults to /tmp so generated source downloads are not added to
the repository.  Use --cache-dir to retain a reproducible frozen cache elsewhere.
"""

from __future__ import annotations

import argparse
import csv
import http.client
import json
import math
import os
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any, Iterable


POWER_PARAMS = [
    "T2M",
    "T2M_MAX",
    "T2M_MIN",
    "T2MDEW",
    "RH2M",
    "WS10M",
    "PRECTOTCORR",
    "CLOUD_AMT",
    "ALLSKY_SFC_SW_DWN",
]

CLOUD_CATEGORY_KEYS = ("clear", "mostly_clear", "partly_cloudy", "mostly_cloudy", "overcast")
CLOUD_CATEGORY_LABELS = {
    "clear": "晴天",
    "mostly_clear": "大部分晴天",
    "partly_cloudy": "部分多云",
    "mostly_cloudy": "大部分多云",
    "overcast": "阴天",
}

MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
CUM_DAYS = [0]
for _days in MONTH_DAYS:
    CUM_DAYS.append(CUM_DAYS[-1] + _days)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--cache-dir", default="/tmp/weatherwhisper_climate_normals_cache")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--skip-noaa", action="store_true")
    return parser.parse_args()


def fetch_json(url: str, cache_path: Path, retries: int = 5) -> Any:
    if cache_path.exists() and cache_path.stat().st_size > 100:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "WeatherWhisper/1.0 climate-normal-builder"})
            with urllib.request.urlopen(request, timeout=240) as response:
                payload = response.read()
            parsed = json.loads(payload)
            cache_path.write_bytes(payload)
            return parsed
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, http.client.IncompleteRead, ConnectionResetError) as exc:
            last_error = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed after {retries} attempts: {url}: {last_error}")


def month_day(doy: int) -> tuple[int, int]:
    for month in range(1, 13):
        if doy <= CUM_DAYS[month]:
            return month, doy - CUM_DAYS[month - 1]
    raise ValueError(doy)


def doy_no_leap(iso_date: str) -> int | None:
    year, month, day = (int(part) for part in iso_date.split("-"))
    if month == 2 and day == 29:
        return None
    value = date(year, month, day).timetuple().tm_yday
    if month > 2 and _is_leap(year):
        value -= 1
    return value


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def valid_number(value: Any, missing_above: float | None = None) -> float | None:
    try:
        number = float(str(value).replace("*", "").strip())
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or (missing_above is not None and number >= missing_above):
        return None
    return number


def f_to_c(value: Any) -> float | None:
    number = valid_number(value, 9999)
    return None if number is None else (number - 32) * 5 / 9


def knots_to_mps(value: Any) -> float | None:
    number = valid_number(value, 999)
    return None if number is None else number * 0.514444


def mean(values: Iterable[float | None]) -> float | None:
    clean = [float(v) for v in values if v is not None and not math.isnan(float(v))]
    return statistics.fmean(clean) if clean else None


def cloud_category(cloud_pct: float) -> str:
    """Classify daily mean sky cover using WeatherSpark-style 20-point bands."""
    if cloud_pct < 20:
        return "clear"
    if cloud_pct < 40:
        return "mostly_clear"
    if cloud_pct < 60:
        return "partly_cloudy"
    if cloud_pct < 80:
        return "mostly_cloudy"
    return "overcast"


def rounded_distribution(values: dict[str, float], digits: int = 1) -> dict[str, float]:
    """Round a five-part percentage distribution while retaining an exact 100% sum."""
    result: dict[str, float] = {}
    for key in CLOUD_CATEGORY_KEYS[:-1]:
        result[key] = round(float(values.get(key, 0)), digits)
    result[CLOUD_CATEGORY_KEYS[-1]] = round(100.0 - sum(result.values()), digits)
    return result


def circular_smooth(values: list[float | None], window: int = 15) -> list[float | None]:
    radius = window // 2
    size = len(values)
    result: list[float | None] = []
    for idx in range(size):
        sample = [values[(idx + offset) % size] for offset in range(-radius, radius + 1)]
        result.append(mean(sample))
    return result


def circular_rolling_sum(values: list[float | None], window: int = 31) -> list[float]:
    radius = window // 2
    size = len(values)
    return [sum(float(values[(idx + offset) % size] or 0) for offset in range(-radius, radius + 1)) for idx in range(size)]


def rh_from_temp_dew(temp_c: float | None, dew_c: float | None) -> float | None:
    if temp_c is None or dew_c is None:
        return None
    value = 100 * math.exp((17.625 * dew_c) / (243.04 + dew_c) - (17.625 * temp_c) / (243.04 + temp_c))
    return max(0.0, min(100.0, value))


def apparent_temperature(temp_c: float, rh: float, wind_mps: float) -> float:
    if temp_c >= 27 and rh >= 40:
        t = temp_c * 9 / 5 + 32
        hi_f = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh
                - 0.00683783 * t * t - 0.05481717 * rh * rh
                + 0.00122874 * t * t * rh + 0.00085282 * t * rh * rh
                - 0.00000199 * t * t * rh * rh)
        return (hi_f - 32) * 5 / 9
    wind_kmh = wind_mps * 3.6
    if temp_c <= 10 and wind_kmh > 4.8:
        return 13.12 + 0.6215 * temp_c - 11.37 * wind_kmh ** 0.16 + 0.3965 * temp_c * wind_kmh ** 0.16
    return temp_c


def interp(x: float, points: list[tuple[float, float]]) -> float:
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (x - x0) / (x1 - x0) * (y1 - y0)
    return points[-1][1]


def tourism_score(apparent: float, cloud: float, wet_probability: float, beach: bool = False) -> float:
    temp_points = [(-50, 0), (18, 0), (24, 9), (28, 10), (32, 9), (38, 1), (60, 1)] if beach else [(-50, 0), (10, 0), (18, 9), (24, 10), (27, 9), (32, 1), (60, 1)]
    temp_score = max(0, min(10, interp(apparent, temp_points)))
    cloud_score = 10 - min(100, max(0, cloud)) / 100 * 9
    precip_score = 10 - min(100, max(0, wet_probability)) / 100 * 10
    return 0.5 * temp_score + 0.25 * cloud_score + 0.25 * precip_score


def tourism_components(apparent: float, cloud: float, wet_probability: float, beach: bool = False) -> tuple[float, float, float]:
    temp_points = [(-50, 0), (18, 0), (24, 9), (28, 10), (32, 9), (38, 1), (60, 1)] if beach else [(-50, 0), (10, 0), (18, 9), (24, 10), (27, 9), (32, 1), (60, 1)]
    return (
        max(0, min(10, interp(apparent, temp_points))),
        10 - min(100, max(0, cloud)) / 100 * 9,
        10 - min(100, max(0, wet_probability)) / 100 * 10,
    )


def direction_text(degrees: float | None) -> str:
    if degrees is None:
        return "—"
    labels = ["北", "东北偏北", "东北", "东北偏东", "东", "东南偏东", "东南", "东南偏南", "南", "西南偏南", "西南", "西南偏西", "西", "西北偏西", "西北", "西北偏北"]
    return labels[int((degrees % 360) / 22.5 + 0.5) % 16]


def months_to_text(months: list[int]) -> str:
    if not months:
        return "四季皆宜"
    values = sorted(set(months))
    ranges: list[tuple[int, int]] = []
    start = previous = values[0]
    for month in values[1:]:
        if month == previous + 1:
            previous = month
            continue
        ranges.append((start, previous))
        start = previous = month
    ranges.append((start, previous))
    return "、".join(f"{start}-{end}月" if start != end else f"{start}月" for start, end in ranges)


def vector_direction(values: list[float | None]) -> float | None:
    clean = [math.radians(v) for v in values if v is not None]
    if not clean:
        return None
    x = statistics.fmean(math.sin(v) for v in clean)
    y = statistics.fmean(math.cos(v) for v in clean)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def power_url(lat: float, lon: float) -> str:
    params = {
        "parameters": ",".join(POWER_PARAMS),
        "community": "RE",
        "longitude": f"{lon:.5f}",
        "latitude": f"{lat:.5f}",
        "start": "19910101",
        "end": "20201231",
        "format": "JSON",
    }
    return "https://power.larc.nasa.gov/api/temporal/daily/point?" + urllib.parse.urlencode(params)


def noaa_url(wmo: str) -> str:
    params = {
        "dataset": "global-summary-of-the-day",
        "stations": f"{wmo}99999",
        "startDate": "1991-01-01",
        "endDate": "2020-12-31",
        "format": "json",
    }
    return "https://www.ncei.noaa.gov/access/services/data/v1?" + urllib.parse.urlencode(params)


def aggregate_power(payload: dict[str, Any]) -> dict[str, Any]:
    parameters = payload["properties"]["parameter"]
    key_map = {
        "T2M": "temperature_2m_mean",
        "T2M_MAX": "temperature_2m_max",
        "T2M_MIN": "temperature_2m_min",
        "T2MDEW": "dew_point_2m_mean",
        "RH2M": "relative_humidity_2m_mean",
        "WS10M": "wind_speed_10m_mean",
        "PRECTOTCORR": "precipitation_sum",
        "CLOUD_AMT": "cloud_cover_mean",
        "ALLSKY_SFC_SW_DWN": "solar_kwh",
    }
    by_doy: dict[str, list[list[float]]] = {value: [[] for _ in range(365)] for value in key_map.values()}
    wet_by_doy: list[list[float]] = [[] for _ in range(365)]
    cloud_category_by_doy: dict[str, list[list[float]]] = {
        key: [[] for _ in range(365)] for key in CLOUD_CATEGORY_KEYS
    }
    month_values: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    monthly_cloud_categories: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    annual_month_precip: dict[tuple[int, int], float] = defaultdict(float)
    dates = sorted(parameters["T2M"])
    for compact_date in dates:
        iso = f"{compact_date[:4]}-{compact_date[4:6]}-{compact_date[6:8]}"
        doy = doy_no_leap(iso)
        if doy is None:
            continue
        year, month = int(iso[:4]), int(iso[5:7])
        for source_key, key in key_map.items():
            value = valid_number(parameters[source_key].get(compact_date))
            if value is not None and value > -900:
                by_doy[key][doy - 1].append(value)
                month_values[month][key].append(value)
                if key == "precipitation_sum":
                    annual_month_precip[(year, month)] += value
        precip = valid_number(parameters["PRECTOTCORR"].get(compact_date))
        wet_by_doy[doy - 1].append(1.0 if (precip or 0) >= 1 else 0.0)
        cloud = valid_number(parameters["CLOUD_AMT"].get(compact_date))
        if cloud is not None and cloud > -900:
            category = cloud_category(cloud)
            for key in CLOUD_CATEGORY_KEYS:
                indicator = 1.0 if key == category else 0.0
                cloud_category_by_doy[key][doy - 1].append(indicator)
                monthly_cloud_categories[month][key].append(indicator)
    profiles = {key: [mean(values) for values in slots] for key, slots in by_doy.items()}
    profiles["wet_probability"] = [(mean(values) or 0) * 100 for values in wet_by_doy]
    profiles["cloud_categories"] = {
        key: [(mean(values) or 0) * 100 for values in cloud_category_by_doy[key]]
        for key in CLOUD_CATEGORY_KEYS
    }
    monthly: dict[int, dict[str, float | None]] = {}
    for month in range(1, 13):
        monthly[month] = {key: mean(month_values[month][key]) for key in key_map.values()}
        monthly[month]["precipitation_sum"] = mean([annual_month_precip[(year, month)] for year in range(1991, 2021)])
        month_wet = [value for doy, values in enumerate(wet_by_doy, 1) if month_day(doy)[0] == month for value in values]
        monthly[month]["wet_probability"] = (mean(month_wet) or 0) * 100
        monthly[month]["cloud_categories"] = {
            key: (mean(monthly_cloud_categories[month][key]) or 0) * 100
            for key in CLOUD_CATEGORY_KEYS
        }
    coordinates = payload.get("geometry", {}).get("coordinates", [])
    return {"profiles": profiles, "monthly": monthly, "grid_lat": coordinates[1] if len(coordinates) > 1 else None, "grid_lon": coordinates[0] if coordinates else None, "grid_elevation": coordinates[2] if len(coordinates) > 2 else None}


def aggregate_noaa(payload: list[dict[str, Any]]) -> dict[str, Any]:
    fields = {"temp": [[] for _ in range(365)], "temp_max": [[] for _ in range(365)], "temp_min": [[] for _ in range(365)], "dew": [[] for _ in range(365)]}
    valid_year_days: dict[int, int] = defaultdict(int)
    valid_records = 0
    for row in payload:
        iso = row.get("DATE", "")
        if len(iso) != 10:
            continue
        doy = doy_no_leap(iso)
        if doy is None:
            continue
        values = {"temp": f_to_c(row.get("TEMP")), "temp_max": f_to_c(row.get("MAX")), "temp_min": f_to_c(row.get("MIN")), "dew": f_to_c(row.get("DEWP"))}
        if values["temp"] is not None:
            valid_year_days[int(iso[:4])] += 1
            valid_records += 1
        for key, value in values.items():
            if value is not None:
                fields[key][doy - 1].append(value)
    valid_years = sum(days >= 180 for days in valid_year_days.values())
    return {
        "eligible": valid_years >= 10 and valid_records >= 3000,
        "valid_years": valid_years,
        "valid_days": valid_records,
        "profiles": {key: [mean(values) for values in slots] for key, slots in fields.items()},
    }


def profile_month_mean(profile: list[float | None], month: int) -> float | None:
    return mean(profile[CUM_DAYS[month - 1]:CUM_DAYS[month]])


def build_city(payload: dict[str, Any], era: dict[str, Any], noaa: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    eprof = era["profiles"]
    match_quality = str(payload.get("metadata", {}).get("station_match_quality", ""))
    geographically_direct = match_quality in {"direct", "direct_quality_override", "audited_direct_override"}
    use_station = bool(geographically_direct and noaa and noaa["eligible"])
    station_profiles = noaa["profiles"] if use_station and noaa else {}
    base: dict[str, list[float | None]] = {
        "temp_avg": station_profiles.get("temp", eprof["temperature_2m_mean"]),
        "temp_max": station_profiles.get("temp_max", eprof["temperature_2m_max"]),
        "temp_min": station_profiles.get("temp_min", eprof["temperature_2m_min"]),
        "dew_point": station_profiles.get("dew", eprof["dew_point_2m_mean"]),
        "cloud": eprof["cloud_cover_mean"],
        "wind": eprof["wind_speed_10m_mean"],
        "wind_dir": [None] * 365,
        "precip": eprof["precipitation_sum"],
        "wet_probability": eprof["wet_probability"],
        "solar_kwh": eprof["solar_kwh"],
    }
    for key in ("temp_avg", "temp_max", "temp_min", "dew_point"):
        base[key] = [value if value is not None else eprof[{"temp_avg": "temperature_2m_mean", "temp_max": "temperature_2m_max", "temp_min": "temperature_2m_min", "dew_point": "dew_point_2m_mean"}[key]][idx] for idx, value in enumerate(base[key])]
    base["humidity"] = [rh_from_temp_dew(base["temp_avg"][idx], base["dew_point"][idx]) for idx in range(365)]
    base["apparent"] = [apparent_temperature(float(base["temp_avg"][idx] or 0), float(base["humidity"][idx] or 0), float(base["wind"][idx] or 0)) for idx in range(365)]
    smooth = {key: circular_smooth(values, 15) for key, values in base.items() if key not in ("precip", "wind_dir")}
    smooth["wind_dir"] = base["wind_dir"]
    smooth["precip_31d"] = circular_rolling_sum(base["precip"], 31)
    cloud_category_profiles = {
        key: circular_smooth(era["profiles"]["cloud_categories"][key], 15)
        for key in CLOUD_CATEGORY_KEYS
    }

    daily_climatology = []
    for idx in range(365):
        month, day = month_day(idx + 1)
        daily_climatology.append({
            "doy": idx + 1,
            "date": f"{month:02d}-{day:02d}",
            "temp_avg": round(float(smooth["temp_avg"][idx] or 0), 2),
            "temp_max": round(float(smooth["temp_max"][idx] or 0), 2),
            "temp_min": round(float(smooth["temp_min"][idx] or 0), 2),
            "apparent_temp": round(float(smooth["apparent"][idx] or 0), 2),
            "dew_point": round(float(smooth["dew_point"][idx] or 0), 2),
            "humidity": round(float(smooth["humidity"][idx] or 0), 1),
            "cloud": round(float(smooth["cloud"][idx] or 0), 1),
            "wind": round(float(smooth["wind"][idx] or 0), 2),
            "precip_31d": round(float(smooth["precip_31d"][idx]), 1),
            "wet_probability": round(float(smooth["wet_probability"][idx] or 0), 1),
            "solar_kwh": round(float(smooth["solar_kwh"][idx] or 0), 2),
        })

    monthly = payload["monthly"]
    for month in range(1, 13):
        item = monthly[str(month)]
        item["temp_avg"] = round(float(profile_month_mean(base["temp_avg"], month) or 0), 2)
        item["temp_max"] = round(float(profile_month_mean(base["temp_max"], month) or 0), 2)
        item["temp_min"] = round(float(profile_month_mean(base["temp_min"], month) or 0), 2)
        item["apparent_temp_avg"] = round(float(profile_month_mean(base["apparent"], month) or 0), 2)
        item["dew_point_avg"] = round(float(profile_month_mean(base["dew_point"], month) or 0), 2)
        item["humidity"] = round(float(profile_month_mean(base["humidity"], month) or 0), 2)
        item["wind"] = round(float(profile_month_mean(base["wind"], month) or 0), 2)
        direction = vector_direction(base["wind_dir"][CUM_DAYS[month - 1]:CUM_DAYS[month]])
        if direction is not None:
            item["wind_dir"] = round(direction, 1)
            item["wind_dir_text"] = direction_text(direction)
        item["precip"] = round(float(era["monthly"][month]["precipitation_sum"] or 0), 1)
        item["precip_probability"] = round(float(era["monthly"][month]["wet_probability"] or 0), 1)
        item["precip_days"] = round(item["precip_probability"] / 100 * MONTH_DAYS[month - 1], 1)
        item["cloud"] = round(float(profile_month_mean(base["cloud"], month) or 0), 1)
        item["opaque_cloud"] = item["cloud"]
        item["sunny_rate"] = round(100 - item["cloud"], 1)
        monthly_category_distribution = rounded_distribution({
            key: float(era["monthly"][month]["cloud_categories"][key] or 0)
            for key in CLOUD_CATEGORY_KEYS
        })
        item["cloud_categories"] = {
            key: {"label": CLOUD_CATEGORY_LABELS[key], "pct": monthly_category_distribution[key]}
            for key in CLOUD_CATEGORY_KEYS
        }
        item["solar"] = round(float(profile_month_mean(base["solar_kwh"], month) or 0) * MONTH_DAYS[month - 1] * 1000, 1)
        temp_score, cloud_score, precip_score = tourism_components(item["apparent_temp_avg"], item["cloud"], item["precip_probability"])
        item["tourism_temp_score"] = round(temp_score, 1)
        item["cloud_score"] = round(cloud_score, 1)
        item["precip_score"] = round(precip_score, 1)
        item["tourism_score"] = round(tourism_score(item["apparent_temp_avg"], item["cloud"], item["precip_probability"]), 1)
        item["beach_score"] = round(tourism_score(item["apparent_temp_avg"], item["cloud"], item["precip_probability"], beach=True), 1)

    yearly = payload["yearly"]
    weights = MONTH_DAYS
    weighted = lambda field: sum(float(monthly[str(m)][field]) * weights[m - 1] for m in range(1, 13)) / 365
    yearly["avg_temp"] = round(weighted("temp_avg"), 2)
    yearly["avg_apparent_temp"] = round(weighted("apparent_temp_avg"), 2)
    yearly["avg_dew_point"] = round(weighted("dew_point_avg"), 2)
    yearly["avg_humidity"] = round(weighted("humidity"), 2)
    yearly["avg_wind"] = round(weighted("wind"), 2)
    yearly["avg_cloud"] = round(weighted("cloud"), 1)
    yearly["avg_opaque_cloud"] = yearly["avg_cloud"]
    yearly["total_precip"] = round(sum(float(monthly[str(m)]["precip"]) for m in range(1, 13)), 1)
    yearly["total_solar"] = round(sum(float(monthly[str(m)]["solar"]) for m in range(1, 13)) / 1000, 1)
    yearly["tourism_score_avg"] = round(statistics.fmean(float(monthly[str(m)]["tourism_score"]) for m in range(1, 13)), 1)
    yearly["beach_score_avg"] = round(statistics.fmean(float(monthly[str(m)]["beach_score"]) for m in range(1, 13)), 1)
    tourism_ranking = sorted(((float(monthly[str(m)]["tourism_score"]), m) for m in range(1, 13)), reverse=True)
    comfortable = sorted(m for m in range(1, 13) if float(monthly[str(m)]["tourism_score"]) >= 6.2)
    preferred = comfortable or sorted(m for _, m in tourism_ranking[:4])
    yearly["best_tourism_months"] = months_to_text(preferred)
    yearly["best_time"] = yearly["best_tourism_months"]
    yearly["tourism_peak_month"] = tourism_ranking[0][1]
    yearly["data_source"] = "1991–2020 climate normals: NOAA GSOD station observations for temperature/dew point when coverage passes audit; NASA POWER/MERRA-2 daily reanalysis for cloud, precipitation, wind, solar energy and gap-free city coverage"
    yearly["method_note"] = "Daily curves are 15-day circular-smoothed 1991–2020 day-of-year normals. Cloud categories classify each historical day's mean sky cover into five 20-percentage-point bands before calculating day-of-year frequencies. Rainfall is a centered rolling 31-day climatological accumulation. The hourly month-by-hour heatmap remains a separately labelled OneBuilding TMY reference."
    yearly["climate_normal_period"] = "1991-2020"
    yearly["temperature_source"] = f"NOAA GSOD station {payload['metadata'].get('source_station_wmo', payload['metadata'].get('wmo'))}" if use_station else "NASA POWER/MERRA-2 gridded reanalysis"
    yearly["gridded_source"] = "NASA POWER/MERRA-2 daily meteorology (approximately 0.5° grid), 1991–2020"

    payload["daily_climatology"] = daily_climatology
    payload["cloud_category_climatology"] = {
        key: ",".join(
            f"{rounded_distribution({category_key: float(cloud_category_profiles[category_key][idx] or 0) for category_key in CLOUD_CATEGORY_KEYS})[key]:.1f}"
            for idx in range(365)
        )
        for key in CLOUD_CATEGORY_KEYS
    }
    payload["methodology"]["climate_normals"] = {
        "period": "1991-2020",
        "daily_smoothing": "15-day centered circular moving mean",
        "cloud_categories": "Daily mean sky cover classified as clear 0-<20%, mostly clear 20-<40%, partly cloudy 40-<60%, mostly cloudy 60-<80%, and overcast 80-100%; category frequencies use a 15-day centered circular window across 1991-2020.",
        "rainfall": "31-day centered rolling accumulation of mean daily precipitation",
        "temperature_dew_point": yearly["temperature_source"],
        "gridded_variables": yearly["gridded_source"],
        "grid_coordinate": [era["grid_lat"], era["grid_lon"]],
        "grid_elevation_m": era["grid_elevation"],
        "hourly_heatmap_boundary": "OneBuilding TMY hourly structure retained as a separate reference; it is not a 30-year climatology.",
    }
    audit = {
        "catalog_id": payload["metadata"].get("catalog_id"),
        "city": payload["metadata"].get("city"),
        "wmo": payload["metadata"].get("source_station_wmo", payload["metadata"].get("wmo")),
        "station_match_quality": payload["metadata"].get("station_match_quality"),
        "temperature_source": "NOAA_GSOD" if use_station else "NASA_POWER",
        "noaa_valid_years": noaa["valid_years"] if noaa else 0,
        "noaa_valid_days": noaa["valid_days"] if noaa else 0,
        "grid_lat": era["grid_lat"],
        "grid_lon": era["grid_lon"],
        "annual_temp_c": yearly["avg_temp"],
        "annual_precip_mm": yearly["total_precip"],
        "annual_cloud_pct": yearly["avg_cloud"],
        "daily_points": len(daily_climatology),
    }
    return payload, audit


def load_catalog(root: Path, only: set[str]) -> list[tuple[Path, dict[str, Any]]]:
    station_ids = {feature["properties"]["id"] for feature in json.loads((root / "public" / "data" / "stations.geojson").read_text(encoding="utf-8"))["features"]}
    result = []
    for path in sorted((root / "public" / "data").glob("prefecture-*.json")):
        if only and path.stem not in only:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if path.stem in station_ids:
            result.append((path, payload))
    return result


def load_admin_coordinates(root: Path) -> dict[str, dict[str, str]]:
    path = root / "data" / "prefecture_city_catalog" / "admin_unit_coordinates_20260716.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["catalog_id"]: row for row in csv.DictReader(handle)}


def update_station_catalog(root: Path, updated: dict[str, dict[str, Any]]) -> None:
    path = root / "public" / "data" / "stations.geojson"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    yearly_fields = (
        "avg_temp", "total_precip", "avg_humidity", "avg_wind", "total_solar",
        "avg_cloud", "avg_opaque_cloud", "avg_apparent_temp", "avg_dew_point",
        "tourism_score_avg", "beach_score_avg", "best_tourism_months", "best_time",
        "tourism_peak_month", "data_source", "method_note", "climate_normal_period",
        "temperature_source", "gridded_source",
    )
    for feature in catalog["features"]:
        payload = updated.get(feature["properties"]["id"])
        if not payload:
            continue
        metadata = payload["metadata"]
        feature["geometry"]["coordinates"] = [float(metadata["lon"]), float(metadata["lat"])]
        for field in yearly_fields:
            if field in payload["yearly"]:
                feature["properties"][field] = payload["yearly"][field]
    encoded = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    path.write_text(encoded, encoding="utf-8")
    processed = root / "data" / "processed" / "stations.geojson"
    if processed.exists():
        processed.write_text(encoded, encoding="utf-8")


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    cache = Path(args.cache_dir)
    audit_dir = root / "audits" / "climate_normals_1991_2020_20260717"
    audit_dir.mkdir(parents=True, exist_ok=True)
    cities = load_catalog(root, set(args.only))
    if not cities:
        raise SystemExit("No matching city JSON files")

    admin_coordinates = load_admin_coordinates(root)
    for path, payload in cities:
        coordinate = admin_coordinates.get(path.stem)
        if not coordinate:
            raise SystemExit(f"Missing administrative coordinate: {path.stem}")
        payload["metadata"]["lat"] = float(coordinate["lat"])
        payload["metadata"]["lon"] = float(coordinate["lon"])
        payload["metadata"]["admin_coordinate_source"] = coordinate["coordinate_source"]

    unique_wmos = sorted({str(payload["metadata"].get("source_station_wmo") or payload["metadata"].get("wmo")) for _, payload in cities})
    noaa_results: dict[str, dict[str, Any]] = {}
    if not args.skip_noaa:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(fetch_json, noaa_url(wmo), cache / "noaa" / f"{wmo}.json"): wmo for wmo in unique_wmos}
            for future in as_completed(futures):
                wmo = futures[future]
                try:
                    noaa_results[wmo] = aggregate_noaa(future.result())
                except Exception as exc:
                    noaa_results[wmo] = {"eligible": False, "valid_years": 0, "valid_days": 0, "profiles": {}, "error": str(exc)}

    era_results: dict[str, dict[str, Any]] = {}
    def fetch_power(entry: tuple[Path, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        path, payload = entry
        lat = float(payload["metadata"]["lat"])
        lon = float(payload["metadata"]["lon"])
        coordinate_source = str(payload["metadata"].get("admin_coordinate_source", "catalog"))
        cache_name = f"{path.stem}.json" if coordinate_source == "catalog" else f"{path.stem}_{lat:.4f}_{lon:.4f}.json"
        response = fetch_json(power_url(lat, lon), cache / "power" / cache_name)
        return path.stem, aggregate_power(response)

    batch_errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_power, entry): entry for entry in cities}
        completed_batches = 0
        for future in as_completed(futures):
            entry = futures[future]
            try:
                stem, era = future.result()
                era_results[stem] = era
                completed_batches += 1
                print(f"NASA POWER {completed_batches}/{len(cities)} cities", flush=True)
            except Exception as exc:
                batch_errors.append({"files": entry[0].name, "error": str(exc)})
                print(f"NASA POWER ERROR: {batch_errors[-1]}", flush=True)
    if batch_errors:
        (audit_dir / "nasa_power_errors.json").write_text(json.dumps(batch_errors, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise SystemExit(f"NASA POWER download failed for {len(batch_errors)} cities; rerun to retry cached-missing cities")

    audits: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    updated_payloads: dict[str, dict[str, Any]] = {}
    def process(entry: tuple[Path, dict[str, Any]]) -> tuple[Path, dict[str, Any], dict[str, Any]]:
        path, payload = entry
        metadata = payload["metadata"]
        era = era_results[path.stem]
        wmo = str(metadata.get("source_station_wmo") or metadata.get("wmo"))
        updated, audit = build_city(payload, era, noaa_results.get(wmo))
        return path, updated, audit

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process, entry): entry[0] for entry in cities}
        for future in as_completed(futures):
            source_path = futures[future]
            try:
                path, payload, audit = future.result()
                encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
                path.write_text(encoded, encoding="utf-8")
                processed = root / "data" / "processed" / path.name
                if processed.exists():
                    processed.write_text(encoded, encoding="utf-8")
                updated_payloads[path.stem] = payload
                audits.append(audit)
                print(f"[{len(audits)}/{len(cities)}] {path.stem}: {audit['temperature_source']}", flush=True)
            except Exception as exc:
                errors.append({"file": str(source_path), "error": str(exc)})
                print(f"ERROR {source_path.name}: {exc}", flush=True)

    fieldnames = list(audits[0].keys()) if audits else ["catalog_id"]
    with (audit_dir / "city_source_audit.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted(audits, key=lambda row: str(row.get("catalog_id"))))
    update_station_catalog(root, updated_payloads)
    curve_signatures = {
        row_id: tuple((point["temp_avg"], point["cloud"], point["precip_31d"]) for point in payload["daily_climatology"])
        for row_id, payload in updated_payloads.items()
    }
    summary = {
        "period": "1991-2020",
        "requested_cities": len(cities),
        "completed_cities": len(audits),
        "errors": errors,
        "temperature_source_counts": {key: sum(row["temperature_source"] == key for row in audits) for key in ("NOAA_GSOD", "NASA_POWER")},
        "coordinate_source_counts": dict(sorted({
            str(payload["metadata"].get("admin_coordinate_source")): sum(
                other["metadata"].get("admin_coordinate_source") == payload["metadata"].get("admin_coordinate_source")
                for other in updated_payloads.values()
            )
            for payload in updated_payloads.values()
        }.items())),
        "unique_daily_climate_curves": len(set(curve_signatures.values())),
        "daily_point_failures": [row["catalog_id"] for row in audits if row["daily_points"] != 365],
        "cloud_category_daily_sum_failures": [
            row_id for row_id, payload in updated_payloads.items()
            if any(abs(sum(float(payload["cloud_category_climatology"][key].split(",")[idx]) for key in CLOUD_CATEGORY_KEYS) - 100) > 0.11 for idx in range(365))
        ],
        "cloud_category_monthly_sum_failures": [
            row_id for row_id, payload in updated_payloads.items()
            if any(abs(sum(float(payload["monthly"][str(month)]["cloud_categories"][key]["pct"]) for key in CLOUD_CATEGORY_KEYS) - 100) > 0.11 for month in range(1, 13))
        ],
        "bounds_failures": [row["catalog_id"] for row in audits if not (-45 <= row["annual_temp_c"] <= 35 and 0 <= row["annual_precip_mm"] <= 12000 and 0 <= row["annual_cloud_pct"] <= 100)],
    }
    (audit_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors or summary["daily_point_failures"] or summary["cloud_category_daily_sum_failures"] or summary["cloud_category_monthly_sum_failures"] or summary["bounds_failures"]:
        raise SystemExit(f"Climate normal build failed validation: {summary}")


if __name__ == "__main__":
    main()
