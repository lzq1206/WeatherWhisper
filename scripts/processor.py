import os
import pandas as pd
import json
import glob
import math
import re
from typing import Dict, Iterable, Tuple

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
PROCESSED_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "..", "public", "data")

CLOUD_CATEGORIES = [
    ("clear", "晴天", 0, 20),
    ("mostly_clear", "大部分晴天", 20, 40),
    ("partly_cloudy", "部分多云", 40, 60),
    ("mostly_cloudy", "大部分多云", 60, 80),
    ("overcast", "阴天", 80, 101),
]

DEWPOINT_CATEGORIES = [
    ("dry", "干燥", -100, 13),
    ("comfortable", "舒适", 13, 16),
    ("humid", "潮湿", 16, 18),
    ("muggy", "闷热", 18, 21),
    ("oppressive", "闷热难受", 21, 24),
    ("miserable", "极为难受", 24, 100),
]

DIRECTION_LABELS = [
    "北", "东北偏北", "东北", "东北偏东", "东", "东南偏东", "东南", "东南偏南",
    "南", "西南偏南", "西南", "西南偏西", "西", "西北偏西", "西北", "西北偏北",
]


def parse_epw_location(first_line):
    parts = first_line.split(',')
    return {
        "city": parts[1].strip(),
        "state": parts[2].strip(),
        "country": parts[3].strip(),
        "wmo": parts[5].strip(),
        "lat": float(parts[6]),
        "lon": float(parts[7]),
        "tz": float(parts[8]),
        "elev": float(parts[9])
    }


def normalize_city_name(raw_city):
    city = str(raw_city).strip()
    zh_aliases = {
        'Anqing': '安庆',
        'Bengbu': '蚌埠',
        'Dangshan': '砀山',
        'Dongcheng': '东城',
        'Fuyang': '阜阳',
        'Huang': '黄山',
        'Huoshan': '霍山',
        'Beijing': '北京',
        'Peking': '北京',
        'Shanghai': '上海',
        'Guangzhou': '广州',
        'Canton': '广州',
        'Shenzhen': '深圳',
        'Tianjin': '天津',
        'Chongqing': '重庆',
        'Chengdu': '成都',
        'Hangzhou': '杭州',
        'Wuhan': '武汉',
        'Nanjing': '南京',
        'Ningbo': '宁波',
        'Qingdao': '青岛',
        'Dalian': '大连',
        'Fuzhou': '福州',
        'Xiamen': '厦门',
        'Changsha': '长沙',
        'Zhengzhou': '郑州',
        'Hefei': '合肥',
        'Changchun': '长春',
        'Shenyang': '沈阳',
        'Harbin': '哈尔滨',
        'Kunming': '昆明',
        'Nanning': '南宁',
        'Taiyuan': '太原',
        'Shijiazhuang': '石家庄',
        'Suzhou': '苏州',
        'Jinan': '济南',
        'Nanchang': '南昌',
        'Mianyang': '绵阳',
        'Xuzhou': '徐州',
        'Yantai': '烟台',
        'Weifang': '潍坊',
        'Taipei': '台北',
        'Urumqi': '乌鲁木齐',
        'Xian': '西安',
        'XiAn': '西安',
        "Xi'an": '西安',
        'Hong Kong': '香港',
        'Macau': '澳门',
    }
    normalized = city.lower().replace("'", '')
    for old, new in zh_aliases.items():
        if old.lower().replace("'", '') in normalized:
            return new
    aliases = {
        'Peking': 'Beijing',
        'Tientsin': 'Tianjin',
        'Canton': 'Guangzhou',
        'Chungking': 'Chongqing',
        'Tsinan': 'Jinan',
        'Mukden': 'Shenyang',
        'Amoy': 'Xiamen',
        'Foochow': 'Fuzhou',
        'Soochow': 'Suzhou',
        'Hangchow': 'Hangzhou',
        'Nanking': 'Nanjing',
        'Hankow': 'Wuhan',
        'Harbin-Taiping': 'Harbin',
        'Chengdu-Shuangliu': 'Chengdu',
        'Chengdu-Wenjiang': 'Chengdu',
        'Shanghai-Baoshan': 'Shanghai',
        'Tianjin-Binhai': 'Tianjin',
        'Guangzhou-Baiyun': 'Guangzhou',
        'Shenzhen-Baoan': 'Shenzhen',
        'Changsha-Huanghua': 'Changsha',
        'Changsha-Datuopu': 'Changsha',
        'Jinan.Tsinan': 'Jinan',
    }
    for old, new in aliases.items():
        if old.lower() in city.lower():
            return new
    city = re.split(r'[\.-]', city)[0].strip()
    return city or str(raw_city).strip()


def safe_float(parts: list[str], idx: int, default: float | None = None, missing: Iterable[str] = ('999', '9999', '99999')) -> float | None:
    try:
        value = parts[idx].strip()
    except Exception:
        return default
    if value in set(missing) or value == '':
        return default
    try:
        return float(value)
    except Exception:
        return default


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def interp_piecewise(x: float, points: list[Tuple[float, float]]) -> float:
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            if x1 == x0:
                return y1
            ratio = (x - x0) / (x1 - x0)
            return y0 + ratio * (y1 - y0)
    return points[-1][1]


def apparent_temperature(temp_c: float, rh: float, wind_mps: float) -> float:
    """Approximate perceived temperature using heat-index and wind-chill branches."""
    if temp_c >= 27 and rh >= 40:
        t = temp_c * 9 / 5 + 32
        r = rh
        hi_f = (-42.379 + 2.04901523 * t + 10.14333127 * r - 0.22475541 * t * r
                - 0.00683783 * t * t - 0.05481717 * r * r
                + 0.00122874 * t * t * r + 0.00085282 * t * r * r
                - 0.00000199 * t * t * r * r)
        return (hi_f - 32) * 5 / 9
    wind_kmh = wind_mps * 3.6
    if temp_c <= 10 and wind_kmh > 4.8:
        return 13.12 + 0.6215 * temp_c - 11.37 * (wind_kmh ** 0.16) + 0.3965 * temp_c * (wind_kmh ** 0.16)
    return temp_c


def cloud_score(cloud_pct: float) -> float:
    """WeatherSpark-like cloud score: clear=10, mostly-clear≈9, overcast=1."""
    cloud_pct = clamp(cloud_pct, 0, 100)
    if cloud_pct <= 25:
        return 10 - (cloud_pct / 25) * 1
    return max(1, 9 - ((cloud_pct - 25) / 75) * 8)


def precip_score(precip_mm: float) -> float:
    """WeatherSpark-like precipitation score: no rain=10, trace≈9, >=1mm=0."""
    precip_mm = max(0.0, precip_mm)
    if precip_mm == 0:
        return 10
    if precip_mm >= 1:
        return 0
    return max(0, 9 * (1 - precip_mm))


def tourism_temperature_score(apparent_c: float) -> float:
    """Tourism temperature score from screenshot thresholds."""
    return clamp(interp_piecewise(apparent_c, [
        (-50, 0),
        (10, 0),
        (18, 9),
        (24, 10),
        (27, 9),
        (32, 1),
        (60, 1),
    ]), 0, 10)


def beach_temperature_score(apparent_c: float) -> float:
    return clamp(interp_piecewise(apparent_c, [
        (-50, 0),
        (18, 0),
        (24, 9),
        (28, 10),
        (32, 9),
        (38, 1),
        (60, 1),
    ]), 0, 10)


def wind_direction_text(deg: float | None) -> str:
    if deg is None or math.isnan(deg):
        return '—'
    idx = int((deg % 360) / 22.5 + 0.5) % 16
    return DIRECTION_LABELS[idx]


def vector_wind_direction(sub: pd.DataFrame) -> float | None:
    valid = sub.dropna(subset=['WindDirection', 'WindSpeed'])
    if valid.empty:
        return None
    radians = valid['WindDirection'].astype(float).map(math.radians)
    weights = valid['WindSpeed'].astype(float).clip(lower=0)
    if float(weights.sum()) <= 0:
        weights = pd.Series([1.0] * len(valid), index=valid.index)
    x = float((radians.map(math.sin) * weights).sum())
    y = float((radians.map(math.cos) * weights).sum())
    if x == 0 and y == 0:
        return None
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def pct_by_category(values: pd.Series, categories: list[Tuple[str, str, float, float]]) -> dict:
    total = len(values.dropna())
    result = {}
    for key, label, lo, hi in categories:
        if total == 0:
            pct = 0.0
        elif hi >= 101:
            pct = float(((values >= lo) & (values <= 100)).sum()) / total * 100
        else:
            pct = float(((values >= lo) & (values < hi)).sum()) / total * 100
        result[key] = {'label': label, 'pct': round(pct, 1)}
    return result


def get_climate_description(stats):
    t = stats['avg_temp']
    p = stats['total_precip']
    desc = ""
    if t > 20:
        desc += "热带/亚热带气候，全年气温较高。"
    elif t > 10:
        desc += "温带气候，四季分明。"
    else:
        desc += "寒冷气候，冬季漫长。"
    if p > 1500:
        desc += " 降水极丰沛。"
    elif p > 800:
        desc += " 湿润多雨。"
    elif p > 400:
        desc += " 半湿润地区。"
    else:
        desc += " 干旱/半干旱地区。"
    return desc


def months_to_text(months):
    if not months:
        return '四季皆宜'
    months = sorted(set(int(m) for m in months))
    if len(months) == 12:
        return '全年'
    ranges = []
    start = prev = months[0]
    for m in months[1:]:
        if m == prev + 1:
            prev = m
            continue
        ranges.append((start, prev))
        start = prev = m
    ranges.append((start, prev))
    return '、'.join([f'{a}-{b}月' if a != b else f'{a}月' for a, b in ranges])


def tourism_comfort_label(score: float) -> str:
    if score >= 7.5:
        return '最佳'
    if score >= 6.2:
        return '舒适'
    if score >= 4.5:
        return '可接受'
    return '偏不舒适'


def parse_epw(epw_path: str) -> tuple[dict, pd.DataFrame]:
    with open(epw_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    metadata = parse_epw_location(lines[0])
    rows = []
    for line in lines:
        if not re.match(r'^\d{4},', line):
            continue
        parts = line.strip().split(',')
        if len(parts) < 34:
            continue
        temp = safe_float(parts, 6)
        dew = safe_float(parts, 7)
        rh = safe_float(parts, 8)
        wind_dir = safe_float(parts, 20)
        wind_speed = safe_float(parts, 21)
        total_cloud = safe_float(parts, 22)
        opaque_cloud = safe_float(parts, 23, default=total_cloud)
        visibility = safe_float(parts, 24, default=None)
        precip = safe_float(parts, 33, default=0.0)
        solar = safe_float(parts, 13, default=0.0)
        if temp is None or rh is None:
            continue
        total_cloud_pct = clamp((total_cloud or 0) * 10, 0, 100)
        opaque_cloud_pct = clamp((opaque_cloud if opaque_cloud is not None else total_cloud or 0) * 10, 0, 100)
        wind_speed = wind_speed if wind_speed is not None else 0.0
        apparent = apparent_temperature(temp, rh, wind_speed)
        cloud_s = cloud_score(opaque_cloud_pct)
        precip_s = precip_score(precip or 0.0)
        temp_s = tourism_temperature_score(apparent)
        beach_s = beach_temperature_score(apparent)
        rows.append({
            'Year': int(parts[0]),
            'Month': int(parts[1]),
            'Day': int(parts[2]),
            'Hour': int(parts[3]) - 1 if parts[3].strip().isdigit() else 0,
            'Temp': temp,
            'DewPoint': dew if dew is not None else temp,
            'Humidity': rh,
            'ApparentTemp': apparent,
            'Solar': solar or 0.0,
            'WindDirection': wind_dir,
            'WindSpeed': wind_speed,
            'Cloud': total_cloud_pct,
            'OpaqueCloud': opaque_cloud_pct,
            'Visibility': visibility,
            'Precip': precip or 0.0,
            'CloudScore': cloud_s,
            'PrecipScore': precip_s,
            'TourismTempScore': temp_s,
            'BeachTempScore': beach_s,
            'TourismScoreHourly': 0.50 * temp_s + 0.25 * cloud_s + 0.25 * precip_s,
            'BeachScoreHourly': 0.50 * beach_s + 0.25 * cloud_s + 0.25 * precip_s,
        })
    return metadata, pd.DataFrame(rows)


def process_station(epw_path):
    print(f"Processing {epw_path}...")
    metadata, df = parse_epw(epw_path)
    station_id = metadata['wmo']
    if df.empty:
        return None

    daily = df.groupby(['Month', 'Day'], as_index=False).agg(
        temp_avg=('Temp', 'mean'),
        temp_max=('Temp', 'max'),
        temp_min=('Temp', 'min'),
        apparent_avg=('ApparentTemp', 'mean'),
        precip=('Precip', 'sum'),
    )

    month_groups = df.groupby('Month')
    daily_groups = daily.groupby('Month')
    monthly_json: Dict[int, dict] = {}

    day_hours = df[(df['Hour'] >= 8) & (df['Hour'] <= 21)].copy()
    if day_hours.empty:
        day_hours = df.copy()

    for month in range(1, 13):
        sub = month_groups.get_group(month) if month in month_groups.groups else pd.DataFrame()
        dsub = daily_groups.get_group(month) if month in daily_groups.groups else pd.DataFrame()
        dhsub = day_hours[day_hours['Month'] == month]
        if sub.empty or dsub.empty:
            continue
        precip_days = int((dsub['precip'] >= 1.0).sum())
        days = int(dsub.shape[0])
        wdir = vector_wind_direction(sub)
        tourism_score = float(dhsub['TourismScoreHourly'].mean()) if not dhsub.empty else float(sub['TourismScoreHourly'].mean())
        beach_score = float(dhsub['BeachScoreHourly'].mean()) if not dhsub.empty else float(sub['BeachScoreHourly'].mean())
        temp_component = float(dhsub['TourismTempScore'].mean()) if not dhsub.empty else float(sub['TourismTempScore'].mean())
        cloud_component = float(dhsub['CloudScore'].mean()) if not dhsub.empty else float(sub['CloudScore'].mean())
        precip_component = float(dhsub['PrecipScore'].mean()) if not dhsub.empty else float(sub['PrecipScore'].mean())
        monthly_json[month] = {
            'temp_avg': round(float(sub['Temp'].mean()), 2),
            'temp_max': round(float(dsub['temp_max'].mean()), 2),
            'temp_min': round(float(dsub['temp_min'].mean()), 2),
            'apparent_temp_avg': round(float(sub['ApparentTemp'].mean()), 2),
            'dew_point_avg': round(float(sub['DewPoint'].mean()), 2),
            'humidity': round(float(sub['Humidity'].mean()), 2),
            'wind': round(float(sub['WindSpeed'].mean()), 2),
            'wind_dir': round(float(wdir), 1) if wdir is not None else None,
            'wind_dir_text': wind_direction_text(wdir),
            'precip': round(float(dsub['precip'].sum()), 2),
            'precip_days': precip_days,
            'precip_probability': round(precip_days / max(days, 1) * 100, 1),
            'solar': round(float(sub['Solar'].sum()), 2),
            'cloud': round(float(sub['Cloud'].mean()), 1),
            'opaque_cloud': round(float(sub['OpaqueCloud'].mean()), 1),
            'visibility': round(float(sub['Visibility'].mean()) / 1000, 1) if sub['Visibility'].notna().any() else None,
            'sunny_rate': round(max(0.0, 100.0 - float(sub['OpaqueCloud'].mean())), 1),
            'cloud_score': round(cloud_component, 1),
            'precip_score': round(precip_component, 1),
            'tourism_temp_score': round(temp_component, 1),
            'tourism_score': round(tourism_score, 1),
            'beach_score': round(beach_score, 1),
            'comfort_label': tourism_comfort_label(tourism_score),
            'cloud_categories': pct_by_category(sub['Cloud'], CLOUD_CATEGORIES),
            'humidity_comfort': pct_by_category(sub['DewPoint'], DEWPOINT_CATEGORIES),
        }

    hourly_monthly: Dict[str, Dict[str, dict]] = {}
    hourly = df.groupby(['Month', 'Hour'], as_index=False).agg(
        temp=('Temp', 'mean'),
        apparent_temp=('ApparentTemp', 'mean'),
        humidity=('Humidity', 'mean'),
        dew_point=('DewPoint', 'mean'),
        cloud=('Cloud', 'mean'),
        opaque_cloud=('OpaqueCloud', 'mean'),
        wind=('WindSpeed', 'mean'),
        precip=('Precip', 'mean'),
        tourism_score=('TourismScoreHourly', 'mean'),
    )
    for _, row in hourly.iterrows():
        m = str(int(row['Month']))
        h = str(int(row['Hour']))
        hourly_monthly.setdefault(m, {})[h] = {
            'temp': round(float(row['temp']), 2),
            'apparent_temp': round(float(row['apparent_temp']), 2),
            'humidity': round(float(row['humidity']), 1),
            'dew_point': round(float(row['dew_point']), 2),
            'cloud': round(float(row['cloud']), 1),
            'opaque_cloud': round(float(row['opaque_cloud']), 1),
            'wind': round(float(row['wind']), 2),
            'precip': round(float(row['precip']), 3),
            'tourism_score': round(float(row['tourism_score']), 1),
        }

    growing_days = int((daily['temp_avg'] > 5).sum())
    yearly_stats = {
        'avg_temp': round(float(df['Temp'].mean()), 2),
        'total_precip': round(float(daily['precip'].sum()), 2),
        'avg_humidity': round(float(df['Humidity'].mean()), 2),
        'avg_wind': round(float(df['WindSpeed'].mean()), 2),
        'total_solar': round(float(df['Solar'].sum() / 1000), 2),
        'avg_cloud': round(float(df['Cloud'].mean()), 1),
        'avg_opaque_cloud': round(float(df['OpaqueCloud'].mean()), 1),
        'avg_visibility': round(float(df['Visibility'].mean()) / 1000, 1) if df['Visibility'].notna().any() else None,
        'avg_apparent_temp': round(float(df['ApparentTemp'].mean()), 2),
        'avg_dew_point': round(float(df['DewPoint'].mean()), 2),
        'growing_season': growing_days,
        'water_temp': round(float(df['Temp'].mean() + 1.5), 1),
        'solar_energy': round(float(df['Solar'].sum() / 1000 * 0.15), 2),
        'data_source': 'OneBuilding Climate.OneBuilding.org EPW / TMYx-CSWD processed locally',
        'method_note': 'Monthly high/low are mean daily high/low; precipitation probability is wet days (>=1 mm/day); tourism score uses WeatherSpark-style 8:00-21:00 hourly apparent-temperature, cloud, and precipitation component scores.',
    }

    yearly_scores = [(s['tourism_score'], int(m)) for m, s in monthly_json.items()]
    yearly_scores.sort(reverse=True)
    top_months = [month for _, month in yearly_scores[:4] if month]
    comfy_months = [int(m) for m, s in monthly_json.items() if s['tourism_score'] >= 6.2]
    yearly_stats['tourism_score_avg'] = round(sum(s['tourism_score'] for s in monthly_json.values()) / max(len(monthly_json), 1), 1)
    yearly_stats['beach_score_avg'] = round(sum(s['beach_score'] for s in monthly_json.values()) / max(len(monthly_json), 1), 1)
    yearly_stats['best_tourism_months'] = months_to_text(comfy_months or top_months[:3])
    yearly_stats['best_time'] = yearly_stats['best_tourism_months']
    yearly_stats['tourism_peak_month'] = top_months[0] if top_months else None
    yearly_stats['overview'] = get_climate_description(yearly_stats)

    station_data = {
        'metadata': metadata,
        'yearly': yearly_stats,
        'monthly': monthly_json,
        'hourly_monthly': hourly_monthly,
        'methodology': {
            'source': 'OneBuilding EPW/TMYx-CSWD typical meteorological year files; WeatherSpark reference page was used for page structure and scoring thresholds, not as copied raw data.',
            'temperature': 'Monthly high/low use the average of daily highs/lows, matching the climate-page convention better than one-month extremes.',
            'cloud_categories': CLOUD_CATEGORIES,
            'humidity_categories': DEWPOINT_CATEGORIES,
            'tourism_score': {
                'analysis_hours': '08:00-21:00 local time',
                'formula': '0.50 * apparent-temperature score + 0.25 * cloud score + 0.25 * precipitation score, averaged across daytime hours by month',
                'temperature_thresholds': 'Tourism: <10°C=0, 18°C=9, 24°C=10, 27°C=9, >=32°C=1; linear interpolation between thresholds.',
                'cloud_thresholds': 'Clear=10, mostly clear≈9, overcast=1; linear interpolation.',
                'precip_thresholds': 'No precipitation=10, trace≈9, >=1 mm/hour=0; linear interpolation.',
            },
        },
    }

    with open(os.path.join(PROCESSED_DIR, f"{station_id}.json"), 'w', encoding='utf-8') as f:
        json.dump(station_data, f, ensure_ascii=False, indent=2)

    return {
        'type': 'Feature',
        'geometry': {
            'type': 'Point',
            'coordinates': [metadata['lon'], metadata['lat']],
        },
        'properties': {
            'id': station_id,
            'city': normalize_city_name(metadata['city']),
            'province': metadata['state'],
            **yearly_stats,
        },
    }


def sync_public_outputs():
    if not os.path.exists(PUBLIC_DIR):
        os.makedirs(PUBLIC_DIR, exist_ok=True)

    for filename in os.listdir(PROCESSED_DIR):
        src = os.path.join(PROCESSED_DIR, filename)
        dst = os.path.join(PUBLIC_DIR, filename)
        if os.path.isfile(src):
            with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
                fdst.write(fsrc.read())


def main():
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR, exist_ok=True)

    epw_files = sorted(glob.glob(os.path.join(RAW_DIR, "**", "*.epw"), recursive=True))
    features_by_id = {}

    for epw in epw_files:
        feat = process_station(epw)
        if feat:
            features_by_id[feat['properties']['id']] = feat

    geojson = {
        'type': 'FeatureCollection',
        'features': list(features_by_id.values()),
    }

    with open(os.path.join(PROCESSED_DIR, "stations.geojson"), 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    sync_public_outputs()

    print(f"Finished processing {len(features_by_id)} stations.")


if __name__ == "__main__":
    main()
