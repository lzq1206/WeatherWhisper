import React, { useEffect, useMemo, useState } from 'react';
import { MapPin, Search, CalendarDays, ThermometerSun, CloudSun, Sparkles } from 'lucide-react';
import ClimateMap from './components/ClimateMap';
import ClimateDashboard from './components/ClimateDashboard';
import TimeSlider from './components/TimeSlider';

type StationFeature = {
  type: 'Feature';
  geometry: { type: 'Point'; coordinates: [number, number] };
  properties: {
    id: string;
    city: string;
    province?: string;
    best_time?: string;
    overview?: string;
    avg_temp?: number;
    total_precip?: number;
    avg_humidity?: number;
    avg_wind?: number;
    total_solar?: number;
    avg_cloud?: number;
    tourism_score_avg?: number;
    water_temp?: number;
    growing_season?: number;
    solar_energy?: number;
    [key: string]: any;
  };
};

type StationListItem = StationFeature['properties'] & {
  id: string;
  city: string;
  province?: string;
};

const BASE_PATH = import.meta.env.BASE_URL;
const MONTH_LABELS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];

function pickLeadStation(stations: StationListItem[]) {
  const preferred = stations.find(item => item.id === 'prefecture-guangzhou')
    ?? stations.find(item => item.id === 'prefecture-shijiazhuang')
    ?? stations.find(item => item.id === '583620');
  return preferred ?? stations[0] ?? null;
}

function App() {
  const [stations, setStations] = useState<StationListItem[]>([]);
  const [selectedStationId, setSelectedStationId] = useState<string>('');
  const [selectedMonth, setSelectedMonth] = useState<number>(new Date().getMonth() + 1);
  const [query, setQuery] = useState('');
  const [isSearchFocused, setIsSearchFocused] = useState(false);

  useEffect(() => {
    fetch(`${BASE_PATH}/data/stations.geojson`)
      .then(res => res.json())
      .then((json: { features?: StationFeature[] }) => {
        const unique = new Map<string, StationListItem>();
        (json.features || []).forEach(feature => {
          const id = feature.properties?.id;
          const city = feature.properties?.city;
          if (!id || !city || unique.has(id)) return;
          unique.set(id, {
            ...feature.properties,
            id,
            city,
          });
        });
        const list = Array.from(unique.values()).sort((a, b) => {
          const left = `${a.province || ''}${a.city}`;
          const right = `${b.province || ''}${b.city}`;
          return left.localeCompare(right, 'zh-Hans-CN');
        });
        setStations(list);
      })
      .catch(err => console.error('Failed to load stations.geojson:', err));
  }, []);

  useEffect(() => {
    if (!stations.length) return;
    if (selectedStationId && stations.some(item => item.id === selectedStationId)) return;
    const lead = pickLeadStation(stations);
    if (lead) setSelectedStationId(lead.id);
  }, [stations, selectedStationId]);

  const selectedStation = useMemo(
    () => stations.find(item => item.id === selectedStationId) ?? pickLeadStation(stations),
    [stations, selectedStationId]
  );

  const searchMatches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return stations.filter(item => {
      const hay = `${item.city} ${item.city_en || ''} ${item.province || ''} ${item.province_en || ''} ${item.id} ${item.source_station_id || ''} ${item.source_station_name || ''} ${item.station_match_quality || ''} ${item.best_time || ''} ${item.overview || ''}`.toLowerCase();
      return hay.includes(q);
    }).slice(0, 10);
  }, [stations, query]);

  const groupedStationOptions = useMemo(() => {
    const groups = new Map<string, StationListItem[]>();
    stations.forEach(item => {
      const province = item.province || '其他地区';
      if (!groups.has(province)) groups.set(province, []);
      groups.get(province)!.push(item);
    });
    return Array.from(groups.entries()).map(([province, items]) => ({ province, items }));
  }, [stations]);

  const showSearchSuggestions = isSearchFocused && query.trim().length > 0;

  const handleSearchSelect = (item: StationListItem) => {
    setSelectedStationId(item.id);
    setQuery(item.province ? `${item.province} · ${item.city}` : item.city);
    setIsSearchFocused(false);
  };

  const heroChips = useMemo(() => {
    if (!selectedStation) return [];
    return [
      selectedStation.province ? `${selectedStation.province} · ${selectedStation.city}` : selectedStation.city,
      selectedStation.admin_level ? `${selectedStation.admin_level}口径` : '地级行政区口径',
      `气象站 ${selectedStation.source_station_id || selectedStation.id}`,
      selectedStation.best_time ? `最佳访问 ${selectedStation.best_time}` : '全年气候页',
      selectedStation.overview || '中国区域气候概览',
    ];
  }, [selectedStation]);

  const quickMetrics = useMemo(() => {
    if (!selectedStation) return [];
    return [
      { icon: ThermometerSun, label: '平均气温', value: selectedStation.avg_temp != null ? `${Number(selectedStation.avg_temp).toFixed(1)}°C` : '—' },
      { icon: CloudSun, label: '年降水', value: selectedStation.total_precip != null ? `${Number(selectedStation.total_precip).toFixed(0)} mm` : '—' },
      { icon: CloudSun, label: '平均云量', value: selectedStation.avg_cloud != null ? `${Number(selectedStation.avg_cloud).toFixed(1)}%` : '—' },
      { icon: Sparkles, label: '旅游平均分', value: selectedStation.tourism_score_avg != null ? `${Number(selectedStation.tourism_score_avg).toFixed(1)} / 10` : '—' },
    ];
  }, [selectedStation]);

  const heroTitle = selectedStation ? `${selectedStation.city} · 气候年鉴` : 'WeatherWhisper · 中国气候页';
  const heroSubtitle = selectedStation
    ? `${selectedStation.overview || '以月份为轴展示全年气候节律、温度带、降水峰值和最佳访问时间。'} 这里的页面采用气候年鉴式信息组织：先给结论，再给月度曲线和细节拆解。`
    : '以气候年鉴式的信息组织方式展示中国站点的全年气候：先看概览，再看月度曲线、年度平均和最佳访问时间。';

  return (
    <div className="min-h-screen text-slate-100 relative overflow-x-hidden">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(56,189,248,.18),transparent_35%),radial-gradient(circle_at_85%_15%,rgba(168,85,247,.16),transparent_28%),linear-gradient(180deg,#020617_0%,#07111f_50%,#020617_100%)]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-gradient-to-b from-cyan-400/10 to-transparent blur-3xl" />

      <div className="relative mx-auto w-full max-w-[1600px] px-3 py-4 sm:px-4 md:px-6 lg:px-8 lg:py-6">
        <header className="grid min-w-0 gap-5 xl:grid-cols-[1.25fr_.75fr]">
          <section className="min-w-0 overflow-hidden rounded-[24px] border border-white/10 bg-white/6 p-4 shadow-[0_24px_80px_rgba(0,0,0,.35)] backdrop-blur-2xl sm:p-5 md:p-7">
            <div className="flex flex-wrap items-center gap-3 text-[11px] uppercase tracking-[0.28em] text-cyan-200/80">
              <span className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1">WeatherWhisper</span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1">China climate atlas page</span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1">333 prefecture-level admin units</span>
            </div>

            <div className="mt-5 grid min-w-0 gap-6 xl:grid-cols-[1.15fr_.85fr] xl:items-end">
              <div className="min-w-0">
                <h1 className="break-words text-3xl font-black leading-[1.08] tracking-tight text-white drop-shadow-[0_12px_30px_rgba(0,0,0,.45)] sm:text-4xl md:text-5xl">
                  {heroTitle}
                </h1>
                <p className="mt-4 max-w-none text-sm leading-7 text-slate-300/90 sm:leading-8 md:text-base">
                  {heroSubtitle}
                </p>

                <div className="mt-5 flex flex-wrap gap-2.5">
                  {heroChips.map(chip => (
                    <span key={chip} className="max-w-full break-words rounded-full border border-white/10 bg-white/6 px-3 py-1.5 text-xs text-slate-200/90">
                      {chip}
                    </span>
                  ))}
                </div>

                <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  {quickMetrics.map(item => (
                    <div key={item.label} className="min-w-0 rounded-2xl border border-white/10 bg-black/20 p-3 shadow-inner shadow-black/10 sm:p-4">
                      <div className="flex items-center gap-3 text-slate-300/80">
                        <item.icon size={16} className="text-cyan-300" />
                        <span className="text-[10px] uppercase tracking-[0.18em] sm:text-[11px] sm:tracking-[0.24em]">{item.label}</span>
                      </div>
                      <div className="mt-3 break-words text-base font-bold text-white sm:text-lg">{item.value}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="min-w-0 overflow-hidden rounded-[24px] border border-white/10 bg-black/20 p-4 shadow-2xl shadow-black/20 sm:p-5">
                <div className="flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Admin-unit switcher</div>
                    <div className="mt-1 break-words text-base font-bold text-white sm:text-lg">选择一个地级行政区</div>
                  </div>
                  <CalendarDays className="text-cyan-300" size={18} />
                </div>

                <div className="mt-4 block">
                  <span className="mb-2 block text-[11px] uppercase tracking-[0.24em] text-slate-400">Search / 查找地级行政区</span>
                  <div className="relative">
                    <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/6 px-3 py-2.5">
                      <Search size={16} className="text-slate-400" />
                      <input
                        value={query}
                        onFocus={() => setIsSearchFocused(true)}
                        onBlur={() => window.setTimeout(() => setIsSearchFocused(false), 120)}
                        onChange={e => setQuery(e.target.value)}
                        placeholder="输入地级行政区、省份、气象站或描述"
                        className="w-full bg-transparent text-sm outline-none placeholder:text-slate-500"
                      />
                    </div>

                    {showSearchSuggestions ? (
                      <div className="absolute left-0 right-0 top-[calc(100%+.5rem)] z-40 max-h-72 overflow-auto rounded-2xl border border-white/10 bg-slate-950/95 p-2 shadow-2xl shadow-black/40 backdrop-blur-xl">
                        {searchMatches.length ? searchMatches.map(item => (
                          <button
                            key={item.id}
                            type="button"
                            onMouseDown={e => e.preventDefault()}
                            onClick={() => handleSearchSelect(item)}
                            className="block w-full rounded-xl px-3 py-2.5 text-left text-sm text-slate-200 transition hover:bg-cyan-400/10 hover:text-white"
                          >
                            <span className="font-semibold text-white">{item.city}</span>
                            <span className="ml-2 text-xs text-slate-400">{item.province || '其他地区'} · 气象站 {item.source_station_id || item.id}</span>
                          </button>
                        )) : (
                          <div className="px-3 py-3 text-sm text-slate-400">没有匹配的地级行政区</div>
                        )}
                      </div>
                    ) : null}
                  </div>
                </div>

                <label className="mt-4 block">
                  <span className="mb-2 block text-[11px] uppercase tracking-[0.24em] text-slate-400">Province / City selector · 省级 / 市级选择</span>
                  <select
                    value={selectedStationId}
                    onChange={e => {
                      setSelectedStationId(e.target.value);
                      setQuery('');
                    }}
                    className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-3 py-3 text-sm text-white outline-none"
                  >
                    {groupedStationOptions.map(group => (
                      <optgroup key={group.province} label={group.province}>
                        {group.items.map(item => (
                          <option key={item.id} value={item.id}>
                            {item.city} ({item.source_station_id || item.id})
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </label>

                <div className="mt-4 rounded-2xl border border-white/10 bg-gradient-to-br from-cyan-500/10 via-slate-900/30 to-indigo-500/10 p-4 text-sm leading-7 text-slate-300/90">
                  <div className="font-semibold text-white">页面目标</div>
                  <div className="mt-1">
                    采用气候年鉴式的信息层次：先给全年概览，再拆分高低温、小时温度、云量、降水、湿度体感、风速风向与旅游指数。
                  </div>
                </div>
              </div>
            </div>
          </section>

          <aside className="grid min-w-0 gap-5">
            <section className="min-w-0 overflow-hidden rounded-[28px] border border-white/10 bg-white/6 p-4 shadow-[0_24px_80px_rgba(0,0,0,.35)] backdrop-blur-2xl sm:p-6">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Fast facts</div>
                  <h2 className="mt-1 break-words text-xl font-black text-white sm:text-2xl">年度气候快照</h2>
                </div>
                <div className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1 text-xs text-emerald-200">
                  选择即联动
                </div>
              </div>

              <div className="mt-5 grid min-w-0 gap-3 sm:grid-cols-2">
                {selectedStation ? [
                  ['城市', selectedStation.city],
                  ['省份', selectedStation.province || '—'],
                  ['行政级别', selectedStation.admin_level || '地级行政区'],
                  ['气象站', selectedStation.source_station_id || selectedStation.id],
                  ['最佳时段', selectedStation.best_time || '—'],
                ].map(([k, v]) => (
                  <div key={k} className="min-w-0 rounded-2xl border border-white/10 bg-black/20 p-3 sm:p-4">
                    <div className="text-[11px] uppercase tracking-[0.22em] text-slate-400">{k}</div>
                    <div className="mt-2 break-words text-sm font-semibold text-white">{v}</div>
                  </div>
                )) : (
                  <div className="rounded-2xl border border-white/10 bg-black/20 p-4 text-sm text-slate-300">
                    正在加载站点数据…
                  </div>
                )}
              </div>

              <div className="mt-5 rounded-2xl border border-white/10 bg-black/20 p-4 text-sm leading-7 text-slate-300/90">
                <div className="font-semibold text-white">阅读方式</div>
                <ul className="mt-2 space-y-1.5 list-disc pl-5">
                  <li>用月份切换来查看高温、低温和降水峰值。</li>
                  <li>从温度曲线判断季节跨度，再用降水/湿度理解体感。</li>
                  <li>下方地图可直接切换站点，保留中国站点浏览入口。</li>
                </ul>
              </div>
            </section>
          </aside>
        </header>

        <main className="mt-6 space-y-6">
          <div className="grid gap-6 xl:grid-cols-[1.35fr_.65fr]">
            <div className="space-y-6 min-w-0">
              <ClimateDashboard
                stationId={selectedStationId || selectedStation?.id || 'prefecture-guangzhou'}
                selectedMonth={selectedMonth}
              />

              <section className="rounded-[28px] border border-white/10 bg-white/6 backdrop-blur-2xl p-5 shadow-[0_24px_80px_rgba(0,0,0,.30)] min-w-0 overflow-hidden">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Monthly explorer</div>
                    <h2 className="mt-1 text-xl font-black text-white">月份切换</h2>
                  </div>
                  <div className="text-xs text-slate-400">当前高亮：{MONTH_LABELS[selectedMonth - 1]}</div>
                </div>
                <TimeSlider currentMonth={selectedMonth} onChange={setSelectedMonth} />
              </section>
            </div>

            <aside className="space-y-6 min-w-0">
              <section className="rounded-[28px] border border-white/10 bg-white/6 backdrop-blur-2xl p-5 shadow-[0_24px_80px_rgba(0,0,0,.30)] min-w-0 overflow-hidden">
                <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Selected station</div>
                <div className="mt-1 break-words text-xl font-black text-white">{selectedStation ? `${selectedStation.city}` : '—'}</div>
                <div className="mt-4 space-y-3 break-words text-sm leading-7 text-slate-300/90">
                  <div>· 这是一页静态气候图谱，适合做“先概览、后细节”的城市气候说明。</div>
                  <div>· 页面已覆盖温度、小时温度、云量、降水、湿度体感、风速风向和旅游指数方法。</div>
                  <div>· 当前页面保留站点切换、月份切换、年度曲线、数据表和地图浏览四层交互。</div>
                </div>
              </section>
            </aside>
          </div>

          <ClimateMap
            onStationSelect={setSelectedStationId}
            selectedMonth={selectedMonth}
            selectedStationId={selectedStationId}
          />
        </main>
      </div>
    </div>
  );
}

export default App;
