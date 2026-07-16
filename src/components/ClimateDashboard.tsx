import React, { useEffect, useMemo, useRef, useState } from 'react';
import * as echarts from 'echarts';
import {
  X,
  Thermometer,
  Droplets,
  Wind,
  Sun,
  Cloud,
  Calendar,
  MapPin,
  ArrowUpRight,
  Waves,
  Compass,
  Umbrella,
  Gauge,
  Sparkles,
} from 'lucide-react';

interface CategoryPct {
  label: string;
  pct: number;
}

interface MonthData {
  temp_avg: number;
  temp_max: number;
  temp_min: number;
  apparent_temp_avg?: number;
  dew_point_avg?: number;
  humidity: number;
  wind: number;
  wind_dir?: number | null;
  wind_dir_text?: string;
  precip: number;
  precip_days?: number;
  precip_probability?: number;
  solar: number;
  cloud: number;
  opaque_cloud?: number;
  visibility?: number | null;
  sunny_rate?: number;
  cloud_score?: number;
  precip_score?: number;
  tourism_temp_score?: number;
  tourism_score?: number;
  beach_score?: number;
  comfort_label?: string;
  cloud_categories?: Record<string, CategoryPct>;
  humidity_comfort?: Record<string, CategoryPct>;
}

interface HourData {
  temp?: number;
  apparent_temp?: number;
  humidity?: number;
  dew_point?: number;
  cloud?: number;
  opaque_cloud?: number;
  wind?: number;
  precip?: number;
  tourism_score?: number;
}

interface DailyClimateData {
  doy: number;
  date: string;
  temp_avg: number;
  temp_max: number;
  temp_min: number;
  apparent_temp: number;
  dew_point: number;
  humidity: number;
  cloud: number;
  wind: number;
  precip_31d: number;
  wet_probability: number;
  solar_kwh: number;
}

interface StationData {
  metadata: { city: string; state: string; country?: string; wmo: string; lat?: number; lon?: number; elev?: number };
  yearly: {
    avg_temp: number;
    total_precip: number;
    avg_humidity: number;
    avg_wind: number;
    total_solar: number;
    avg_cloud: number;
    avg_opaque_cloud?: number;
    avg_visibility?: number | null;
    avg_apparent_temp?: number;
    avg_dew_point?: number;
    water_temp: number;
    growing_season: number;
    best_time: string;
    best_tourism_months?: string;
    tourism_score_avg?: number;
    beach_score_avg?: number;
    tourism_peak_month?: number | null;
    overview: string;
    solar_energy: number;
    data_source?: string;
    method_note?: string;
    climate_normal_period?: string;
    temperature_source?: string;
    gridded_source?: string;
  };
  monthly: Record<string, MonthData>;
  daily_climatology?: DailyClimateData[];
  hourly_monthly?: Record<string, Record<string, HourData>>;
  methodology?: any;
}

interface ClimateDashboardProps {
  stationId: string;
  selectedMonth: number;
  onClose?: () => void;
}

const BASE_PATH = import.meta.env.BASE_URL;
const MONTHS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];
const CLOUD_KEYS = ['clear', 'mostly_clear', 'partly_cloudy', 'mostly_cloudy', 'overcast'];
const CLOUD_LABELS: Record<string, string> = {
  clear: '晴天',
  mostly_clear: '大部分晴天',
  partly_cloudy: '部分多云',
  mostly_cloudy: '大部分多云',
  overcast: '阴天',
};
const CLOUD_COLORS: Record<string, string> = {
  clear: '#60a5fa',
  mostly_clear: '#93c5fd',
  partly_cloudy: '#cbd5e1',
  mostly_cloudy: '#94a3b8',
  overcast: '#475569',
};
const HUMIDITY_KEYS = ['dry', 'comfortable', 'humid', 'muggy', 'oppressive', 'miserable'];
const HUMIDITY_LABELS: Record<string, string> = {
  dry: '干燥',
  comfortable: '舒适',
  humid: '潮湿',
  muggy: '闷热',
  oppressive: '闷热难受',
  miserable: '极为难受',
};
const HUMIDITY_COLORS: Record<string, string> = {
  dry: '#bae6fd',
  comfortable: '#86efac',
  humid: '#fde68a',
  muggy: '#fdba74',
  oppressive: '#f472b6',
  miserable: '#ef4444',
};
const ABSOLUTE_TEMP_PIECES = [
  { lt: -10, label: '< -10°C', color: '#313695' },
  { gte: -10, lt: 0, label: '-10–0°C', color: '#4575b4' },
  { gte: 0, lt: 5, label: '0–5°C', color: '#74add1' },
  { gte: 5, lt: 10, label: '5–10°C', color: '#abd9e9' },
  { gte: 10, lt: 15, label: '10–15°C', color: '#e0f3f8' },
  { gte: 15, lt: 20, label: '15–20°C', color: '#d9ef8b' },
  { gte: 20, lt: 24, label: '20–24°C', color: '#fee08b' },
  { gte: 24, lt: 28, label: '24–28°C', color: '#fdae61' },
  { gte: 28, lt: 32, label: '28–32°C', color: '#f46d43' },
  { gte: 32, lt: 36, label: '32–36°C', color: '#d73027' },
  { gte: 36, label: '≥ 36°C', color: '#a50026' },
];

function oneDecimal(value: number | undefined | null, suffix = '') {
  return value == null || Number.isNaN(Number(value)) ? '—' : `${Number(value).toFixed(1)}${suffix}`;
}

function twoDecimal(value: number | undefined | null, suffix = '') {
  return value == null || Number.isNaN(Number(value)) ? '—' : `${Number(value).toFixed(2)}${suffix}`;
}

function asPctCloud(value: number | undefined | null) {
  if (value == null || Number.isNaN(Number(value))) return 0;
  const n = Number(value);
  return n <= 10 ? n * 10 : n;
}

function fallbackTourismScore(item: MonthData) {
  const temp = Number(item.apparent_temp_avg ?? item.temp_avg);
  const cloudPct = asPctCloud(item.opaque_cloud ?? item.cloud);
  const precipProb = Number(item.precip_probability ?? 0);
  const tempScore = Math.max(0, Math.min(10, 10 - Math.abs(temp - 23) / 14 * 10));
  const cloudScore = Math.max(1, 10 - cloudPct / 100 * 9);
  const precipScore = Math.max(0, 10 - precipProb / 100 * 10);
  return Math.round((0.5 * tempScore + 0.25 * cloudScore + 0.25 * precipScore) * 10) / 10;
}

function chartLifecycle(ref: React.RefObject<HTMLDivElement>, option: any) {
  if (!ref.current) return undefined;
  const chart = echarts.init(ref.current);
  chart.setOption(option);
  const handleResize = () => chart.resize();
  window.addEventListener('resize', handleResize);
  return () => {
    window.removeEventListener('resize', handleResize);
    chart.dispose();
  };
}

const ClimateDashboard: React.FC<ClimateDashboardProps> = ({ stationId, selectedMonth, onClose }) => {
  const [data, setData] = useState<StationData | null>(null);
  const tempChartRef = useRef<HTMLDivElement>(null);
  const hourlyChartRef = useRef<HTMLDivElement>(null);
  const cloudChartRef = useRef<HTMLDivElement>(null);
  const precipChartRef = useRef<HTMLDivElement>(null);
  const humidityChartRef = useRef<HTMLDivElement>(null);
  const windChartRef = useRef<HTMLDivElement>(null);
  const solarChartRef = useRef<HTMLDivElement>(null);
  const tourismChartRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!stationId) return;
    fetch(`${BASE_PATH}/data/${stationId}.json`)
      .then(res => res.json())
      .then(setData)
      .catch(err => console.error('Failed to load station data:', err));
  }, [stationId]);

  const monthlySorted = useMemo(() => {
    if (!data) return [] as (MonthData & { month: number; tourism_score: number; sunny_rate: number; precip_probability: number })[];
    return Object.entries(data.monthly)
      .sort(([a], [b]) => Number(a) - Number(b))
      .map(([month, value]) => ({
        ...value,
        month: Number(month),
        tourism_score: value.tourism_score ?? fallbackTourismScore(value),
        sunny_rate: value.sunny_rate ?? Math.max(0, 100 - asPctCloud(value.opaque_cloud ?? value.cloud)),
        precip_probability: value.precip_probability ?? 0,
      }));
  }, [data]);

  const dailyClimate = data?.daily_climatology || [];
  const dailyXAxis = dailyClimate.map(item => item.date);
  const dailyAxisLabel = (value: string) => value.endsWith('-01') ? `${Number(value.slice(0, 2))}月` : '';
  const selectedMonthArea = dailyClimate.length ? [[
    { xAxis: `${String(selectedMonth).padStart(2, '0')}-01` },
    { xAxis: `${String(selectedMonth).padStart(2, '0')}-${new Date(2021, selectedMonth, 0).getDate()}` },
  ]] : [];

  const selectedIndex = Math.min(Math.max(selectedMonth, 1), 12) - 1;
  const selected = monthlySorted[selectedIndex];
  const indexOfMax = (fn: (m: MonthData) => number) => monthlySorted.reduce((best, item, idx) => fn(item) > fn(monthlySorted[best]) ? idx : best, 0);
  const indexOfMin = (fn: (m: MonthData) => number) => monthlySorted.reduce((best, item, idx) => fn(item) < fn(monthlySorted[best]) ? idx : best, 0);

  const hottest = monthlySorted.length ? indexOfMax(item => item.temp_max) : 0;
  const coldest = monthlySorted.length ? indexOfMin(item => item.temp_min) : 0;
  const wettest = monthlySorted.length ? indexOfMax(item => item.precip) : 0;
  const driest = monthlySorted.length ? indexOfMin(item => item.precip) : 0;
  const clearest = monthlySorted.length ? indexOfMin(item => asPctCloud(item.opaque_cloud ?? item.cloud)) : 0;
  const cloudiest = monthlySorted.length ? indexOfMax(item => asPctCloud(item.opaque_cloud ?? item.cloud)) : 0;
  const bestTourismMonth = monthlySorted.length ? indexOfMax(item => item.tourism_score ?? fallbackTourismScore(item)) : 0;
  const bestTourismMonths = data?.yearly.best_tourism_months || (monthlySorted[bestTourismMonth] ? MONTHS[bestTourismMonth] : '—');
  const tourismAvg = monthlySorted.length ? monthlySorted.reduce((sum, item) => sum + item.tourism_score, 0) / monthlySorted.length : 0;

  const hourlyHeatmapData = useMemo(() => {
    if (!data?.hourly_monthly) return [] as [number, number, number][];
    const rows: [number, number, number][] = [];
    for (let m = 1; m <= 12; m += 1) {
      for (let h = 0; h < 24; h += 1) {
        const val = data.hourly_monthly[String(m)]?.[String(h)]?.temp ?? monthlySorted[m - 1]?.temp_avg ?? 0;
        rows.push([m - 1, 23 - h, Number(val.toFixed ? val.toFixed(1) : val)]);
      }
    }
    return rows;
  }, [data, monthlySorted]);

  useEffect(() => {
    if (!monthlySorted.length) return;
    const useDaily = dailyClimate.length === 365;
    const xData = useDaily ? dailyXAxis : MONTHS;
    return chartLifecycle(tempChartRef, {
      backgroundColor: 'transparent',
      animationDuration: 420,
      tooltip: { trigger: 'axis', backgroundColor: 'rgba(2,6,23,.94)', borderColor: 'rgba(148,163,184,.18)', textStyle: { color: '#fff' } },
      legend: { data: ['平均高温', '平均温度', '平均低温', '体感温度'], textStyle: { color: '#cbd5e1' }, top: 2 },
      grid: { left: 42, right: 24, top: 48, bottom: 34 },
      xAxis: { type: 'category', data: xData, boundaryGap: false, axisLabel: { color: '#94a3b8', interval: 0, formatter: useDaily ? dailyAxisLabel : undefined }, axisLine: { lineStyle: { color: 'rgba(148,163,184,.25)' } } },
      yAxis: { type: 'value', name: '°C', nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.10)' } } },
      series: [
        { name: '平均高温', type: 'line', showSymbol: !useDaily, smooth: true, data: useDaily ? dailyClimate.map(item => item.temp_max) : monthlySorted.map(item => item.temp_max), lineStyle: { width: 3, color: '#ef4444' }, itemStyle: { color: '#ef4444' }, areaStyle: { opacity: 0.08, color: '#ef4444' } },
        { name: '平均温度', type: 'line', showSymbol: !useDaily, smooth: true, data: useDaily ? dailyClimate.map(item => item.temp_avg) : monthlySorted.map(item => item.temp_avg), lineStyle: { width: 2, color: '#f59e0b' }, itemStyle: { color: '#f59e0b' } },
        { name: '平均低温', type: 'line', showSymbol: !useDaily, smooth: true, data: useDaily ? dailyClimate.map(item => item.temp_min) : monthlySorted.map(item => item.temp_min), lineStyle: { width: 3, color: '#3b82f6' }, itemStyle: { color: '#3b82f6' }, areaStyle: { opacity: 0.08, color: '#3b82f6' } },
        { name: '体感温度', type: 'line', showSymbol: false, smooth: true, data: useDaily ? dailyClimate.map(item => item.apparent_temp) : monthlySorted.map(item => item.apparent_temp_avg ?? item.temp_avg), lineStyle: { width: 2, color: '#f472b6', type: 'dashed' }, itemStyle: { color: '#f472b6' }, markArea: useDaily ? { silent: true, itemStyle: { color: 'rgba(34,211,238,.07)' }, data: selectedMonthArea } : undefined },
      ],
    });
  }, [monthlySorted, dailyClimate, selectedMonth]);

  useEffect(() => {
    if (!hourlyHeatmapData.length) return;
    const hourLabels = Array.from({ length: 24 }, (_, idx) => `${23 - idx}时`);
    return chartLifecycle(hourlyChartRef, {
      backgroundColor: 'transparent',
      animationDuration: 420,
      tooltip: { position: 'top', backgroundColor: 'rgba(2,6,23,.94)', borderColor: 'rgba(148,163,184,.18)', textStyle: { color: '#fff' }, formatter: (p: any) => `${MONTHS[p.data[0]]} ${23 - p.data[1]}时<br/>平均温度 ${p.data[2]}°C<br/><span style="opacity:.72">固定绝对温度色阶</span>` },
      grid: { left: 46, right: 18, top: 18, bottom: 96 },
      xAxis: { type: 'category', data: MONTHS, axisLabel: { color: '#94a3b8' }, splitArea: { show: false }, axisLine: { lineStyle: { color: 'rgba(148,163,184,.25)' } } },
      yAxis: { type: 'category', data: hourLabels, axisLabel: { color: '#94a3b8', interval: 1 }, axisLine: { lineStyle: { color: 'rgba(148,163,184,.25)' } } },
      visualMap: {
        type: 'piecewise',
        pieces: ABSOLUTE_TEMP_PIECES,
        orient: 'horizontal',
        left: 'center',
        bottom: 2,
        itemWidth: 16,
        itemHeight: 10,
        itemGap: 6,
        textStyle: { color: '#cbd5e1', fontSize: 10 },
      },
      series: [{ name: '小时温度', type: 'heatmap', data: hourlyHeatmapData, emphasis: { itemStyle: { borderColor: '#fff', borderWidth: 1 } } }],
    });
  }, [hourlyHeatmapData]);

  useEffect(() => {
    if (!monthlySorted.length) return;
    if (dailyClimate.length === 365) {
      return chartLifecycle(cloudChartRef, {
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis', backgroundColor: 'rgba(2,6,23,.94)', borderColor: 'rgba(148,163,184,.18)', textStyle: { color: '#fff' }, formatter: (params: any) => `${params[0].name}<br/>平均云量 ${params[0].value}%` },
        grid: { left: 44, right: 22, top: 28, bottom: 34 },
        xAxis: { type: 'category', data: dailyXAxis, boundaryGap: false, axisLabel: { color: '#94a3b8', interval: 0, formatter: dailyAxisLabel }, axisLine: { lineStyle: { color: 'rgba(148,163,184,.25)' } } },
        yAxis: { type: 'value', min: 0, max: 100, name: '%', nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.10)' } } },
        series: [{ name: '平均云量', type: 'line', showSymbol: false, smooth: true, data: dailyClimate.map(item => item.cloud), lineStyle: { width: 3, color: '#94a3b8' }, areaStyle: { opacity: 0.28, color: '#64748b' }, markArea: { silent: true, itemStyle: { color: 'rgba(34,211,238,.07)' }, data: selectedMonthArea } }],
      });
    }
    return chartLifecycle(cloudChartRef, {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: 'rgba(2,6,23,.94)', borderColor: 'rgba(148,163,184,.18)', textStyle: { color: '#fff' } },
      legend: { data: CLOUD_KEYS.map(k => CLOUD_LABELS[k]), textStyle: { color: '#cbd5e1' }, top: 2 },
      grid: { left: 44, right: 22, top: 58, bottom: 34 },
      xAxis: { type: 'category', data: MONTHS, axisLabel: { color: '#94a3b8' }, axisLine: { lineStyle: { color: 'rgba(148,163,184,.25)' } } },
      yAxis: { type: 'value', min: 0, max: 100, name: '%', nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.10)' } } },
      series: CLOUD_KEYS.map(key => ({
        name: CLOUD_LABELS[key], type: 'bar', stack: 'cloud', barMaxWidth: 28,
        data: monthlySorted.map(item => item.cloud_categories?.[key]?.pct ?? 0),
        itemStyle: { color: CLOUD_COLORS[key] },
      })),
    });
  }, [monthlySorted, dailyClimate, selectedMonth]);

  useEffect(() => {
    if (!monthlySorted.length) return;
    if (dailyClimate.length === 365) {
      return chartLifecycle(precipChartRef, {
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis', backgroundColor: 'rgba(2,6,23,.94)', borderColor: 'rgba(148,163,184,.18)', textStyle: { color: '#fff' } },
        legend: { data: ['31日滑动降水量', '湿润日概率'], textStyle: { color: '#cbd5e1' }, top: 2 },
        grid: { left: 46, right: 46, top: 50, bottom: 34 },
        xAxis: { type: 'category', data: dailyXAxis, boundaryGap: false, axisLabel: { color: '#94a3b8', interval: 0, formatter: dailyAxisLabel }, axisLine: { lineStyle: { color: 'rgba(148,163,184,.25)' } } },
        yAxis: [
          { type: 'value', name: 'mm / 31日', nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.10)' } } },
          { type: 'value', min: 0, max: 100, name: '%', nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { show: false } },
        ],
        series: [
          { name: '31日滑动降水量', type: 'line', showSymbol: false, smooth: true, data: dailyClimate.map(item => item.precip_31d), lineStyle: { width: 3, color: '#3b82f6' }, areaStyle: { opacity: 0.20, color: '#3b82f6' }, markArea: { silent: true, itemStyle: { color: 'rgba(34,211,238,.07)' }, data: selectedMonthArea } },
          { name: '湿润日概率', type: 'line', yAxisIndex: 1, showSymbol: false, smooth: true, data: dailyClimate.map(item => item.wet_probability), lineStyle: { width: 2, color: '#22c55e' } },
        ],
      });
    }
    return chartLifecycle(precipChartRef, {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', backgroundColor: 'rgba(2,6,23,.94)', borderColor: 'rgba(148,163,184,.18)', textStyle: { color: '#fff' } },
      legend: { data: ['月降水量', '降水概率', '降水得分'], textStyle: { color: '#cbd5e1' }, top: 2 },
      grid: { left: 46, right: 46, top: 50, bottom: 34 },
      xAxis: { type: 'category', data: MONTHS, axisLabel: { color: '#94a3b8' }, axisLine: { lineStyle: { color: 'rgba(148,163,184,.25)' } } },
      yAxis: [
        { type: 'value', name: 'mm', nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.10)' } } },
        { type: 'value', min: 0, max: 100, name: '% / score', nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { show: false } },
      ],
      series: [
        { name: '月降水量', type: 'bar', data: monthlySorted.map(item => item.precip), barMaxWidth: 24, itemStyle: { color: 'rgba(59,130,246,.60)', borderRadius: [8, 8, 0, 0] } },
        { name: '降水概率', type: 'line', yAxisIndex: 1, smooth: true, data: monthlySorted.map(item => item.precip_probability), lineStyle: { width: 3, color: '#22c55e' }, itemStyle: { color: '#22c55e' } },
        { name: '降水得分', type: 'line', yAxisIndex: 1, smooth: true, data: monthlySorted.map(item => (item.precip_score ?? 0) * 10), lineStyle: { width: 2, color: '#a78bfa', type: 'dashed' }, itemStyle: { color: '#a78bfa' } },
      ],
    });
  }, [monthlySorted, dailyClimate, selectedMonth]);

  useEffect(() => {
    if (!monthlySorted.length) return;
    if (dailyClimate.length === 365) {
      return chartLifecycle(humidityChartRef, {
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis', backgroundColor: 'rgba(2,6,23,.94)', borderColor: 'rgba(148,163,184,.18)', textStyle: { color: '#fff' } },
        legend: { data: ['相对湿度', '露点', '体感温度'], textStyle: { color: '#cbd5e1' }, top: 2 },
        grid: { left: 46, right: 46, top: 52, bottom: 34 },
        xAxis: { type: 'category', data: dailyXAxis, boundaryGap: false, axisLabel: { color: '#94a3b8', interval: 0, formatter: dailyAxisLabel }, axisLine: { lineStyle: { color: 'rgba(148,163,184,.25)' } } },
        yAxis: [
          { type: 'value', min: 0, max: 100, name: '%', nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.10)' } } },
          { type: 'value', name: '°C', nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { show: false } },
        ],
        series: [
          { name: '相对湿度', type: 'line', showSymbol: false, smooth: true, data: dailyClimate.map(item => item.humidity), lineStyle: { width: 2, color: '#22d3ee' }, areaStyle: { opacity: 0.10, color: '#22d3ee' }, markArea: { silent: true, itemStyle: { color: 'rgba(34,211,238,.07)' }, data: selectedMonthArea } },
          { name: '露点', type: 'line', yAxisIndex: 1, showSymbol: false, smooth: true, data: dailyClimate.map(item => item.dew_point), lineStyle: { width: 2, color: '#34d399' } },
          { name: '体感温度', type: 'line', yAxisIndex: 1, showSymbol: false, smooth: true, data: dailyClimate.map(item => item.apparent_temp), lineStyle: { width: 3, color: '#f472b6' } },
        ],
      });
    }
    return chartLifecycle(humidityChartRef, {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: 'rgba(2,6,23,.94)', borderColor: 'rgba(148,163,184,.18)', textStyle: { color: '#fff' } },
      legend: { data: [...HUMIDITY_KEYS.map(k => HUMIDITY_LABELS[k]), '体感温度'], textStyle: { color: '#cbd5e1' }, top: 2 },
      grid: { left: 42, right: 44, top: 60, bottom: 34 },
      xAxis: { type: 'category', data: MONTHS, axisLabel: { color: '#94a3b8' }, axisLine: { lineStyle: { color: 'rgba(148,163,184,.25)' } } },
      yAxis: [
        { type: 'value', min: 0, max: 100, name: '%', nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.10)' } } },
        { type: 'value', name: '°C', nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { show: false } },
      ],
      series: [
        ...HUMIDITY_KEYS.map(key => ({
          name: HUMIDITY_LABELS[key], type: 'bar', stack: 'dewpoint', barMaxWidth: 28,
          data: monthlySorted.map(item => item.humidity_comfort?.[key]?.pct ?? 0),
          itemStyle: { color: HUMIDITY_COLORS[key] },
        })),
        { name: '体感温度', type: 'line', yAxisIndex: 1, smooth: true, data: monthlySorted.map(item => item.apparent_temp_avg ?? item.temp_avg), lineStyle: { width: 3, color: '#f472b6' }, itemStyle: { color: '#f472b6' } },
      ],
    });
  }, [monthlySorted, dailyClimate, selectedMonth]);

  useEffect(() => {
    if (!monthlySorted.length) return;
    if (dailyClimate.length === 365) {
      return chartLifecycle(windChartRef, {
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis', backgroundColor: 'rgba(2,6,23,.94)', borderColor: 'rgba(148,163,184,.18)', textStyle: { color: '#fff' }, formatter: (params: any) => `${params[0].name}<br/>平均风速 ${params[0].value} m/s` },
        grid: { left: 42, right: 24, top: 22, bottom: 46 },
        xAxis: { type: 'category', data: dailyXAxis, boundaryGap: false, axisLabel: { color: '#94a3b8', interval: 0, formatter: dailyAxisLabel }, axisLine: { lineStyle: { color: 'rgba(148,163,184,.25)' } } },
        yAxis: { type: 'value', name: 'm/s', nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.10)' } } },
        series: [{ name: '风速', type: 'line', showSymbol: false, smooth: true, data: dailyClimate.map(item => item.wind), lineStyle: { width: 3, color: '#2dd4bf' }, areaStyle: { opacity: 0.14, color: '#2dd4bf' }, markArea: { silent: true, itemStyle: { color: 'rgba(34,211,238,.07)' }, data: selectedMonthArea } }],
      });
    }
    const directions = monthlySorted.map(item => item.wind_dir_text || '—');
    return chartLifecycle(windChartRef, {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', backgroundColor: 'rgba(2,6,23,.94)', borderColor: 'rgba(148,163,184,.18)', textStyle: { color: '#fff' }, formatter: (params: any) => {
        const p = Array.isArray(params) ? params[0] : params;
        return `${p.name}<br/>平均风速 ${p.value} m/s<br/>主导风向 ${directions[p.dataIndex]}`;
      } },
      grid: { left: 42, right: 24, top: 22, bottom: 46 },
      xAxis: { type: 'category', data: MONTHS, axisLabel: { color: '#94a3b8' }, axisLine: { lineStyle: { color: 'rgba(148,163,184,.25)' } } },
      yAxis: { type: 'value', name: 'm/s', nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.10)' } } },
      series: [{ name: '风速', type: 'bar', data: monthlySorted.map(item => item.wind), barMaxWidth: 24, itemStyle: { color: 'rgba(45,212,191,.65)', borderRadius: [8, 8, 0, 0] }, label: { show: true, position: 'top', color: '#cbd5e1', fontSize: 10, formatter: (p: any) => directions[p.dataIndex] } }],
    });
  }, [monthlySorted, dailyClimate, selectedMonth]);

  useEffect(() => {
    if (dailyClimate.length !== 365) return;
    return chartLifecycle(solarChartRef, {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', backgroundColor: 'rgba(2,6,23,.94)', borderColor: 'rgba(148,163,184,.18)', textStyle: { color: '#fff' }, formatter: (params: any) => `${params[0].name}<br/>短波太阳能 ${params[0].value} kWh/m²/日` },
      grid: { left: 48, right: 24, top: 22, bottom: 42 },
      xAxis: { type: 'category', data: dailyXAxis, boundaryGap: false, axisLabel: { color: '#94a3b8', interval: 0, formatter: dailyAxisLabel }, axisLine: { lineStyle: { color: 'rgba(148,163,184,.25)' } } },
      yAxis: { type: 'value', name: 'kWh/m²/日', nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.10)' } } },
      series: [{ name: '短波太阳能', type: 'line', showSymbol: false, smooth: true, data: dailyClimate.map(item => item.solar_kwh), lineStyle: { width: 3, color: '#f59e0b' }, areaStyle: { opacity: 0.22, color: '#f59e0b' }, markArea: { silent: true, itemStyle: { color: 'rgba(34,211,238,.07)' }, data: selectedMonthArea } }],
    });
  }, [dailyClimate, selectedMonth]);

  useEffect(() => {
    if (!monthlySorted.length) return;
    return chartLifecycle(tourismChartRef, {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', backgroundColor: 'rgba(2,6,23,.94)', borderColor: 'rgba(148,163,184,.18)', textStyle: { color: '#fff' } },
      legend: { data: ['旅游指数', '温度得分', '云量得分', '降水得分', '沙滩/泳池'], textStyle: { color: '#cbd5e1' }, top: 2 },
      grid: { left: 42, right: 24, top: 58, bottom: 34 },
      xAxis: { type: 'category', data: MONTHS, axisLabel: { color: '#94a3b8' }, axisLine: { lineStyle: { color: 'rgba(148,163,184,.25)' } } },
      yAxis: { type: 'value', min: 0, max: 10, name: '0-10', nameTextStyle: { color: '#94a3b8' }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.10)' } } },
      series: [
        { name: '旅游指数', type: 'line', smooth: true, data: monthlySorted.map(item => item.tourism_score), lineStyle: { width: 3, color: '#14b8a6' }, itemStyle: { color: '#14b8a6' }, areaStyle: { opacity: 0.20, color: '#14b8a6' }, markPoint: { data: [{ name: '最佳月', value: monthlySorted[bestTourismMonth]?.tourism_score, xAxis: MONTHS[bestTourismMonth], yAxis: monthlySorted[bestTourismMonth]?.tourism_score }] } },
        { name: '温度得分', type: 'line', smooth: true, data: monthlySorted.map(item => item.tourism_temp_score ?? 0), lineStyle: { width: 2, color: '#ef4444' }, itemStyle: { color: '#ef4444' } },
        { name: '云量得分', type: 'line', smooth: true, data: monthlySorted.map(item => item.cloud_score ?? 0), lineStyle: { width: 2, color: '#60a5fa' }, itemStyle: { color: '#60a5fa' } },
        { name: '降水得分', type: 'line', smooth: true, data: monthlySorted.map(item => item.precip_score ?? 0), lineStyle: { width: 2, color: '#22c55e' }, itemStyle: { color: '#22c55e' } },
        { name: '沙滩/泳池', type: 'line', smooth: true, data: monthlySorted.map(item => item.beach_score ?? 0), lineStyle: { width: 2, color: '#f472b6', type: 'dashed' }, itemStyle: { color: '#f472b6' } },
      ],
    });
  }, [monthlySorted, bestTourismMonth]);

  if (!data || !monthlySorted.length) {
    return (
      <section className="rounded-[28px] border border-white/10 bg-white/6 backdrop-blur-2xl p-6 shadow-[0_24px_80px_rgba(0,0,0,.30)]">
        <div className="text-slate-300">正在加载气候数据…</div>
      </section>
    );
  }

  const climateSummary = `${data.metadata.city} 年平均气温约 ${oneDecimal(data.yearly.avg_temp, '°C')}，平均体感温度约 ${oneDecimal(data.yearly.avg_apparent_temp ?? data.yearly.avg_temp, '°C')}；最热月份通常是 ${MONTHS[hottest]}，平均高温约 ${oneDecimal(monthlySorted[hottest].temp_max, '°C')}，最冷月份是 ${MONTHS[coldest]}，平均低温约 ${oneDecimal(monthlySorted[coldest].temp_min, '°C')}。`;
  const precipSummary = `年降水量约 ${oneDecimal(data.yearly.total_precip, ' mm')}，降水最多的月份是 ${MONTHS[wettest]}（${oneDecimal(monthlySorted[wettest].precip, ' mm')}），最少的月份是 ${MONTHS[driest]}。${MONTHS[selectedIndex]} 的降水概率约 ${oneDecimal(selected?.precip_probability, '%')}，月降水量约 ${oneDecimal(selected?.precip, ' mm')}。`;
  const cloudSummary = `云量最少的月份是 ${MONTHS[clearest]}，遮蔽云量约 ${oneDecimal(monthlySorted[clearest].opaque_cloud ?? monthlySorted[clearest].cloud, '%')}；云量最多的月份是 ${MONTHS[cloudiest]}，遮蔽云量约 ${oneDecimal(monthlySorted[cloudiest].opaque_cloud ?? monthlySorted[cloudiest].cloud, '%')}。`;
  const visitSummary = `按 8:00-21:00 的体感温度、云量和降水综合评分，最佳访问窗口为 ${bestTourismMonths}，峰值月份为 ${MONTHS[bestTourismMonth]}，旅游指数约 ${oneDecimal(monthlySorted[bestTourismMonth].tourism_score, ' / 10')}。`;

  const metrics = [
    { icon: Thermometer, label: '平均气温', value: oneDecimal(data.yearly.avg_temp, '°C'), color: 'text-sky-300' },
    { icon: Gauge, label: '平均体感', value: oneDecimal(data.yearly.avg_apparent_temp ?? data.yearly.avg_temp, '°C'), color: 'text-pink-300' },
    { icon: Droplets, label: '年降水量', value: oneDecimal(data.yearly.total_precip, ' mm'), color: 'text-cyan-300' },
    { icon: Umbrella, label: '峰值降水月', value: `${MONTHS[wettest]} · ${oneDecimal(monthlySorted[wettest].precip, ' mm')}`, color: 'text-blue-300' },
    { icon: Cloud, label: '平均云量', value: oneDecimal(data.yearly.avg_cloud, '%'), color: 'text-slate-200' },
    { icon: Sun, label: '平均晴朗率', value: oneDecimal(monthlySorted.reduce((s, m) => s + m.sunny_rate, 0) / monthlySorted.length, '%'), color: 'text-amber-300' },
    { icon: Droplets, label: '露点均值', value: oneDecimal(data.yearly.avg_dew_point, '°C'), color: 'text-emerald-300' },
    { icon: Wind, label: '平均风速', value: twoDecimal(data.yearly.avg_wind, ' m/s'), color: 'text-violet-300' },
    { icon: Sparkles, label: '旅游平均分', value: oneDecimal(tourismAvg, ' / 10'), color: 'text-teal-300' },
    { icon: Calendar, label: '最佳访问', value: data.yearly.best_time, color: 'text-emerald-200' },
  ];

  const selectedFacts = selected ? [
    ['均温', oneDecimal(selected.temp_avg, '°C')],
    ['平均高温', oneDecimal(selected.temp_max, '°C')],
    ['平均低温', oneDecimal(selected.temp_min, '°C')],
    ['体感温度', oneDecimal(selected.apparent_temp_avg ?? selected.temp_avg, '°C')],
    ['降水概率', oneDecimal(selected.precip_probability, '%')],
    ['降水量', oneDecimal(selected.precip, ' mm')],
    ['云量', oneDecimal(selected.cloud, '%')],
    ['湿度', oneDecimal(selected.humidity, '%')],
    ['露点', oneDecimal(selected.dew_point_avg, '°C')],
    ['风速', oneDecimal(selected.wind, ' m/s')],
    ['主导风向', selected.wind_dir_text || '—'],
    ['旅游指数', oneDecimal(selected.tourism_score, ' / 10')],
  ] : [];

  return (
    <section className="min-w-0 overflow-hidden rounded-[24px] border border-white/10 bg-white/6 p-4 shadow-[0_24px_80px_rgba(0,0,0,.30)] backdrop-blur-2xl sm:p-5 md:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">climate-comfort annual climate page</div>
          <h2 className="mt-1 break-words text-2xl font-black text-white sm:text-3xl">{data.metadata.city}</h2>
          <p className="mt-2 break-words text-sm text-slate-300/90">
            {data.metadata.state} · WMO {data.metadata.wmo}
            {data.metadata.lat != null && data.metadata.lon != null ? ` · ${data.metadata.lat.toFixed(2)}°, ${data.metadata.lon.toFixed(2)}°` : ''}
            {data.metadata.elev != null ? ` · 海拔 ${data.metadata.elev.toFixed(0)} m` : ''}
          </p>
        </div>
        {onClose ? (
          <button onClick={onClose} className="rounded-full border border-white/10 bg-white/6 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white">
            <X size={18} />
          </button>
        ) : null}
      </div>

      <div className="mt-5 rounded-[24px] border border-white/10 bg-black/20 p-4 text-sm leading-7 text-slate-300/90 sm:p-5">
        <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">年度文字摘要</div>
        <p className="mt-2">{climateSummary}</p>
        <p className="mt-2">{precipSummary}</p>
        <p className="mt-2">{cloudSummary}</p>
        <p className="mt-2">{visitSummary}</p>
      </div>

      <div className="mt-5 grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {metrics.map(metric => (
          <div key={metric.label} className="min-w-0 rounded-2xl border border-white/10 bg-black/20 p-3 shadow-inner shadow-black/10 sm:p-4">
            <div className="flex items-center gap-3 text-slate-300/80">
              <metric.icon size={16} className={metric.color} />
              <span className="text-[10px] uppercase tracking-[0.18em] sm:text-[11px] sm:tracking-[0.22em]">{metric.label}</span>
            </div>
            <div className="mt-3 break-words text-base font-bold text-white sm:text-lg">{metric.value}</div>
          </div>
        ))}
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <ChartCard eyebrow="1 · Temperature" title="逐日平均高温 / 低温 / 体感" note="主曲线是1991–2020逐日气候常年值，经15日环形移动平均平滑；月份内部不再只有一个离散点。浅色区为当前选择月份。">
          <div ref={tempChartRef} className="h-[260px] w-full sm:h-[320px]" />
        </ChartCard>
        <ChartCard eyebrow="1b · Typical-year hourly pattern" title="典型年一日内不同时段温度" note="这一张仍来自OneBuilding TMY的小时结构，仅用于观察日变化；它不是1991–2020多年平均，已与主气候常年曲线分开标注。">
          <div ref={hourlyChartRef} className="h-[360px] w-full sm:h-[420px]" />
        </ChartCard>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <ChartCard eyebrow="2 · Cloudiness" title="逐日平均云量" note="NASA POWER/MERRA-2 1991–2020逐日云量常年值（约50 km格点），经15日平滑；这里显示天空平均覆盖率，不等同于‘多云时长占比’。">
          <div ref={cloudChartRef} className="h-[280px] w-full sm:h-[330px]" />
        </ChartCard>
        <ChartCard eyebrow="3 · Precipitation" title="31日滑动降水量与湿润日概率" note="蓝线为以年内每一天为中心的31日平均累计降水，绿线为日降水≥1 mm的多年概率，因此能显示月份内部的雨季转折。">
          <div ref={precipChartRef} className="h-[280px] w-full sm:h-[330px]" />
        </ChartCard>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <ChartCard eyebrow="4 · Humidity & feel" title="逐日湿度、露点与体感温度" note="站点覆盖合格时温度和露点来自NOAA GSOD，缺口与无站城市由ERA5-Land补足；体感温度结合温湿度和风速估算。">
          <div ref={humidityChartRef} className="h-[300px] w-full sm:h-[350px]" />
        </ChartCard>
        <ChartCard eyebrow="5 · Wind" title="逐日平均风速" note="NASA POWER/MERRA-2 1991–2020年内逐日平均风速，经15日平滑；月度表仍给出典型年主导风向。">
          <div ref={windChartRef} className="h-[300px] w-full sm:h-[350px]" />
        </ChartCard>
      </div>

      {dailyClimate.length === 365 ? (
        <div className="mt-5">
          <ChartCard eyebrow="6 · Solar energy" title="逐日地表短波太阳能" note="NASA POWER 1991–2020日均地表短波辐射，单位为kWh/m²/日；与日照时数不同，但可更直接反映到达地面的太阳能季节变化。">
            <div ref={solarChartRef} className="h-[280px] w-full sm:h-[330px]" />
          </ChartCard>
        </div>
      ) : null}

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.2fr_.8fr]">
        <ChartCard eyebrow="7 · Tourism score" title="旅游指数及组成" note="旅游指数仍按月汇总，填充区域为综合分；温度、云量与降水底层输入已改为1991–2020气候常年值。">
          <div ref={tourismChartRef} className="h-[300px] w-full sm:h-[350px]" />
        </ChartCard>
        <section className="min-w-0 overflow-hidden rounded-[24px] border border-white/10 bg-black/20 p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Methodology</div>
              <h3 className="mt-1 text-lg font-bold text-white">旅游指数计算方法</h3>
            </div>
            <Compass size={18} className="text-teal-300" />
          </div>
          <div className="space-y-3 text-sm leading-7 text-slate-300/90">
            <p>分析时段：每天 <span className="font-semibold text-white">08:00–21:00</span> 的小时数据，先算小时得分，再按月平均。</p>
            <p>综合公式：<span className="font-semibold text-white">0.50 × 体感温度得分 + 0.25 × 云量得分 + 0.25 × 降水得分</span>。</p>
            <p>温度得分按图示阈值线性插值：低于 10°C 为 0；18°C 为 9；24°C 为 10；27°C 为 9；32°C 及以上为 1。</p>
            <p>云量得分：完全晴朗 10，大部分晴朗约 9，阴天 1，中间线性下降。降水得分：无降水 10，微量降水约 9，≥1mm/h 为 0。</p>
            <p className="text-xs text-slate-400">数据源：{data.yearly.data_source || 'OneBuilding EPW/TMYx-CSWD 本地处理'}。</p>
            {data.yearly.climate_normal_period ? <p className="text-xs text-slate-400">标准期：{data.yearly.climate_normal_period}。温度源：{data.yearly.temperature_source}。网格变量：{data.yearly.gridded_source}。</p> : null}
            <p className="text-xs text-slate-400">页面采用相似的气候统计表达方式，但不抓取或复制WeatherSpark的专有原始数据。</p>
          </div>
        </section>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.05fr_.95fr]">
        <section className="min-w-0 overflow-hidden rounded-[24px] border border-white/10 bg-black/20 p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Monthly spotlight</div>
              <h3 className="mt-1 text-lg font-bold text-white">{MONTHS[selectedIndex]} 细节</h3>
            </div>
            <div className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1 text-xs text-cyan-200">当前月份</div>
          </div>
          <div className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {selectedFacts.map(([k, v]) => (
              <div key={k} className="min-w-0 rounded-2xl border border-white/10 bg-white/5 p-3 sm:p-4">
                <div className="text-[11px] uppercase tracking-[0.22em] text-slate-400">{k}</div>
                <div className="mt-2 break-words text-lg font-bold text-white sm:text-xl">{v}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="min-w-0 overflow-hidden rounded-[24px] border border-white/10 bg-black/20 p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Location & visit window</div>
              <h3 className="mt-1 text-lg font-bold text-white">位置与访问建议</h3>
            </div>
            <MapPin size={18} className="text-cyan-300" />
          </div>
          <div className="space-y-3 break-words text-sm leading-7 text-slate-300/90">
            <div>· 最热月份：<span className="font-semibold text-white">{MONTHS[hottest]}</span></div>
            <div>· 最冷月份：<span className="font-semibold text-white">{MONTHS[coldest]}</span></div>
            <div>· 降水最多：<span className="font-semibold text-white">{MONTHS[wettest]}</span></div>
            <div>· 降水最少：<span className="font-semibold text-white">{MONTHS[driest]}</span></div>
            <div>· 最晴朗月份：<span className="font-semibold text-white">{MONTHS[clearest]}</span></div>
            <div>· 最佳旅游月：<span className="font-semibold text-white">{MONTHS[bestTourismMonth]}</span></div>
            <div>· 经验结论：<span className="font-semibold text-white">{data.yearly.best_time}</span></div>
          </div>
          <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm leading-7 text-slate-300/90">
            {data.yearly.overview}
            <div className="mt-2 flex items-center gap-2 text-xs text-slate-400">
              <ArrowUpRight size={14} />
              <span>当前页面是静态气候摘要，适合做城市气候介绍、旅行窗口判断和月度对比。</span>
            </div>
          </div>
        </section>
      </div>

      <div className="mt-5 min-w-0 overflow-hidden rounded-[24px] border border-white/10 bg-black/20">
        <div className="border-b border-white/10 px-4 py-3">
          <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Monthly table</div>
          <div className="mt-1 text-lg font-bold text-white">全年月度概览</div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1180px] border-collapse text-left text-sm">
            <thead className="bg-white/5 text-slate-300">
              <tr>
                {['月份', '均温', '高温', '低温', '体感', '降水概率', '降水量', '湿度', '露点', '云量', '晴朗率', '风速', '风向', '旅游指数', '沙滩/泳池'].map(head => (
                  <th key={head} className="px-4 py-3 font-medium">{head}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {monthlySorted.map((item, idx) => (
                <tr key={item.month} className={idx === selectedIndex ? 'bg-cyan-400/10' : 'border-t border-white/5'}>
                  <td className="px-4 py-3 text-white">{MONTHS[idx]}</td>
                  <td className="px-4 py-3">{oneDecimal(item.temp_avg, '°C')}</td>
                  <td className="px-4 py-3">{oneDecimal(item.temp_max, '°C')}</td>
                  <td className="px-4 py-3">{oneDecimal(item.temp_min, '°C')}</td>
                  <td className="px-4 py-3">{oneDecimal(item.apparent_temp_avg ?? item.temp_avg, '°C')}</td>
                  <td className="px-4 py-3">{oneDecimal(item.precip_probability, '%')}</td>
                  <td className="px-4 py-3">{oneDecimal(item.precip, ' mm')}</td>
                  <td className="px-4 py-3">{oneDecimal(item.humidity, '%')}</td>
                  <td className="px-4 py-3">{oneDecimal(item.dew_point_avg, '°C')}</td>
                  <td className="px-4 py-3">{oneDecimal(item.cloud, '%')}</td>
                  <td className="px-4 py-3">{oneDecimal(item.sunny_rate, '%')}</td>
                  <td className="px-4 py-3">{oneDecimal(item.wind, ' m/s')}</td>
                  <td className="px-4 py-3">{item.wind_dir_text || '—'}</td>
                  <td className="px-4 py-3">{oneDecimal(item.tourism_score, '')}</td>
                  <td className="px-4 py-3">{oneDecimal(item.beach_score, '')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
};

function ChartCard({ eyebrow, title, note, children }: { eyebrow: string; title: string; note: string; children: React.ReactNode }) {
  return (
    <section className="min-w-0 overflow-hidden rounded-[24px] border border-white/10 bg-black/20 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">{eyebrow}</div>
          <h3 className="mt-1 break-words text-lg font-bold text-white">{title}</h3>
        </div>
      </div>
      {children}
      <div className="mt-3 text-xs leading-6 text-slate-400">{note}</div>
    </section>
  );
}

export default ClimateDashboard;
