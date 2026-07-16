# WeatherWhisper

WeatherWhisper is a China climate visualization site designed as a climate-comfort annual climate page.

## Current scope
The site now uses **339 climate-page entries**: 333 mainland Chinese prefecture-level administrative units（293 prefecture-level cities, 7 prefectures, 30 autonomous prefectures and 3 leagues）, plus Beijing, Tianjin, Shanghai, Chongqing, Hong Kong and Macau. The catalog excludes urban districts, counties and county-level cities.

Core climate modules:

1. 1991–2020逐日高温、低温、平均温度与平均体感温度常年值
2. 一日内不同时段平均温度热力图（固定绝对摄氏温度色阶）
3. 逐日平均云量
4. 逐日湿日概率和中心31日累计降水常年值
5. 逐日相对湿度、露点与体感温度
6. 逐日风速
7. 旅游指数、沙滩/泳池参考指数及计算方法说明
8. 地级行政区切换、月份切换、地图浏览和月度数据表

## Data source
The main climate curves use WMO-standard 1991–2020 normals built from variable-specific sources. NOAA GSOD direct-station observations supply temperature and dew point when the station match and coverage audit pass; NASA POWER/MERRA-2 supplies gap-free precipitation, cloud, wind and solar fields for every administrative centre. OneBuilding EPW/TMY data is retained only for the separately labelled month-by-hour typical-year heatmap.

- `scripts/build_climate_normals.py`: fetches/caches source data and builds 365-point daily normals for all 339 entries
- `scripts/fetch_admin_coordinates.py`: builds the reproducible administrative-centre coordinate table
- `scripts/build_prefecture_city_catalog.py`: rebuilds the 333-unit catalog and admin-unit-to-station aliases
- `scripts/processor.py`: processes EPW files into monthly/hourly climate metrics
- `data/prefecture_city_catalog/`: admin-unit list and admin-unit-to-station match tables
- `data/processed/`: processed station JSON files and generated admin-unit aliases
- `public/data/`: static JSON served by Vite / GitHub Pages
- `audits/prefecture_admin_unit_expansion_20260711/`: validation outputs and match audit
- `audits/climate_normals_1991_2020_20260716/`: climate-source, coverage and WeatherSpark comparison audit

The climate atlas reference page is used for information architecture and scoring-threshold inspiration. The project does **not** copy climate atlas proprietary raw data.

## Processing method
Run the full 339-entry rebuild:

```bash
python3 scripts/build_prefecture_city_catalog.py
```

For station-only processing without rebuilding admin-unit aliases:

```bash
python3 scripts/processor.py
```

The climate-normal builder derives:

- 365 day-of-year normals, smoothed with a centred 15-day circular window
- centred 31-day climatological precipitation totals
- monthly and annual summaries derived from the same 1991–2020 inputs
- direct-station temperature/dew point only when at least 10 effective years and 3,000 valid days pass audit
- climate-comfort tourism scores from apparent temperature, cloud score and wet-day probability

Run the climate-normal rebuild after the base catalog exists:

```bash
python3 scripts/fetch_admin_coordinates.py
python3 scripts/build_climate_normals.py
```

Tourism score formula:

```text
Tourism score = 0.50 * apparent-temperature score
              + 0.25 * cloud score
              + 0.25 * precipitation score
```

Daytime hours are 08:00–21:00 local time. Temperature thresholds follow the reference screenshot: below 10°C = 0, 18°C = 9, 24°C = 10, 27°C = 9, 32°C and above = 1, with linear interpolation between points.

## Admin-unit catalog validation
The 333-unit builder hard-stops unless all conditions pass:

- exactly 333 entries
- type counts are 293 地级市, 7 地区, 30 自治州 and 3 盟
- no duplicate admin-unit names
- province-level table counts equal parsed admin-unit counts
- every map feature has one matching `public/data/prefecture-*.json` file

The 2026-07-16 climate-normal rebuild completed all 339 entries with 365 points each. It uses 130 audited NOAA station temperature series and 209 NASA POWER temperature series; gridded cloud, rainfall, wind and solar fields cover all entries. Nearby cities can still share a MERRA-2 grid cell, and Xi'an/Xianyang share the same qualified NOAA station, so the project records source coordinates and does not manufacture artificial city differences.

## Local development

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
```

## Notes

- The default lead city is Guangzhou (`prefecture-guangzhou`).
- Map points represent prefecture-level administrative centres. Main curves are 1991–2020 normals; the hourly heatmap remains a separate OneBuilding typical-year reference.
- If a direct station becomes available for a fallback admin unit, add/download its EPW file and update the alias mapping in `scripts/build_prefecture_city_catalog.py`.
