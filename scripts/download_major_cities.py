#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import os
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / 'data' / 'raw'

@dataclass(frozen=True)
class TargetZip:
    name: str
    url: str

# National major one/two-tier cities (verified OneBuilding zip links)
TARGETS: list[TargetZip] = [
    TargetZip('Beijing', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/BJ_Beijing/CHN_BJ_Beijing-Capital.Intl.AP.545110_TMYx.zip'),
    TargetZip('Shanghai', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/SH_Shanghai/CHN_SH_Shanghai-Baoshan.583620_TMYx.zip'),
    TargetZip('Guangzhou', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/GD_Guangdong/CHN_GD_Guangzhou.592870_TMYx.zip'),
    TargetZip('Shenzhen', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/GD_Guangdong/CHN_GD_Shenzhen.594930_TMYx.zip'),
    TargetZip('Tianjin', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/TJ_Tianjin/CHN_TJ_Tianjin-Binhai.Intl.AP.545273_TMYx.zip'),
    TargetZip('Chongqing', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/CQ_Chongqing/CHN_CQ_Chongqing.575160_TMYx.zip'),
    TargetZip('Chengdu', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/SC_Sichuan/CHN_SC_Chengdu-Shuangliu.AP.562940_TMYx.zip'),
    TargetZip('Hangzhou', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/ZJ_Zhejiang/CHN_ZJ_Hangzhou.584570_TMYx.zip'),
    TargetZip('Wuhan', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/HB_Hubei/CHN_HB_Tianhe-Wuhan.574940_TMYx.zip'),
    TargetZip('Nanjing', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/JS_Jiangsu/CHN_JS_Nanjing.582380_TMYx.zip'),
    TargetZip('Ningbo', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/ZJ_Zhejiang/CHN_ZJ_Ningbo.585620_TMYx.zip'),
    TargetZip('Qingdao', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/SD_Shandong/CHN_SD_Qingdao.Intl.AP.548570_TMYx.zip'),
    TargetZip('Dalian', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/LN_Liaoning/CHN_LN_Dalian-Zhoushuizi.Intl.AP.546620_TMYx.zip'),
    TargetZip('Fuzhou', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/FJ_Fujian/CHN_FJ_Fuzhou.588470_TMYx.zip'),
    TargetZip('Xiamen', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/FJ_Fujian/CHN_FJ_Xiamen.591340_TMYx.zip'),
    TargetZip('Changsha', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/HN_Hunan/CHN_HN_Changsha.576870_TMYx.zip'),
    TargetZip('Zhengzhou', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/HA_Henan/CHN_HA_Zhengzhou.570830_CSWD.zip'),
    TargetZip('Hefei', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/AH_Anhui/CHN_AH_Hefei.583210_TMYx.zip'),
    TargetZip('Changchun', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/JL_Jilin/CHN_JL_Changchun.541610_TMYx.zip'),
    TargetZip('Shenyang', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/LN_Liaoning/CHN_LN_Shenyang.543420_TMYx.zip'),
    TargetZip('Harbin', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/HL_Heilongjiang/CHN_HL_Harbin-Taiping.AP.541611_TMYx.zip'),
    TargetZip('Kunming', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/YN_Yunnan/CHN_YN_Kunming-Wujiaba.AP.567780_TMYx.zip'),
    TargetZip('Nanning', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/GX_Guangxi_ZHuang/CHN_GX_Nanning.594310_TMYx.zip'),
    TargetZip('Taiyuan', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/SX_Shanxi/CHN_SX_Taiyuan.537720_TMYx.zip'),
    TargetZip('Shijiazhuang', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/HE_Hebei/CHN_HE_Shijiazhuang.536980_TMYx.zip'),
    TargetZip('Suzhou', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/JS_Jiangsu/CHN_JS_Suzhou.583580_TMYx.zip'),
    TargetZip('Jinan', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/SD_Shandong/CHN_SD_Jinan.Tsinan.548230_TMYx.zip'),
    TargetZip('Nanchang', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/JX_Jiangxi/CHN_JX_Nanchang.586060_TMYx.zip'),
    TargetZip('Mianyang', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/SC_Sichuan/CHN_SC_Mianyang.561960_TMYx.zip'),
    TargetZip('Xuzhou', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/JS_Jiangsu/CHN_JS_Xuzhou.580270_TMYx.zip'),
    TargetZip('Yantai', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/SD_Shandong/CHN_SD_Yantai.547630_TMYx.zip'),
    TargetZip('Weifang', 'https://climate.onebuilding.org/WMO_Region_2_Asia/CHN_China/SD_Shandong/CHN_SD_Weifang.548430_TMYx.zip'),
    TargetZip('Taipei', 'https://climate.onebuilding.org/WMO_Region_2_Asia/TWN_Taiwan/NOR_Northern_Region/TWN_NOR_Taipei-Songshan.AP.466960_TMYx.zip'),
]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def download_bytes(url: str) -> bytes:
    req = Request(url, headers={
        'User-Agent': 'WeatherWhisper/1.0 (+OpenClaw)',
        'Accept': 'application/zip,application/octet-stream;q=0.9,*/*;q=0.8',
    })
    with urlopen(req, timeout=60) as resp:
        return resp.read()


def existing_raw_files_for(target: TargetZip) -> list[Path]:
    """Return already-extracted files for a target by matching the ZIP stem.

    This keeps reruns idempotent and avoids unnecessary network requests while
    expanding coverage in batches.
    """
    stem = Path(target.url).stem
    return sorted(RAW_DIR.glob(f"{stem}.*"))


def extract_zip(content: bytes, source_label: str) -> int:
    count = 0
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            lower = info.filename.lower()
            if not lower.endswith(('.epw', '.stat')):
                continue
            base_name = os.path.basename(info.filename)
            dest = RAW_DIR / base_name
            ensure_dir(dest.parent)
            with zf.open(info) as src, open(dest, 'wb') as dst:
                dst.write(src.read())
            count += 1
            print(f'  extracted {base_name}')
    print(f'[{source_label}] extracted {count} climate files')
    return count


def select_batch(targets: list[TargetZip], batch_size: int | None, batch_index: int) -> list[TargetZip]:
    if batch_size is None:
        return targets
    if batch_size <= 0:
        raise ValueError('--batch-size must be positive')
    if batch_index < 0:
        raise ValueError('--batch-index must be zero or positive')
    start = batch_index * batch_size
    return targets[start:start + batch_size]


def main() -> int:
    parser = argparse.ArgumentParser(description='Download selected OneBuilding climate ZIPs in polite batches.')
    parser.add_argument('--batch-size', type=int, default=None, help='Number of city ZIPs to process in this run.')
    parser.add_argument('--batch-index', type=int, default=0, help='Zero-based batch index when --batch-size is set.')
    parser.add_argument('--delay', type=float, default=2.0, help='Seconds to wait between network requests.')
    parser.add_argument('--force', action='store_true', help='Re-download even when extracted files already exist.')
    args = parser.parse_args()

    ensure_dir(RAW_DIR)
    selected = select_batch(TARGETS, args.batch_size, args.batch_index)
    if not selected:
        print('No targets selected for this batch.')
        return 0

    total = 0
    for offset, target in enumerate(selected, start=1):
        existing = existing_raw_files_for(target)
        if existing and not args.force:
            print(f'Skipping {target.name}: {len(existing)} existing climate files found.')
            continue
        print(f'Fetching {target.name} ({offset}/{len(selected)})...')
        try:
            content = download_bytes(target.url)
        except Exception as e:
            print(f'  failed: {e}')
            continue
        try:
            total += extract_zip(content, target.name)
        except Exception as e:
            print(f'  extract failed: {e}')
        if offset < len(selected) and args.delay > 0:
            time.sleep(args.delay)
    print(f'Done. Total extracted files: {total}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
