# Station quality re-audit — 2026-07-16

## Objective

Replace the anomalous Sanya source with Sanya Phoenix International Airport and
audit all multi-candidate/direct matches before rebuilding the 339-entry web
catalog.

## Inputs and rules

- OneBuilding China/Hong Kong/Macau EPW inventory.
- Published 339-entry catalog from commit `184433f` as the before version.
- City and station coordinates, EPW hourly dry-bulb temperature, relative
  humidity, total/opaque sky cover, visibility, and precipitation.
- Candidate order retains geographic intent. Within the same WMO, the newest
  available TMYx period is preferred. A different WMO requires explicit audit
  evidence; airports are not preferred automatically.

## Audited cross-station replacements

| Administrative unit | Before | After | Evidence |
| --- | --- | --- | --- |
| 三亚市 | Sanya 599480 | Sanya Phoenix Intl AP 574941 | Cloud 85.1% → 59.6%, temperature 23.22°C → 26.52°C, RH 89.67% → 77.76%; Phoenix is 11.9 km from the city coordinate. |
| 白城市 | mislabeled Baicheng 516330 | Baicheng 509360 | 516330 coordinates are about 3,286 km from Baicheng; 509360 is about 1.5 km away. |
| 甘孜藏族自治州 | Garze 561460 | Kangding 563740 | The web unit is represented by its prefectural seat, Kangding; the former station was about 256 km from the seat. |
| 菏泽市 | Jinan fallback 548230 | Heze Caozhou 549060 | A direct same-city station is available and supersedes the provincial fallback. |

Luoyang is explicitly pinned to 570730 because it is about 6 km from the city
coordinate, versus about 52 km for the other same-name 570780 candidate. This
does not change its prior published WMO.

## System-level corrections

- Processing now emits one series per WMO and chooses the newest period before
  calculating the JSON metrics. This removes filesystem-order/last-writer-wins
  behavior when CSWD and several TMYx versions coexist.
- Catalog matching preserves the ordered geographic candidate list and upgrades
  only within a physical station unless an audited override exists.
- Published entries using 2011–2025 files increased from 222 to 267. CSWD-based
  entries decreased from 62 to 17.

## Validation results

- 339 GeoJSON features and 339 unique catalog IDs.
- Every feature has a corresponding JSON file with 12 monthly records.
- 188 unique source stations; 176 direct matches, 4 audited direct overrides,
  109 city-alias fallbacks, and 50 provincial-capital fallbacks.
- No direct or audited-direct station is more than 80 km from its administrative
  unit coordinate; the largest observed direct distance is about 49.6 km.
- No published entry has annual mean cloud cover above 80% or annual mean
  relative humidity above 85% after the rebuild.
- Fourteen entries still inherit visibility below 2 km from seven older source
  stations. These values are retained and not silently corrected because no
  demonstrably better same-city source was available.

## Files

- `multi_station_candidate_metrics_20260716.csv`: hourly-derived metrics for
  cities with multiple station candidates.
- `prefecture_admin_unit_station_matches_20260716v2.csv`: final city-to-station
  mapping and coordinates.
- `summary.json`: final catalog and match-quality counts.

## Remaining limitation

OneBuilding does not provide an independent station for all 339 administrative
units. The 159 fallback entries remain explicitly labeled; replacing them with
city-specific data requires a gridded climate product or a documented spatial
interpolation layer.
