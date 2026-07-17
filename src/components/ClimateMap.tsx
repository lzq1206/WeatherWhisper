import React, { useEffect, useMemo, useState } from 'react';
import DeckGL from '@deck.gl/react';
import { ScatterplotLayer } from '@deck.gl/layers';
import { Map } from 'react-map-gl/maplibre';
import InterpolationLayer from '../layers/InterpolationLayer';

interface StationFeature {
  type: 'Feature';
  geometry: {
    type: 'Point';
    coordinates: [number, number];
  };
  properties: {
    id: string;
    city: string;
    province?: string;
    [key: string]: any;
  };
}

interface ClimateMapProps {
  onStationSelect: (stationId: string) => void;
  selectedMonth: number;
  selectedStationId?: string;
}

const BASE_PATH = import.meta.env.BASE_URL;
const METRICS = [
  { id: 'avg_temp', label: '温度', unit: '°C', note: '年平均气温' },
  { id: 'total_precip', label: '降水', unit: 'mm', note: '年降水量' },
  { id: 'avg_humidity', label: '湿度', unit: '%', note: '年平均湿度' },
  { id: 'avg_wind', label: '风速', unit: 'm/s', note: '年平均风速' },
  { id: 'total_solar', label: '太阳辐射', unit: 'kWh/m²', note: '全年累计辐射' },
  { id: 'avg_cloud', label: '云量', unit: '%', note: '年平均云量' },
  { id: 'water_temp', label: '水温', unit: '°C', note: '估算水温' },
  { id: 'growing_season', label: '生长季', unit: '天', note: '适宜生长天数' },
  { id: 'solar_energy', label: '太阳能', unit: 'kWh', note: '可用太阳能潜力' },
];

const ClimateMap: React.FC<ClimateMapProps> = ({ onStationSelect, selectedMonth, selectedStationId }) => {
  const [data, setData] = useState<StationFeature[]>([]);
  const [metric, setMetric] = useState('avg_temp');

  useEffect(() => {
    fetch(`${BASE_PATH}data/stations.geojson`)
      .then(res => res.json())
      .then((json: { features?: StationFeature[] }) => {
        const unique = new globalThis.Map<string, StationFeature>();
        (json.features || []).forEach(feature => {
          const id = feature.properties?.id;
          if (!id || unique.has(id)) return;
          unique.set(id, feature);
        });
        setData(Array.from(unique.values()));
      })
      .catch(err => console.error('Failed to load stations:', err));
  }, []);


  const currentMetric = METRICS.find(item => item.id === metric) || METRICS[0];
  const selectedFeature = useMemo(
    () => data.find(item => item.properties.id === selectedStationId),
    [data, selectedStationId]
  );

  const layers = useMemo(() => [
    new InterpolationLayer({
      id: 'idw-layer',
      data,
      getPosition: (d: any) => d.geometry.coordinates,
      getValue: (d: any) => Number(d.properties[metric]) || 0,
      p: 2.5,
      opacity: 0.5,
      pickable: false,
    }),
    new ScatterplotLayer({
      id: 'stations-layer',
      data,
      pickable: true,
      radiusScale: 6,
      radiusMinPixels: 4,
      getPosition: (d: any) => d.geometry.coordinates,
      getRadius: (d: any) => (d.properties.id === selectedStationId ? 2400 : 1400),
      getFillColor: (d: any) => (d.properties.id === selectedStationId ? [34, 211, 238, 240] : [255, 255, 255, 200]),
      getLineColor: (d: any) => (d.properties.id === selectedStationId ? [255, 255, 255, 220] : [10, 15, 30, 180]),
      lineWidthMinPixels: 1,
      onClick: (info: any) => {
        if (info.object) {
          onStationSelect(info.object.properties.id);
        }
      },
    }),
  ], [data, metric, onStationSelect, selectedStationId]);

  const viewState = {
    longitude: 105,
    latitude: 35,
    zoom: 3.45,
    pitch: 0,
    bearing: 0,
  };

  const visibleStations = data.length;

  return (
    <section className="relative h-[520px] overflow-hidden rounded-[28px] border border-white/10 bg-white/6 shadow-[0_24px_80px_rgba(0,0,0,.30)] backdrop-blur-2xl sm:h-[620px] lg:h-[760px]">
      <div className="absolute left-3 top-3 z-20 w-[min(280px,calc(100%-1.5rem))] rounded-[22px] border border-white/10 bg-slate-950/80 p-3 shadow-2xl shadow-black/40 backdrop-blur-xl sm:left-4 sm:top-4 sm:w-[min(320px,calc(100%-2rem))] sm:p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Climate map</div>
            <div className="mt-1 text-lg font-bold text-white">中国气候站点</div>
          </div>
          <div className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-2.5 py-1 text-[11px] text-cyan-200">
            {visibleStations} stations
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2">
          {METRICS.map(m => (
            <button
              key={m.id}
              onClick={() => setMetric(m.id)}
              className={`rounded-xl border px-3 py-2 text-left text-xs transition-all duration-300 ${
                metric === m.id
                  ? 'border-cyan-300/40 bg-cyan-400/15 text-white shadow-[0_0_18px_rgba(34,211,238,.22)]'
                  : 'border-white/10 bg-white/5 text-slate-300 hover:bg-white/10 hover:border-white/20'
              }`}
            >
              <div className="font-semibold">{m.label}</div>
              <div className="mt-1 text-[10px] text-slate-400">{m.unit || '—'}</div>
            </button>
          ))}
        </div>

        <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-3 text-xs leading-6 text-slate-300">
          <div className="font-semibold text-white">当前图层</div>
          <div className="mt-1">{currentMetric.label} · {currentMetric.note}</div>
          <div>月份高亮：{selectedMonth} 月</div>
          {selectedFeature ? <div>选中站点：{selectedFeature.properties.city}</div> : null}
        </div>
      </div>

      <div className="absolute bottom-3 left-3 z-20 rounded-2xl border border-white/10 bg-slate-950/75 px-3 py-2 text-[11px] text-slate-300 backdrop-blur-xl sm:bottom-4 sm:left-4 sm:px-4 sm:py-3 sm:text-xs">
        <div className="font-semibold text-white">点击站点切换页面主视图</div>
        <div className="mt-1 text-slate-400">地图仅作站点浏览与局部气候分布参考。</div>
      </div>

      <DeckGL
        initialViewState={viewState}
        controller={true}
        layers={layers}
        style={{ width: '100%', height: '100%' }}
        getTooltip={({ object }: any) => {
          if (!object) return null;
          return {
            html: `
              <div style="background: rgba(2,6,23,0.92); color: white; padding: 12px 14px; border-radius: 14px; border: 1px solid rgba(255,255,255,0.15); font-family: sans-serif; min-width: 180px; box-shadow: 0 18px 40px rgba(0,0,0,.35);">
                <div style="font-weight: 700; margin-bottom: 6px; font-size: 13px;">${object.properties.city}</div>
                <div style="display: flex; justify-content: space-between; gap: 20px; align-items: center; font-size: 12px; line-height: 1.6;">
                  <span style="opacity: 0.72;">${currentMetric.label}</span>
                  <span style="font-weight: 600; color: #67e8f9;">${object.properties[metric]}${currentMetric.unit}</span>
                </div>
              </div>
            `,
            style: { backgroundColor: 'transparent', padding: '0px' },
          };
        }}
      >
        <Map
          style={{ width: '100%', height: '100%' }}
          mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
        />
      </DeckGL>
    </section>
  );
};

export default ClimateMap;
