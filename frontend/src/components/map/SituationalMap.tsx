import { useEffect, useRef } from 'react';
import L from 'leaflet';
import type { HeatmapZone, EvacRoute, RiskState } from '../../types';
import { useMapStore } from '../../store';
import { RISK_COLORS } from '../../utils/riskColors';

const TIME_LABELS = ['CURRENT', 'PREDICTED +10M', 'PREDICTED +20M', 'PREDICTED +30M'];

interface SituationalMapProps {
  riskState: RiskState;
  routes: { recommended: EvacRoute; alternatives: EvacRoute[] };
}

export function SituationalMap({ riskState, routes }: SituationalMapProps) {
  const mapRef = useRef<L.Map | null>(null);
  const mapDivRef = useRef<HTMLDivElement>(null);
  const riskLayerRef = useRef<L.LayerGroup>(L.layerGroup());
  const routeLayerRef = useRef<L.LayerGroup>(L.layerGroup());
  const assetLayerRef = useRef<L.LayerGroup>(L.layerGroup());

  const { activeLayer, timeHorizon } = useMapStore();

  // ── Init map ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (mapRef.current || !mapDivRef.current) return;

    const map = L.map(mapDivRef.current, {
      center: [28.6448, 77.2167],
      zoom: 14,
      zoomControl: true,
      attributionControl: false,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
    }).addTo(map);

    riskLayerRef.current.addTo(map);
    routeLayerRef.current.addTo(map);
    assetLayerRef.current.addTo(map);

    // Static assets
    const assetLayer = assetLayerRef.current;

    // Shelter marker
    const shelterIcon = L.divIcon({
      html: `<div style="width:14px;height:14px;border-radius:50%;background:#4bd39b;border:2px solid #07111f;box-shadow:0 0 8px rgba(75,211,155,0.6)"></div>`,
      iconSize: [14, 14], iconAnchor: [7, 7], className: '',
    });
    L.marker([28.6310, 77.2450], { icon: shelterIcon })
      .addTo(assetLayer)
      .bindTooltip('SHELTER-04', { permanent: true, direction: 'right', className: 'map-tooltip' });

    // Sensor markers
    const sensorIcon = (label: string) => L.divIcon({
      html: `<div style="display:flex;flex-direction:column;align-items:center"><div style="width:10px;height:10px;border-radius:50%;background:#35c7d9;border:2px solid #07111f;box-shadow:0 0 6px rgba(53,199,217,0.6)"></div><span style="font-size:8px;color:#35c7d9;font-weight:800;margin-top:2px;white-space:nowrap">${label}</span></div>`,
      iconSize: [40, 28], iconAnchor: [20, 5], className: '',
    });
    L.marker([28.6560, 77.2210], { icon: sensorIcon('S-21') }).addTo(assetLayer);
    L.marker([28.6600, 77.2080], { icon: sensorIcon('S-08') }).addTo(assetLayer);

    // Sector labels
    const labelIcon = (text: string) => L.divIcon({
      html: `<span style="font-size:10px;color:#b7c9d8;font-weight:800;letter-spacing:1px;text-shadow:0 1px 4px #000">${text}</span>`,
      className: '', iconAnchor: [0, 0],
    });
    L.marker([28.6448, 77.2090], { icon: labelIcon('SECTOR A'), interactive: false }).addTo(assetLayer);
    L.marker([28.6530, 77.2280], { icon: labelIcon('SECTOR B'), interactive: false }).addTo(assetLayer);
    L.marker([28.6290, 77.2430], { icon: labelIcon('SECTOR C'), interactive: false }).addTo(assetLayer);

    mapRef.current = map;
  }, []);

  // ── Update risk zones when horizon changes ──────────────────────────────
  useEffect(() => {
    const layer = riskLayerRef.current;
    layer.clearLayers();

    riskState.heatmapZones.forEach((zone: HeatmapZone) => {
      L.circle([zone.lat, zone.lng], {
        radius: zone.radiusMeters,
        color: RISK_COLORS[zone.level],
        fillColor: RISK_COLORS[zone.level],
        fillOpacity: 0.18,
        weight: 0,
      }).addTo(layer);
    });
  }, [riskState]);

  // ── Update route layer ──────────────────────────────────────────────────
  useEffect(() => {
    const layer = routeLayerRef.current;
    layer.clearLayers();

    const rec = routes.recommended;
    const latlngs = rec.waypoints.map(w => [w.lat, w.lng] as L.LatLngTuple);

    L.polyline(latlngs, {
      color: '#35c7d9',
      weight: 5,
      opacity: 0.95,
      dashArray: '10 7',
    }).addTo(layer);

    // Waypoint dots
    rec.waypoints.forEach((wp, i) => {
      const isLast = i === rec.waypoints.length - 1;
      const color = isLast ? '#4bd39b' : '#d9eef5';
      L.circleMarker([wp.lat, wp.lng], {
        radius: isLast ? 9 : 6,
        color: '#08121f',
        fillColor: color,
        fillOpacity: 1,
        weight: 2,
      }).addTo(layer).bindTooltip(wp.label, { direction: 'top', className: 'map-tooltip' });
    });

    // Route label
    if (latlngs.length >= 2) {
      const midIdx = Math.floor(latlngs.length / 2);
      const midPt = latlngs[midIdx];
      const labelIcon = L.divIcon({
        html: `<span style="font-size:9px;color:#8fe6ef;font-weight:800;letter-spacing:0.8px;text-shadow:0 1px 4px #000;white-space:nowrap">RECOMMENDED EVACUATION ROUTE</span>`,
        className: '', iconAnchor: [80, 18],
      });
      L.marker(midPt as L.LatLngTuple, { icon: labelIcon, interactive: false }).addTo(layer);
    }
  }, [routes]);

  // ── Layer visibility ────────────────────────────────────────────────────
  useEffect(() => {
    riskLayerRef.current.eachLayer(l => {
      (l as any).setStyle?.({ fillOpacity: activeLayer === 'risk' ? 0.18 : 0.05 });
    });
    routeLayerRef.current.eachLayer(l => {
      (l as any).setStyle?.({ opacity: activeLayer === 'route' ? 0.95 : 0.3 });
    });
    assetLayerRef.current.eachLayer(l => {
      if ((l as any).setOpacity) (l as any).setOpacity(activeLayer === 'assets' ? 1 : 0.45);
    });
  }, [activeLayer]);

  const timeLabel = TIME_LABELS[timeHorizon] ?? 'CURRENT';
  const nowStr = new Date().toLocaleTimeString('en-GB', { hour12: false }).slice(0, 5);

  return (
    <div className="relative w-full h-full">
      {/* Map toolbar */}
      <MapToolbar />

      {/* Leaflet container */}
      <div
        ref={mapDivRef}
        className="absolute inset-0 top-[55px]"
        style={{ background: '#0a1828' }}
      />

      {/* Status overlay */}
      <div
        className="absolute top-[70px] left-[14px] z-[400] rounded-[9px] px-3 py-[10px] text-[11px]"
        style={{ background: 'rgba(7,17,31,0.88)', border: '1px solid #21334a' }}
      >
        <b>{timeHorizon === 0 ? `CURRENT · ${nowStr}` : `PREDICTED · ${riskState.label}`}</b>
        <div className="text-ax-muted text-[9px] mt-[3px] max-w-[200px]">
          {riskState.mapStatusText}
        </div>
      </div>

      {/* Legend */}
      <div
        className="absolute bottom-[14px] left-[14px] z-[400] rounded-[9px] px-3 py-[10px] text-[9px] text-ax-muted"
        style={{ background: 'rgba(7,17,31,0.88)', border: '1px solid #21334a' }}
      >
        <div className="text-[#dce8f2] font-extrabold mb-[6px]">RISK LEVEL</div>
        {(['CRITICAL', 'HIGH', 'MODERATE', 'LOW'] as const).map(level => (
          <div key={level} className="flex items-center gap-[7px] my-[5px]">
            <i className="w-[9px] h-[9px] rounded-full" style={{ background: RISK_COLORS[level] }} />
            <span className="capitalize">{level.charAt(0) + level.slice(1).toLowerCase()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MapToolbar() {
  const { activeLayer, setLayer } = useMapStore();
  const layers = [
    { key: 'risk' as const,   label: 'Risk' },
    { key: 'route' as const,  label: 'Routes' },
    { key: 'assets' as const, label: 'Assets' },
  ];

  return (
    <div className="absolute top-0 right-0 h-[55px] flex items-center gap-[6px] pr-4 z-[500]">
      {layers.map(({ key, label }) => (
        <button
          key={key}
          onClick={() => setLayer(key)}
          className="text-[10px] px-[9px] py-[6px] rounded-[7px] cursor-pointer transition-all duration-150"
          style={{
            border: `1px solid ${activeLayer === key ? '#2f7890' : '#21334a'}`,
            background: activeLayer === key ? '#123047' : '#0b1829',
            color: activeLayer === key ? '#fff' : '#a8bbcd',
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
