import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import type { HeatmapZone, EvacRoute, RiskState, SpatialSummaryResponse } from '../../types';
import { useMapStore } from '../../store';
import { RISK_COLORS } from '../../utils/riskColors';
import { fetchSpatialSummary } from '../../services/api';

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
  const hazardLayerRef = useRef<L.LayerGroup>(L.layerGroup());
  const elevationLayerRef = useRef<L.LayerGroup>(L.layerGroup());

  const { activeLayer, timeHorizon } = useMapStore();
  const [spatialInfo, setSpatialInfo] = useState<SpatialSummaryResponse | null>(null);

  // ── Fetch Spatial Summary ───────────────────────────────────────────────
  useEffect(() => {
    fetchSpatialSummary()
      .then((data) => setSpatialInfo(data))
      .catch((err) => console.warn('[SituationalMap] Spatial summary fetch failed:', err));
  }, []);

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
    hazardLayerRef.current.addTo(map);
    elevationLayerRef.current.addTo(map);

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

  // ── Update Spatial Hazard & Elevation Overlays dynamically based on provenance ─
  useEffect(() => {
    const hazardLayer = hazardLayerRef.current;
    const elevLayer = elevationLayerRef.current;
    hazardLayer.clearLayers();
    elevLayer.clearLayers();

    // 1. Hazard Layer Rendering Policy:
    // If an authoritative dataset is loaded, render its features.
    // Otherwise render provisional river corridor geometry explicitly labeled PROVISIONAL.
    if (spatialInfo?.hazard_layers?.is_available && spatialInfo.hazard_layers.hazard_features.length > 0) {
      spatialInfo.hazard_layers.hazard_features.forEach((feat) => {
        if (feat.geometry?.type === 'Polygon' && feat.geometry.coordinates?.[0]) {
          const coords = feat.geometry.coordinates[0].map(([lng, lat]: [number, number]) => [lat, lng] as L.LatLngTuple);
          L.polygon(coords, {
            color: '#e63946',
            fillColor: '#e63946',
            fillOpacity: 0.3,
            weight: 2,
          }).addTo(hazardLayer).bindTooltip(`[AUTHORITATIVE] ${feat.properties?.name || 'Hazard Zone'}`, { direction: 'top' });
        }
      });
    } else {
      // PROVISIONAL RIVER PROXIMITY DEMONSTRATION GEOMETRY
      const yamunaCorridor: L.LatLngTuple[] = [
        [28.6650, 77.2280],
        [28.6550, 77.2320],
        [28.6400, 77.2360],
        [28.6250, 77.2420],
        [28.6250, 77.2500],
        [28.6420, 77.2440],
        [28.6580, 77.2390],
        [28.6660, 77.2340],
      ];
      L.polygon(yamunaCorridor, {
        color: '#ff9800',
        fillColor: '#ff9800',
        fillOpacity: 0.2,
        weight: 2,
        dashArray: '6 6',
      }).addTo(hazardLayer).bindTooltip(
        '[PROVISIONAL DEMONSTRATION] Yamuna River Proximity Corridor — NOT an official flood forecast or authoritative inundation map',
        { direction: 'top' }
      );
    }

    // 2. DEM Elevation Layer Rendering Policy:
    // Only render elevation markers if a real DEM dataset is enabled and available.
    // Never render fabricated elevation values when DEM is unavailable.
    if (spatialInfo?.dem_enabled) {
      const elevIcon = (text: string) => L.divIcon({
        html: `<div style="background:rgba(15,28,44,0.9);border:1px solid #35c7d9;border-radius:4px;padding:2px 5px;font-size:9px;color:#8fe6ef;font-weight:700;white-space:nowrap;box-shadow:0 2px 6px rgba(0,0,0,0.5)">▲ ${text}</div>`,
        className: '', iconAnchor: [30, 10],
      });
      L.marker([28.6448, 77.2167], { icon: elevIcon('Connaught Place: DEM Measured'), interactive: false }).addTo(elevLayer);
      L.marker([28.6530, 77.2320], { icon: elevIcon('Yamuna Bank: DEM Measured'), interactive: false }).addTo(elevLayer);
    }
  }, [spatialInfo]);

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

    // 1. Render alternative routes first (translucent background polylines)
    if (routes.alternatives && routes.alternatives.length > 0) {
      routes.alternatives.forEach((alt, idx) => {
        if (!alt.waypoints || alt.waypoints.length === 0) return;
        const altLatLngs = alt.waypoints.map(w => [w.lat, w.lng] as L.LatLngTuple);
        const isBlocked = alt.isBlocked;
        const altColor = isBlocked ? '#ff5d6c' : '#ffc277';

        L.polyline(altLatLngs, {
          color: altColor,
          weight: 3,
          opacity: 0.55,
          dashArray: '5 5',
        }).addTo(layer).bindTooltip(
          `ALT ROUTE: ${alt.name} | ETA: ${alt.eta}m | Safety: ${Math.round(alt.safetyScore * 100)}% ${isBlocked ? '(BLOCKED)' : ''}`,
          { direction: 'top', className: 'map-tooltip' }
        );
      });
    }

    // 2. Render recommended route (bold primary polyline)
    const rec = routes.recommended;
    if (rec && rec.waypoints && rec.waypoints.length > 0) {
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
    hazardLayerRef.current.eachLayer(l => {
      (l as any).setStyle?.({ fillOpacity: activeLayer === 'hazards' ? 0.35 : 0.05, opacity: activeLayer === 'hazards' ? 0.9 : 0.2 });
    });
    elevationLayerRef.current.eachLayer(l => {
      if ((l as any).setOpacity) (l as any).setOpacity(activeLayer === 'elevation' ? 1 : 0.0);
    });
  }, [activeLayer]);

  const timeLabel = TIME_LABELS[timeHorizon] ?? 'CURRENT';
  const nowStr = new Date().toLocaleTimeString('en-GB', { hour12: false }).slice(0, 5);

  const isDemUnavailable = !spatialInfo?.dem_enabled;
  const isHazardProvisional = !spatialInfo?.hazard_layers?.is_available;

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

      {/* Elevation layer status notice overlay when active */}
      {activeLayer === 'elevation' && isDemUnavailable && (
        <div
          className="absolute top-[70px] right-[14px] z-[400] rounded-[9px] px-3 py-[10px] text-[10px]"
          style={{ background: 'rgba(25,18,10,0.92)', border: '1px solid #d97706', color: '#fef3c7' }}
        >
          <div className="font-bold uppercase text-[#f59e0b] mb-1">DEM ELEVATION: UNAVAILABLE</div>
          <div className="text-[9px] text-[#fde68a] max-w-[220px]">
            No real DEM dataset configured. No fabricated elevation measurements displayed. (provenance: elevation:unavailable)
          </div>
        </div>
      )}

      {/* Hazard layer status notice overlay when active */}
      {activeLayer === 'hazards' && isHazardProvisional && (
        <div
          className="absolute top-[70px] right-[14px] z-[400] rounded-[9px] px-3 py-[10px] text-[10px]"
          style={{ background: 'rgba(25,18,10,0.92)', border: '1px solid #d97706', color: '#fef3c7' }}
        >
          <div className="font-bold uppercase text-[#f59e0b] mb-1">PROVISIONAL RIVER PROXIMITY CONTEXT</div>
          <div className="text-[9px] text-[#fde68a] max-w-[240px]">
            Yamuna river-distance demonstration geometry. NOT an official flood forecast or authoritative flood zone. (provenance: hazard:provisional_river_proximity)
          </div>
        </div>
      )}

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
    { key: 'risk' as const,      label: 'Risk' },
    { key: 'route' as const,     label: 'Routes' },
    { key: 'assets' as const,    label: 'Assets' },
    { key: 'hazards' as const,   label: 'Hazards' },
    { key: 'elevation' as const, label: 'Elevation' },
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
