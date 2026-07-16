# WeatherWhisper station precision audit — 2026-07-16

## Goal

Add Beijing, Tianjin, Shanghai, Chongqing, Hong Kong and Macau to search / grouped selection, and replace broad province-capital reuse with the most specific available OneBuilding city station.

## Inputs

- OneBuilding China, Hong Kong and Macau index pages
- Locally cached EPW / STAT source files under `data/raw/`
- 333-unit mainland prefecture catalog plus 6 municipality / SAR supplemental entries

## Results

- Web catalog entries: 339
- Unique catalog IDs: 339
- Direct same-city matches: 180
- City-alias fallback matches: 109
- Province-capital fallback matches: 50
- Unique source stations / unique climate payloads: 187
- Missing per-entry JSON files: 0
- Entries without all 12 months: 0
- Cross-region station-file matches: 0
- Beijing / Tianjin / Shanghai / Chongqing / Hong Kong / Macau: all six use direct, distinct source stations
- WeatherSpark string occurrences in source and published data: 0

## Precision controls

Station matching is constrained by the province/region code embedded in OneBuilding filenames. This prevents same-name cross-province collisions such as Guangxi Yulin (玉林) being assigned Shaanxi Yulin (榆林) data.

## Build verification

`npm run build` completed successfully. The generated `dist/data/stations.geojson` contains 339 entries.

## Remaining limitation

OneBuilding does not provide a direct EPW city station for every one of the 339 administrative entries. Therefore 159 entries remain explicitly marked as same-province fallback matches. Producing 339 genuinely independent series would require a separate interpolation pipeline or another gridded observational dataset; duplicating or relabeling a nearby station is not treated as higher precision.
