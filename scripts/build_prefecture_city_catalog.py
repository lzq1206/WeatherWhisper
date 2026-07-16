#!/usr/bin/env python3
"""Build WeatherWhisper catalog for all 333 mainland Chinese prefecture-level admin units.

Source boundary:
- Admin-unit list: zh.wikipedia.org/wiki/中华人民共和国地级行政区列表 main table.
- The table has exactly 333 rows: 293 prefecture-level cities, 7 prefectures,
  30 autonomous prefectures and 3 leagues. It excludes province-level
  municipalities and county/district-level units.
- Validation hard-stops unless the type counts match 293/7/30/3 and names are unique.

Climate boundary:
- Weather data come from OneBuilding / Climate.OneBuilding.org EPW/TMYx/CSWD
  files. If a prefecture-level city has no direct weather station, this script
  records a same-province fallback station in the match table.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / 'data' / 'raw'
PROCESSED_DIR = ROOT / 'data' / 'processed'
PUBLIC_DIR = ROOT / 'public' / 'data'
CATALOG_DIR = ROOT / 'data' / 'prefecture_city_catalog'
RUN_DATE = '20260716'
AUDIT_DIR = ROOT / 'audits' / f'prefecture_admin_unit_expansion_{RUN_DATE}'

PREFECTURE_LIST_URL = 'https://zh.wikipedia.org/wiki/%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E5%9C%B0%E7%BA%A7%E8%A1%8C%E6%94%BF%E5%8C%BA%E5%88%97%E8%A1%A8'
ONEBUILDING_CHINA_URL = 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/'
ONEBUILDING_HONG_KONG_URL = 'https://climate.onebuilding.org/WMO_Region_2_Asia/HKG_Hong_Kong/'
ONEBUILDING_MACAU_URL = 'https://climate.onebuilding.org/WMO_Region_2_Asia/MAC_Macau/'

SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'WeatherWhisper/OpenClaw prefecture-city catalog builder'})

SUPPLEMENTAL_WEB_UNITS = [
    {
        'province_zh': '北京市',
        'province_en': 'Beijing',
        'city_zh': '北京市',
        'city_short_zh': '北京',
        'admin_type_zh': '直辖市',
        'division_code': '110000',
        'city_en': 'Beijing',
        'wiki_title_zh': '北京市',
        'wiki_title_en': 'Beijing',
        'lat': 39.9042,
        'lon': 116.4074,
        'slug': 'beijing',
    },
    {
        'province_zh': '天津市',
        'province_en': 'Tianjin',
        'city_zh': '天津市',
        'city_short_zh': '天津',
        'admin_type_zh': '直辖市',
        'division_code': '120000',
        'city_en': 'Tianjin',
        'wiki_title_zh': '天津市',
        'wiki_title_en': 'Tianjin',
        'lat': 39.0842,
        'lon': 117.2009,
        'slug': 'tianjin',
    },
    {
        'province_zh': '上海市',
        'province_en': 'Shanghai',
        'city_zh': '上海市',
        'city_short_zh': '上海',
        'admin_type_zh': '直辖市',
        'division_code': '310000',
        'city_en': 'Shanghai',
        'wiki_title_zh': '上海市',
        'wiki_title_en': 'Shanghai',
        'lat': 31.2304,
        'lon': 121.4737,
        'slug': 'shanghai',
    },
    {
        'province_zh': '重庆市',
        'province_en': 'Chongqing',
        'city_zh': '重庆市',
        'city_short_zh': '重庆',
        'admin_type_zh': '直辖市',
        'division_code': '500000',
        'city_en': 'Chongqing',
        'wiki_title_zh': '重庆市',
        'wiki_title_en': 'Chongqing',
        'lat': 29.4316,
        'lon': 106.9123,
        'slug': 'chongqing',
    },
    {
        'province_zh': '香港特别行政区',
        'province_en': 'Hong Kong',
        'city_zh': '香港',
        'city_short_zh': '香港',
        'admin_type_zh': '特别行政区',
        'division_code': '810000',
        'city_en': 'Hong Kong',
        'wiki_title_zh': '香港',
        'wiki_title_en': 'Hong Kong',
        'lat': 22.3193,
        'lon': 114.1694,
        'slug': 'hong-kong',
    },
    {
        'province_zh': '澳门特别行政区',
        'province_en': 'Macau',
        'city_zh': '澳门',
        'city_short_zh': '澳门',
        'admin_type_zh': '特别行政区',
        'division_code': '820000',
        'city_en': 'Macau',
        'wiki_title_zh': '澳门',
        'wiki_title_en': 'Macau',
        'lat': 22.1987,
        'lon': 113.5439,
        'slug': 'macau',
    },
]

PROVINCE_ZH_TO_EN = {
    '河北省': 'Hebei', '山西省': 'Shanxi', '内蒙古自治区': 'Inner Mongolia',
    '辽宁省': 'Liaoning', '吉林省': 'Jilin', '黑龙江省': 'Heilongjiang',
    '江苏省': 'Jiangsu', '浙江省': 'Zhejiang', '安徽省': 'Anhui',
    '福建省': 'Fujian', '江西省': 'Jiangxi', '山东省': 'Shandong',
    '河南省': 'Henan', '湖北省': 'Hubei', '湖南省': 'Hunan',
    '广东省': 'Guangdong', '广西壮族自治区': 'Guangxi', '海南省': 'Hainan',
    '四川省': 'Sichuan', '贵州省': 'Guizhou', '云南省': 'Yunnan',
    '西藏自治区': 'Tibet', '陕西省': 'Shaanxi', '甘肃省': 'Gansu',
    '青海省': 'Qinghai', '宁夏回族自治区': 'Ningxia', '新疆维吾尔自治区': 'Xinjiang',
}

# OneBuilding encodes the province/region in the second filename component.
# Restrict matching to that component so same-name cities (for example 玉林/榆林)
# cannot silently borrow a station from another province.
PROVINCE_STATION_CODES = {
    '北京市': {'BJ'}, '天津市': {'TJ'}, '上海市': {'SH'}, '重庆市': {'CQ'},
    '河北省': {'HE'}, '山西省': {'SX'}, '内蒙古自治区': {'NM'},
    '辽宁省': {'LN'}, '吉林省': {'JL'}, '黑龙江省': {'HL'},
    '江苏省': {'JS'}, '浙江省': {'ZJ'}, '安徽省': {'AH'},
    '福建省': {'FJ'}, '江西省': {'JX'}, '山东省': {'SD'},
    '河南省': {'HA'}, '湖北省': {'HB'}, '湖南省': {'HN'},
    '广东省': {'GD'}, '广西壮族自治区': {'GX'}, '海南省': {'HI'},
    '四川省': {'SC'}, '贵州省': {'GZ'}, '云南省': {'YN'},
    '西藏自治区': {'XJ'}, '陕西省': {'SN'}, '甘肃省': {'GS'},
    '青海省': {'QH'}, '宁夏回族自治区': {'NX'}, '新疆维吾尔自治区': {'XZ'},
    '香港特别行政区': {'HKI'}, '澳门特别行政区': {'MA'},
}

PROVINCE_FALLBACK_CITY = {
    '河北省': 'Shijiazhuang', '山西省': 'Taiyuan', '内蒙古自治区': 'Hohhot',
    '辽宁省': 'Shenyang', '吉林省': 'Changchun', '黑龙江省': 'Harbin',
    '江苏省': 'Nanjing', '浙江省': 'Hangzhou', '安徽省': 'Hefei',
    '福建省': 'Fuzhou', '江西省': 'Nanchang', '山东省': 'Jinan',
    '河南省': 'Zhengzhou', '湖北省': 'Wuhan', '湖南省': 'Changsha',
    '广东省': 'Guangzhou', '广西壮族自治区': 'Nanning', '海南省': 'Haikou',
    '四川省': 'Chengdu', '贵州省': 'Guiyang', '云南省': 'Kunming',
    '西藏自治区': 'Lhasa', '陕西省': 'Xian', '甘肃省': 'Lanzhou',
    '青海省': 'Xining', '宁夏回族自治区': 'Yinchuan', '新疆维吾尔自治区': 'Urumqi',
}

# City-specific station aliases. Direct city-name matches are tried first.
CITY_STATION_ALIASES = {
    '佛山市': ['Guangzhou', 'Shenzhen'],
    '东莞市': ['Guangzhou', 'Shenzhen'],
    '中山市': ['Guangzhou', 'Shenzhen'],
    '珠海市': ['Guangzhou', 'Shenzhen'],
    '江门市': ['Guangzhou', 'Shenzhen'],
    '惠州市': ['Shenzhen', 'Guangzhou'],
    '肇庆市': ['Guangzhou'],
    '清远市': ['Guangzhou'],
    '云浮市': ['Guangzhou'],
    '揭阳市': ['Shantou'],
    '潮州市': ['Shantou'],
    '汕尾市': ['Shantou', 'Shenzhen'],
    '茂名市': ['Zhanjiang', 'Guangzhou'],
    '阳江市': ['Zhanjiang', 'Guangzhou'],
    '梅州市': ['Shantou', 'Guangzhou'],
    '河源市': ['Guangzhou', 'Shenzhen'],
    '韶关市': ['Guangzhou'],
    '无锡市': ['Suzhou', 'Nanjing'],
    '镇江市': ['Nanjing'],
    '扬州市': ['Nanjing'],
    '淮安市': ['Nanjing', 'Xuzhou'],
    '泰州市': ['Nanjing'],
    '宿迁市': ['Xuzhou', 'Nanjing'],
    '连云港市': ['Xuzhou', 'Yancheng'],
    '苏州市': ['Suzhou', 'Shanghai'],
    '嘉兴市': ['Hangzhou', 'Shanghai'],
    '绍兴市': ['Hangzhou', 'Ningbo'],
    '湖州市': ['Hangzhou', 'Shanghai'],
    '舟山市': ['Ningbo'],
    '台州市': ['Ningbo', 'Wenzhou'],
    '衢州市': ['Hangzhou', 'Jinhua'],
    '丽水市': ['Wenzhou', 'Jinhua'],
    '金华市': ['Yi Wu', 'Hangzhou'],
    '三明市': ['Fuzhou', 'Xiamen'],
    '莆田市': ['Fuzhou', 'Xiamen'],
    '泉州市': ['Jinjiang', 'Xiamen'],
    '漳州市': ['Xiamen', 'Fuzhou'],
    '龙岩市': ['Xiamen', 'Fuzhou'],
    '南平市': ['Fuzhou'],
    '宁德市': ['Fuzhou'],
    '淄博市': ['Jinan', 'Qingdao'],
    '枣庄市': ['Linyi', 'Jinan'],
    '东营市': ['Jinan', 'Weifang'],
    '济宁市': ['Jinan'],
    '泰安市': ['Tai An', 'Jinan'],
    '日照市': ['Linyi', 'Qingdao'],
    '德州市': ['Jinan'],
    '聊城市': ['Jinan'],
    '滨州市': ['Jinan'],
    '菏泽市': ['Heze', 'Jinan'],
    '开封市': ['Zhengzhou'],
    '平顶山市': ['Zhengzhou', 'Luoyang'],
    '安阳市': ['Zhengzhou'],
    '鹤壁市': ['Zhengzhou'],
    '新乡市': ['Zhengzhou'],
    '焦作市': ['Zhengzhou'],
    '濮阳市': ['Zhengzhou'],
    '许昌市': ['Zhengzhou'],
    '漯河市': ['Zhengzhou'],
    '三门峡市': ['Luoyang', 'Zhengzhou'],
    '商丘市': ['Zhengzhou'],
    '信阳市': ['Zhengzhou', 'Wuhan'],
    '周口市': ['Zhengzhou'],
    '驻马店市': ['Zhengzhou', 'Wuhan'],
    '鄂州市': ['Wuhan'],
    '孝感市': ['Wuhan'],
    '荆州市': ['Wuhan', 'Yichang'],
    '黄冈市': ['Wuhan'],
    '咸宁市': ['Wuhan'],
    '随州市': ['Wuhan'],
    '黄石市': ['Wuhan'],
    '十堰市': ['Wuhan'],
    '襄阳市': ['Wuhan'],
    '常德市': ['Changsha'],
    '张家界市': ['Changsha'],
    '益阳市': ['Changsha'],
    '郴州市': ['Changsha'],
    '永州市': ['Changsha'],
    '怀化市': ['Changsha'],
    '娄底市': ['Changsha'],
    '邵阳市': ['Changsha'],
    '湘潭市': ['Changsha', 'Zhuzhou'],
    '岳阳市': ['Changsha', 'Wuhan'],
    '衡阳市': ['Changsha'],
    '自贡市': ['Chengdu'],
    '攀枝花市': ['Chengdu', 'Kunming'],
    '泸州市': ['Chongqing', 'Chengdu'],
    '德阳市': ['Chengdu', 'Mianyang'],
    '广元市': ['Chengdu', 'Mianyang'],
    '遂宁市': ['Chengdu', 'Nanchong'],
    '内江市': ['Chengdu'],
    '乐山市': ['Chengdu'],
    '宜宾市': ['Chongqing', 'Chengdu'],
    '广安市': ['Chongqing', 'Chengdu'],
    '达州市': ['Chongqing', 'Chengdu'],
    '巴中市': ['Chengdu', 'Nanchong'],
    '雅安市': ['Chengdu'],
    '眉山市': ['Chengdu'],
    '资阳市': ['Chengdu'],
    '遵义市': ['Zunyi', 'Guiyang'],
    '六盘水市': ['Guiyang'],
    '安顺市': ['Guiyang'],
    '毕节市': ['Guiyang'],
    '铜仁市': ['Guiyang'],
    '曲靖市': ['Kunming'],
    '玉溪市': ['Kunming'],
    '保山市': ['Kunming'],
    '昭通市': ['Kunming'],
    '丽江市': ['Kunming'],
    '普洱市': ['Kunming'],
    '临沧市': ['Kunming'],
    '日喀则市': ['Lhasa'],
    '昌都市': ['Lhasa'],
    '林芝市': ['Nyingchi', 'Lhasa'],
    '山南市': ['Lhasa'],
    '那曲市': ['Lhasa'],
    '铜川市': ['Xian'],
    '宝鸡市': ['Xian'],
    '咸阳市': ['Xian'],
    '渭南市': ['Xian'],
    '延安市': ['Xian'],
    '汉中市': ['Xian'],
    '榆林市': ['Yulin', 'Xian'],
    '安康市': ['Xian'],
    '商洛市': ['Xian'],
    '金昌市': ['Lanzhou'],
    '白银市': ['Lanzhou'],
    '天水市': ['Lanzhou'],
    '武威市': ['Lanzhou'],
    '张掖市': ['Shandan', 'Lanzhou'],
    '平凉市': ['Lanzhou'],
    '酒泉市': ['Lanzhou'],
    '庆阳市': ['Lanzhou'],
    '定西市': ['Lanzhou'],
    '陇南市': ['Lanzhou'],
    '海东市': ['Xining'],
    '石嘴山市': ['Yinchuan'],
    '吴忠市': ['Yinchuan'],
    '固原市': ['Yinchuan'],
    '中卫市': ['Yinchuan'],
    '克拉玛依市': ['Karamay', 'Urumqi'],
    '吐鲁番市': ['Turpan', 'Urumqi'],
    '哈密市': ['Hami', 'Urumqi'],
    '秦皇岛市': ['Tianjin', 'Tangshan'],
    '承德市': ['Beijing', 'Shijiazhuang'],
    '沧州市': ['Tianjin', 'Shijiazhuang'],
    '廊坊市': ['Beijing', 'Tianjin'],
    '衡水市': ['Shijiazhuang'],
    '阳泉市': ['Taiyuan'],
    '长治市': ['Taiyuan'],
    '晋城市': ['Taiyuan'],
    '朔州市': ['Datong', 'Taiyuan'],
    '晋中市': ['Taiyuan'],
    '运城市': ['Taiyuan', 'Xian'],
    '忻州市': ['Taiyuan'],
    '临汾市': ['Taiyuan'],
    '吕梁市': ['Taiyuan'],
    '乌海市': ['Hohhot', 'Baotou'],
    '赤峰市': ['Hohhot'],
    '通辽市': ['Hohhot'],
    '鄂尔多斯市': ['Hohhot', 'Baotou'],
    '呼伦贝尔市': ['Hohhot'],
    '巴彦淖尔市': ['Hohhot', 'Baotou'],
    '乌兰察布市': ['Hohhot', 'Jining'],
    '抚顺市': ['Shenyang'],
    '本溪市': ['Shenyang'],
    '丹东市': ['Shenyang', 'Dalian'],
    '锦州市': ['Shenyang'],
    '营口市': ['Shenyang', 'Dalian'],
    '阜新市': ['Shenyang'],
    '辽阳市': ['Shenyang', 'Anshan'],
    '盘锦市': ['Shenyang'],
    '铁岭市': ['Shenyang'],
    '朝阳市': ['Shenyang'],
    '葫芦岛市': ['Shenyang'],
    '四平市': ['Changchun'],
    '辽源市': ['Changchun'],
    '通化市': ['Changchun'],
    '白山市': ['Changchun'],
    '松原市': ['Changchun'],
    '白城市': ['Changchun'],
    '齐齐哈尔市': ['Harbin'],
    '鸡西市': ['Harbin'],
    '鹤岗市': ['Harbin'],
    '双鸭山市': ['Harbin'],
    '大庆市': ['Harbin'],
    '伊春市': ['Harbin'],
    '佳木斯市': ['Harbin'],
    '七台河市': ['Harbin'],
    '牡丹江市': ['Harbin'],
    '黑河市': ['Harbin'],
    '绥化市': ['Harbin'],
}

@dataclass
class PrefectureCity:
    index: int
    province_zh: str
    province_en: str
    city_zh: str
    city_short_zh: str
    admin_type_zh: str = ''
    division_code: str = ''
    city_en: str = ''
    wiki_title_zh: str = ''
    wiki_title_en: str = ''
    lat: float | None = None
    lon: float | None = None
    slug: str = ''

@dataclass
class StationZip:
    url: str
    file: str
    station_name: str
    norm_name: str
    wmo: str
    preference: int
    region_code: str


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def ascii_text(value: str) -> str:
    return unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')


def slugify(value: str) -> str:
    text = ascii_text(value).lower().replace("'", '')
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text or 'city'


def normalize_name(value: str) -> str:
    return re.sub(r'[^a-z0-9]', '', ascii_text(value).lower().replace("'", ''))


def get_text_with_retries(url: str, *, timeout: int = 60, attempts: int = 4, sleep_base: float = 2.0) -> str:
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            resp = SESSION.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            time.sleep(sleep_base * attempt)
    raise RuntimeError(f'Failed to fetch {url} after {attempts} attempts: {last_exc}')


def clean_english_title(title: str) -> str:
    title = re.sub(r'\s*\([^)]*\)\s*', ' ', title).strip()
    title = re.sub(r'\s+', ' ', title)
    return title


def english_candidates(city: PrefectureCity) -> list[str]:
    items = []
    for raw in [city.city_en, city.wiki_title_en]:
        if not raw:
            continue
        cleaned = clean_english_title(raw)
        items.append(cleaned)
        if ',' in cleaned:
            items.append(cleaned.split(',', 1)[0].strip())
        for suffix in [' City', ' city']:
            if cleaned.endswith(suffix):
                items.append(cleaned[: -len(suffix)].strip())
        for suffix in [' Autonomous Prefecture', ' Prefecture', ' League']:
            if cleaned.endswith(suffix):
                base = cleaned[: -len(suffix)].strip()
                items.append(base)
                # Many station files use only the geographic stem, e.g. Dali,
                # Xishuangbanna, Aksu, Xilingol, instead of the full admin title.
                base = re.sub(
                    r'\b(Tibetan|Qiang|Yi|Hui|Mongol|Mongolian|Kazakh|Korean|Bai|Dai|Miao|Dong|Bouyei|Tujia|Lisu|Zhuang|Hani|Jingpo|Kirgiz)\b.*$',
                    '',
                    base,
                    flags=re.I,
                ).strip()
                if base:
                    items.append(base)
    items.extend(CITY_STATION_ALIASES.get(city.city_zh, []))
    # stable de-dup
    result = []
    seen = set()
    for item in items:
        item = item.strip()
        key = normalize_name(item)
        if item and key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def station_preference(file: str) -> int:
    if '2011-2025' in file:
        return 60
    if '2009-2023' in file:
        return 50
    if '2007-2021' in file:
        return 40
    if '2004-2018' in file:
        return 30
    if 'TMYx' in file:
        return 20
    if 'CSWD' in file:
        return 10
    return 0


def clean_station_name_from_zip(url: str) -> str:
    file = url.rsplit('/', 1)[-1]
    base = re.sub(r'\.zip$', '', file, flags=re.I)
    parts = base.split('_')
    name = '_'.join(parts[2:]) if len(parts) > 2 else base
    name = re.sub(r'\.\d{5,6}_.*$', '', name)
    name = name.replace('.', ' ').replace('-', ' ').replace('_', ' ')
    for word in ['International', 'Intl', 'AP', 'Aero', 'Airport']:
        name = re.sub(r'\b' + word + r'\b', ' ', name, flags=re.I)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def station_word_match(candidate: str, station_name: str) -> bool:
    candidate_ascii = re.escape(ascii_text(candidate).strip())
    if not candidate_ascii:
        return False
    return re.search(r'(?<![A-Za-z0-9])' + candidate_ascii + r'(?![A-Za-z0-9])', ascii_text(station_name), re.I) is not None


def fetch_prefecture_cities() -> list[PrefectureCity]:
    html = get_text_with_retries(PREFECTURE_LIST_URL, timeout=60)
    tables = pd.read_html(io.StringIO(html))
    summary_table = tables[1]
    table = tables[2]
    cities: list[PrefectureCity] = []
    index = 0
    province_count_checks: list[tuple[str, int, int]] = []

    rows_by_province = table.groupby('所属省级行政区').size().to_dict()
    for _, row in summary_table.iterrows():
        province_zh = str(row.get('省级行政区', '')).strip()
        if province_zh == '合计' or province_zh not in PROVINCE_ZH_TO_EN:
            continue
        expected = int(row.get('地级行政区', 0))
        province_count_checks.append((province_zh, expected, int(rows_by_province.get(province_zh, 0))))

    for _, row in table.iterrows():
        province_zh = str(row['所属省级行政区']).strip()
        if province_zh not in PROVINCE_ZH_TO_EN:
            continue
        name = re.sub(r'\[.*?\]', '', str(row['行政区划名称'])).strip()
        admin_type = str(row['行政区类型']).strip()
        division_code = str(row.get('区划代码[2]', '')).strip()
        if not name or name == 'nan':
            continue
        index += 1
        short = name
        for suffix in ['市', '地区', '自治州', '盟']:
            if short.endswith(suffix):
                short = short[:-len(suffix)]
                break
        cities.append(PrefectureCity(
            index=index,
            province_zh=province_zh,
            province_en=PROVINCE_ZH_TO_EN.get(province_zh, province_zh),
            city_zh=name,
            city_short_zh=short,
            admin_type_zh=admin_type,
            division_code=division_code,
        ))
    validate_prefecture_list(cities, province_count_checks)
    enrich_wiki_metadata(cities)
    assign_unique_slugs(cities)
    return cities


def validate_prefecture_list(cities: list[PrefectureCity], province_count_checks: list[tuple[str, int, int]]) -> None:
    mismatches = [item for item in province_count_checks if item[1] != item[2]]
    if mismatches:
        raise ValueError(f'Province count mismatch: {mismatches}')
    names = [city.city_zh for city in cities]
    dupes = sorted({name for name in names if names.count(name) > 1})
    type_counts: dict[str, int] = {}
    for city in cities:
        type_counts[city.admin_type_zh] = type_counts.get(city.admin_type_zh, 0) + 1
    expected_type_counts = {'地级市': 293, '地区': 7, '自治州': 30, '盟': 3}
    if len(cities) != 333:
        raise ValueError(f'Expected 333 prefecture-level admin units, got {len(cities)}')
    if dupes:
        raise ValueError(f'Duplicate prefecture-level admin-unit names: {dupes}')
    if type_counts != expected_type_counts:
        raise ValueError(f'Unexpected admin type counts: {type_counts}, expected {expected_type_counts}')


def wiki_query_zh(title: str) -> dict[str, Any] | None:
    params = {
        'action': 'query', 'format': 'json', 'redirects': 1,
        'prop': 'langlinks|coordinates', 'titles': title,
        'lllang': 'en', 'lllimit': 10, 'colimit': 10,
    }
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            resp = SESSION.get('https://zh.wikipedia.org/w/api.php', params=params, timeout=30)
            resp.raise_for_status()
            pages = resp.json().get('query', {}).get('pages', {})
            return next(iter(pages.values())) if pages else None
        except Exception as exc:
            last_exc = exc
            time.sleep(0.7 * attempt)
    print(f'[WARN] wiki metadata failed for {title}: {last_exc}', file=sys.stderr)
    return None


def wiki_query_batch(titles: list[str]) -> dict[str, dict[str, Any]]:
    params = {
        'action': 'query', 'format': 'json', 'redirects': 1,
        'prop': 'langlinks|coordinates', 'titles': '|'.join(titles),
        'lllang': 'en', 'lllimit': 'max', 'colimit': 'max',
    }
    last_exc: Exception | None = None
    for attempt in range(1, 6):
        try:
            next_params = dict(params)
            merged: dict[str, dict[str, Any]] = {}
            while True:
                resp = SESSION.get('https://zh.wikipedia.org/w/api.php', params=next_params, timeout=45)
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get('Retry-After') or (5 * attempt))
                    time.sleep(retry_after)
                    raise RuntimeError('Wikipedia API rate limited during batch query')
                resp.raise_for_status()
                payload = resp.json()
                pages = payload.get('query', {}).get('pages', {})
                for page in pages.values():
                    title = page.get('title', '')
                    if not title:
                        continue
                    existing = merged.get(title, {})
                    if page.get('langlinks'):
                        existing['langlinks'] = page['langlinks']
                    if page.get('coordinates'):
                        existing['coordinates'] = page['coordinates']
                    existing.update({k: v for k, v in page.items() if k not in {'langlinks', 'coordinates'}})
                    merged[title] = existing
                cont = payload.get('continue')
                if not cont:
                    return merged
                next_params = {**next_params, **cont}
        except Exception as exc:
            last_exc = exc
            time.sleep(2.0 * attempt)
    print(f'[WARN] wiki metadata batch failed for {titles[0]}...: {last_exc}', file=sys.stderr)
    return {}


def enrich_wiki_metadata(cities: list[PrefectureCity]) -> None:
    title_to_city = {city.city_zh: city for city in cities}
    titles = list(title_to_city.keys())
    for start in range(0, len(titles), 40):
        batch = titles[start:start + 40]
        pages = wiki_query_batch(batch)
        for title in batch:
            city = title_to_city[title]
            page = pages.get(title)
            if page and page.get('missing') is None:
                city.wiki_title_zh = page.get('title', city.city_zh)
                links = page.get('langlinks') or []
                if links:
                    city.wiki_title_en = links[0].get('*', '')
                    city.city_en = clean_english_title(city.wiki_title_en.split(',', 1)[0])
                coords = page.get('coordinates') or []
                if coords:
                    city.lat = float(coords[0].get('lat'))
                    city.lon = float(coords[0].get('lon'))
            if not city.city_en:
                # Last-resort readable but unique slug basis. This should be rare if batch metadata succeeds.
                city.city_en = city.city_short_zh
            if not city.wiki_title_zh:
                city.wiki_title_zh = city.city_zh
        # Batch rather than per-city calls, with a polite pause to avoid API limits.
        time.sleep(1.5)


def assign_unique_slugs(cities: list[PrefectureCity]) -> None:
    base_counts: dict[str, int] = {}
    for city in cities:
        base = slugify(city.city_en)
        base_counts[base] = base_counts.get(base, 0) + 1
    used = set()
    for city in cities:
        base = slugify(city.city_en)
        slug = base
        if base_counts[base] > 1:
            slug = f'{base}-{slugify(city.province_en)}'
        counter = 2
        original = slug
        while slug in used:
            slug = f'{original}-{counter}'
            counter += 1
        used.add(slug)
        city.slug = slug


def supplemental_web_units(start_index: int) -> list[PrefectureCity]:
    units: list[PrefectureCity] = []
    for offset, item in enumerate(SUPPLEMENTAL_WEB_UNITS, start=1):
        units.append(PrefectureCity(index=start_index + offset, **item))
    return units


def fetch_inventory_from_index(index_url: str) -> list[str]:
    html = get_text_with_retries(urljoin(index_url, 'index.html'), timeout=90)
    soup = BeautifulSoup(html, 'html.parser')
    return [urljoin(index_url, a['href']) for a in soup.find_all('a', href=True) if a['href'].lower().endswith('.zip')]


def fetch_onebuilding_inventory() -> list[StationZip]:
    urls: list[str] = []
    seen_urls: set[str] = set()
    for index_url in [ONEBUILDING_CHINA_URL, ONEBUILDING_HONG_KONG_URL, ONEBUILDING_MACAU_URL]:
        for url in fetch_inventory_from_index(index_url):
            if url in seen_urls:
                continue
            seen_urls.add(url)
            urls.append(url)
    inventory: list[StationZip] = []
    for url in urls:
        file = url.rsplit('/', 1)[-1]
        station = clean_station_name_from_zip(url)
        wmo_match = re.search(r'\.(\d{5,6})_', file) or re.search(r'\.(\d{5,6})\.', file)
        inventory.append(StationZip(
            url=url,
            file=file,
            station_name=station,
            norm_name=normalize_name(station),
            wmo=wmo_match.group(1) if wmo_match else '',
            preference=station_preference(file),
            region_code=file.split('_', 2)[1] if file.count('_') >= 2 else '',
        ))
    return inventory


def best_by_norm(inventory: list[StationZip]) -> dict[str, StationZip]:
    best: dict[str, StationZip] = {}
    for item in inventory:
        if not item.norm_name:
            continue
        if item.norm_name not in best or item.preference > best[item.norm_name].preference:
            best[item.norm_name] = item
    return best


def best_by_wmo(inventory: list[StationZip]) -> dict[str, StationZip]:
    best: dict[str, StationZip] = {}
    for item in inventory:
        if not item.wmo:
            continue
        if item.wmo not in best or item.preference > best[item.wmo].preference:
            best[item.wmo] = item
    return best


def find_station_by_candidates(
    candidates: list[str],
    best_norm: dict[str, StationZip],
    inventory: list[StationZip],
    allowed_region_codes: set[str] | None = None,
) -> StationZip | None:
    pool = [
        item for item in inventory
        if not allowed_region_codes or item.region_code in allowed_region_codes
    ]
    for candidate in candidates:
        key = normalize_name(candidate)
        hits = [item for item in pool if item.norm_name == key]
        if hits:
            return max(hits, key=lambda item: item.preference)
    for candidate in candidates:
        hits = [item for item in pool if station_word_match(candidate, item.station_name)]
        if hits:
            hits.sort(key=lambda item: (item.preference, -len(item.station_name)), reverse=True)
            return hits[0]
    return None


def match_city(city: PrefectureCity, best_norm: dict[str, StationZip], best_wmo: dict[str, StationZip], inventory: list[StationZip]) -> tuple[StationZip, str]:
    region_codes = PROVINCE_STATION_CODES.get(city.province_zh)
    direct_candidates = []
    for candidate in english_candidates(city):
        if candidate in CITY_STATION_ALIASES.get(city.city_zh, []):
            continue
        direct_candidates.append(candidate)
    direct = find_station_by_candidates(direct_candidates, best_norm, inventory, region_codes)
    if direct:
        return direct, 'direct'

    alias = find_station_by_candidates(CITY_STATION_ALIASES.get(city.city_zh, []), best_norm, inventory, region_codes)
    if alias:
        return alias, 'city_alias_fallback'

    fallback = find_station_by_candidates([PROVINCE_FALLBACK_CITY.get(city.province_zh, '')], best_norm, inventory, region_codes)
    if fallback:
        return fallback, 'province_capital_fallback'

    # Last resort: best available China station. Should not occur with the fallback map.
    fallback = sorted(inventory, key=lambda item: item.preference, reverse=True)[0]
    return fallback, 'global_fallback'


def download_zip(item: StationZip) -> int:
    ensure_dir(RAW_DIR)
    expected_stem = re.sub(r'\.zip$', '', item.file, flags=re.I)
    if list(RAW_DIR.glob(f'{expected_stem}*.epw')):
        return 0
    resp = None
    for attempt in range(1, 5):
        try:
            resp = SESSION.get(item.url, timeout=120)
            if resp.status_code == 429:
                retry_after = float(resp.headers.get('Retry-After') or (10 * attempt))
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            break
        except Exception:
            if attempt >= 4:
                raise
            time.sleep(3.0 * attempt)
    if resp is None:
        raise RuntimeError(f'Failed to download {item.url}')
    count = 0
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith(('.epw', '.stat')):
                continue
            dest = RAW_DIR / os.path.basename(info.filename)
            with zf.open(info) as src, open(dest, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            count += 1
    return count


def run_processor() -> None:
    subprocess.run([sys.executable, str(ROOT / 'scripts' / 'processor.py')], cwd=ROOT, check=True)


def load_station_json(wmo: str) -> dict[str, Any]:
    path = PROCESSED_DIR / f'{wmo}.json'
    if not path.exists():
        raise FileNotFoundError(f'Missing processed station JSON: {path}')
    return json.loads(path.read_text(encoding='utf-8'))


def remove_old_alias_files() -> None:
    for directory in [PROCESSED_DIR, PUBLIC_DIR]:
        if not directory.exists():
            continue
        for pattern in ['top100-*.json', 'prefecture-*.json']:
            for path in directory.glob(pattern):
                path.unlink()


def write_json_both(name: str, payload: Any) -> None:
    ensure_dir(PROCESSED_DIR)
    ensure_dir(PUBLIC_DIR)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    (PROCESSED_DIR / name).write_text(text, encoding='utf-8')
    (PUBLIC_DIR / name).write_text(text, encoding='utf-8')


def create_prefecture_aliases(cities: list[PrefectureCity], matches: dict[str, tuple[StationZip, str]]) -> list[dict[str, Any]]:
    remove_old_alias_files()
    features = []
    rows = []
    for city in cities:
        station, quality = matches[city.city_zh]
        station_data = load_station_json(station.wmo)
        base_metadata = station_data.get('metadata', {})
        station_lat = base_metadata.get('lat')
        station_lon = base_metadata.get('lon')
        lat = city.lat if city.lat is not None else station_lat
        lon = city.lon if city.lon is not None else station_lon
        city_id = f'prefecture-{city.slug}'

        catalog_type = 'prefecture_level_admin_unit'
        if city.admin_type_zh in {'直辖市', '特别行政区'}:
            catalog_type = 'supplemental_admin_unit'

        payload = json.loads(json.dumps(station_data, ensure_ascii=False))
        payload['metadata'] = {
            **base_metadata,
            'city': city.city_zh,
            'city_short_zh': city.city_short_zh,
            'city_en': city.city_en,
            'province': city.province_zh,
            'province_en': city.province_en,
            'admin_level': city.admin_type_zh,
            'catalog_id': city_id,
            'prefecture_index': city.index,
            'division_code': city.division_code,
            'lat': lat,
            'lon': lon,
            'source_station_city': base_metadata.get('city'),
            'source_station_wmo': station.wmo,
            'source_station_lat': station_lat,
            'source_station_lon': station_lon,
            'station_match_quality': quality,
            'catalog_type': catalog_type,
        }
        payload['yearly'] = {
            **payload.get('yearly', {}),
            'admin_level': city.admin_type_zh,
            'prefecture_index': city.index,
            'division_code': city.division_code,
            'source_station_id': station.wmo,
            'source_station_name': base_metadata.get('city'),
            'station_match_quality': quality,
            'catalog_type': catalog_type,
        }
        payload.setdefault('methodology', {})['prefecture_city_catalog'] = {
            'city_list_source': PREFECTURE_LIST_URL,
            'station_source': 'OneBuilding Asia index pages for China / Hong Kong / Macau',
            'admin_level': city.admin_type_zh,
            'source_station_file': station.file,
            'source_station_wmo': station.wmo,
            'station_match_quality': quality,
            'catalog_type': catalog_type,
        }
        write_json_both(f'{city_id}.json', payload)

        properties = {
            'id': city_id,
            'city': city.city_zh,
            'city_short_zh': city.city_short_zh,
            'city_en': city.city_en,
            'province': city.province_zh,
            'province_en': city.province_en,
            'admin_level': city.admin_type_zh,
            'catalog_type': catalog_type,
            'prefecture_index': city.index,
            'division_code': city.division_code,
            'source_station_id': station.wmo,
            'source_station_name': base_metadata.get('city'),
            'source_station_file': station.file,
            'station_match_quality': quality,
            **payload.get('yearly', {}),
        }
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
            'properties': properties,
        })
        rows.append({
            **asdict(city),
            'catalog_id': city_id,
            'source_station_wmo': station.wmo,
            'source_station_file': station.file,
            'source_station_name': base_metadata.get('city'),
            'source_station_lat': station_lat,
            'source_station_lon': station_lon,
            'station_match_quality': quality,
        })

    geo = {'type': 'FeatureCollection', 'features': features}
    write_json_both('stations.geojson', geo)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    if not rows:
        return
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    ensure_dir(CATALOG_DIR)
    ensure_dir(AUDIT_DIR)
    cities = fetch_prefecture_cities()
    web_units = [*cities, *supplemental_web_units(len(cities))]
    inventory = fetch_onebuilding_inventory()
    best_norm = best_by_norm(inventory)
    best_wmo = best_by_wmo(inventory)

    matches: dict[str, tuple[StationZip, str]] = {}
    selected_zips: dict[str, StationZip] = {}
    for city in web_units:
        station, quality = match_city(city, best_norm, best_wmo, inventory)
        matches[city.city_zh] = (station, quality)
        selected_zips[station.file] = station

    extracted = 0
    for idx, station in enumerate(sorted(selected_zips.values(), key=lambda item: item.file), start=1):
        try:
            extracted += download_zip(station)
        except Exception as exc:
            print(f'[WARN] download failed: {station.file}: {exc}', file=sys.stderr)
        # Deliberately keep climate downloads serial and paced. The script also
        # skips already-cached EPW files, so reruns do not re-hit OneBuilding.
        time.sleep(0.4)
        if idx % 10 == 0:
            time.sleep(4.0)

    run_processor()
    rows = create_prefecture_aliases(web_units, matches)
    write_csv(CATALOG_DIR / f'prefecture_admin_unit_list_333_{RUN_DATE}.csv', [asdict(city) for city in cities])
    write_csv(AUDIT_DIR / f'prefecture_admin_unit_list_333_{RUN_DATE}.csv', [asdict(city) for city in cities])
    write_csv(CATALOG_DIR / f'prefecture_admin_unit_station_matches_{RUN_DATE}.csv', rows)
    write_csv(AUDIT_DIR / f'prefecture_admin_unit_station_matches_{RUN_DATE}.csv', rows)

    quality_counts: dict[str, int] = {}
    for _, quality in matches.values():
        quality_counts[quality] = quality_counts.get(quality, 0) + 1
    summary = {
        'prefecture_admin_unit_count': len(cities),
        'web_catalog_entry_count': len(web_units),
        'supplemental_unit_count': len(web_units) - len(cities),
        'unique_admin_unit_names': len({city.city_zh for city in cities}),
        'admin_type_counts': {key: sum(1 for city in cities if city.admin_type_zh == key) for key in ['地级市', '地区', '自治州', '盟']},
        'unique_source_stations': len({station.wmo for station, _ in matches.values()}),
        'source_station_reuse_count': len(web_units) - len({station.wmo for station, _ in matches.values()}),
        'match_quality_counts': quality_counts,
        'new_files_extracted': extracted,
        'city_list_source': PREFECTURE_LIST_URL,
        'station_source': [ONEBUILDING_CHINA_URL, ONEBUILDING_HONG_KONG_URL, ONEBUILDING_MACAU_URL],
    }
    (CATALOG_DIR / f'summary_{RUN_DATE}.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (AUDIT_DIR / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
