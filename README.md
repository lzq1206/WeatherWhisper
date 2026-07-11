# WeatherWhisper

WeatherWhisper is a China climate visualization site designed as a WeatherSpark-style annual climate page.

## Current scope
The page now supports the core modules requested for the climate topic:

1. 月均高温、低温、平均温度与平均体感温度
2. 一日内不同时段平均温度热力图
3. 月度云量结构（晴天 / 大部分晴天 / 部分多云 / 大部分多云 / 阴天）
4. 降水概率和月降水量
5. 湿度舒适水平（按露点）与体感温度
6. 风速和主导风向
7. 旅游指数、沙滩/泳池参考指数及计算方法说明
8. 月份切换、站点切换、地图浏览和月度数据表

## Data source
The repository uses locally processed EPW weather files from OneBuilding / Climate.OneBuilding.org:

- `data/raw/`: source EPW / STAT files
- `data/processed/`: processed station JSON files
- `public/data/`: static JSON served by Vite / GitHub Pages

The WeatherSpark reference page is used for information architecture and scoring-threshold inspiration. The project does **not** copy WeatherSpark proprietary raw data.

## Processing method
Run:

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

Tourism score formula used in this repository:

```text
Tourism score = 0.50 * apparent-temperature score
              + 0.25 * cloud score
              + 0.25 * precipitation score
```

Daytime hours are 08:00–21:00 local time. Temperature thresholds follow the reference screenshot: below 10°C = 0, 18°C = 9, 24°C = 10, 27°C = 9, 32°C and above = 1, with linear interpolation between points.


## Nationwide China coverage plan

The repository now keeps a validated catalog of mainland China prefecture-level administrative units in `data/china_prefecture_units.json`. The catalog contains 337 entries: 4 municipalities plus the 333 non-municipality prefecture-level units requested for nationwide coverage. It intentionally excludes city districts, counties, and county-level cities so station expansion does not accidentally duplicate district-level names as prefecture-level cities.

Validate the catalog before adding more stations:

```bash
python3 scripts/validate_prefecture_units.py
```

Download climate ZIPs in small, polite batches to avoid rate limiting. Existing extracted `.epw`/`.stat` files are skipped by default, so reruns are safe:

```bash
python3 scripts/download_major_cities.py --batch-size 10 --batch-index 0 --delay 5
python3 scripts/download_major_cities.py --batch-size 10 --batch-index 1 --delay 5
python3 scripts/processor.py
```

When expanding the `TARGETS` list, map one representative OneBuilding station ZIP to each prefecture-level unit from the catalog and prefer the unit's principal urban weather station. Do not add district names (for example `东城`, `宝山`, `双流`) as separate cities; those may appear in station filenames but should be normalized to their parent prefecture-level unit for display.

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

- The site is static and deploys cleanly with Vite.
- The default lead station remains Shanghai-Baoshan (`583620`), with major China / East Asia stations available from the station switcher and map.
- If a new city is needed, add/download its EPW file under `data/raw/` and rerun `scripts/processor.py`.
