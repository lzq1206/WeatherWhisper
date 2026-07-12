# WeatherWhisper

WeatherWhisper is a China climate visualization site designed as a WeatherSpark-style annual climate page.

## Current scope
The site now uses a catalog of **333 mainland Chinese prefecture-level administrative units（地级行政区划单位）**: 293 prefecture-level cities, 7 prefectures, 30 autonomous prefectures and 3 leagues. The catalog deliberately excludes urban districts, counties, county-level cities, province-level municipalities and special administrative regions.

Core climate modules:

1. 月均高温、低温、平均温度与平均体感温度
2. 一日内不同时段平均温度热力图（固定绝对摄氏温度色阶）
3. 月度云量结构（晴天 / 大部分晴天 / 部分多云 / 大部分多云 / 阴天）
4. 降水概率和月降水量
5. 湿度舒适水平（按露点）与体感温度
6. 风速和主导风向
7. 旅游指数、沙滩/泳池参考指数及计算方法说明
8. 地级行政区切换、月份切换、地图浏览和月度数据表

## Data source
The repository uses locally processed EPW weather files from OneBuilding / Climate.OneBuilding.org and a reproducible prefecture-level admin-unit catalog:

- `scripts/build_prefecture_city_catalog.py`: rebuilds the 333-unit catalog and admin-unit-to-station aliases
- `scripts/processor.py`: processes EPW files into monthly/hourly climate metrics
- `data/prefecture_city_catalog/`: admin-unit list and admin-unit-to-station match tables
- `data/processed/`: processed station JSON files and generated admin-unit aliases
- `public/data/`: static JSON served by Vite / GitHub Pages
- `audits/prefecture_admin_unit_expansion_20260711/`: validation outputs and match audit

The WeatherSpark reference page is used for information architecture and scoring-threshold inspiration. The project does **not** copy WeatherSpark proprietary raw data.

## Processing method
Run the full 333-unit rebuild:

```bash
python3 scripts/build_prefecture_city_catalog.py
```

For station-only processing without rebuilding admin-unit aliases:

```bash
python3 scripts/processor.py
```

The processor derives:

- monthly average daily high / low / mean temperatures
- monthly apparent temperature and dew-point based humidity comfort classes
- hourly-by-month temperature grids
- monthly cloudiness category percentages
- wet-day precipitation probability (`daily precipitation >= 1 mm`)
- monthly wind speed and vector-averaged dominant wind direction
- WeatherSpark-style tourism scores from daytime hourly apparent temperature, cloud score, and precipitation score

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

Some admin units do not have direct OneBuilding EPW stations. In those cases, WeatherWhisper uses a documented same-province or nearby representative station and records the source in `station_match_quality`, `source_station_id`, and the audit CSV.

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
- Map points represent prefecture-level admin units; climate metrics come from their matched weather stations.
- If a direct station becomes available for a fallback admin unit, add/download its EPW file and update the alias mapping in `scripts/build_prefecture_city_catalog.py`.
