<template>
  <div class="map-wrapper">
    <div ref="mapContainer" class="map-container"></div>
    <div class="dashboard-panel"></div>
    <div class="source-disclaimer">資料來源：交通部高速公路局「交通資料庫」</div>
  </div>
</template>

<script setup lang="ts">
import { ref, shallowRef, onMounted, onUnmounted, watch } from "vue";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

type FeatureProperties = Record<string, string | number | undefined>;

const mapContainer = shallowRef<HTMLElement | null>(null);
const map = shallowRef<maplibregl.Map | null>(null);

const MAX_LANES = 4;
const MACRO_LAYER_ID = "highway-macro";
const MICRO_LAYER_PREFIX = "highway-micro-lane-";
const TRANSPARENT = "rgba(0,0,0,0)";
const SPEED_API_URL = "/api/vd-speed";
const POLL_INTERVAL_MS = 60_000;

let pollTimer: ReturnType<typeof setInterval> | null = null;
const hoverPopup = shallowRef<maplibregl.Popup | null>(null);

const {
  data: speedData,
  refresh: refreshSpeedFetch,
  error: speedFetchError,
} = await useLazyFetch(SPEED_API_URL, {
  server: false,
  immediate: false,
  default: () => null,
});

type SpeedMap = NonNullable<typeof speedData.value>;
type SpeedItem = SpeedMap[string];

function readAvg(item: SpeedItem | undefined) {
  const avg = (item as { avg?: unknown } | undefined)?.avg;
  return typeof avg === "number" ? avg : undefined;
}

function readLaneSpeed(item: SpeedItem | undefined, laneIndex: number) {
  const lanes = (item as { lanes?: Record<string, unknown> } | undefined)?.lanes;
  if (!lanes) return undefined;

  const laneSpeed =
    lanes[String(laneIndex)] ?? lanes[String(laneIndex + 1)] ?? lanes[`${laneIndex}`] ?? lanes[`${laneIndex + 1}`];

  return typeof laneSpeed === "number" ? laneSpeed : undefined;
}

function speedToColor(speed: SpeedItem["avg"] | undefined) {
  if (typeof speed !== "number") return TRANSPARENT;
  if (speed >= 80) return "#00ff00";
  if (speed >= 60) return "#ffff00";
  if (speed >= 40) return "#ffa500";
  if (speed < 20) return "#8000ff";
  return "#ff0000";
}

function laneLayerId(laneIndex: number) {
  return `${MICRO_LAYER_PREFIX}${laneIndex}`;
}

function getSegmentName(properties: FeatureProperties | undefined, linkId: string) {
  return properties?.SectionName || properties?.RoadSectionName || properties?.RoadName || `Link ${linkId}`;
}

function formatSpeed(speed: number | undefined) {
  return typeof speed === "number" ? `${speed} km/h` : "--";
}

function buildPopupHTML(linkId: string, properties: FeatureProperties | undefined, zoomLevel: number) {
  const speedItem = speedData.value?.[linkId];
  const segmentName = getSegmentName(properties, linkId);
  const avgSpeed = formatSpeed(readAvg(speedItem));

  let lanesHtml = "";
  const lanes = (speedItem as { lanes?: Record<string, unknown> } | undefined)?.lanes;
  if (zoomLevel >= 13 && lanes && Object.keys(lanes).length > 0) {
    const laneEntries = Object.entries(lanes)
      .map(([lane, speed]) => [Number(lane), speed] as const)
      .sort((a, b) => a[0] - b[0]);

    const laneRows = laneEntries
      .map(([lane, speed]) => `<li>車道 ${lane}: ${formatSpeed(typeof speed === "number" ? speed : undefined)}</li>`)
      .join("");

    lanesHtml = `<hr style=\"border:0;border-top:1px solid rgba(255,255,255,.2);margin:8px 0;\"><ul style=\"margin:0;padding-left:16px;\">${laneRows}</ul>`;
  }

  return `<div style=\"font-size:12px;line-height:1.5;\"><div style=\"font-weight:700;margin-bottom:4px;\">${segmentName}</div><div>LinkID: ${linkId}</div><div>平均時速: ${avgSpeed}</div>${lanesHtml}</div>`;
}

function showHoverPopup(event: any) {
  const mapInstance = map.value;
  if (!mapInstance || !event.features?.length) return;

  const feature = event.features[0];
  const rawLinkId = feature?.properties?.LinkID;
  if (!rawLinkId) return;
  const linkId = String(rawLinkId);
  const properties = feature?.properties as FeatureProperties | undefined;

  if (!hoverPopup.value) {
    hoverPopup.value = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 12,
      className: "speed-popup",
    });
  }

  const html = buildPopupHTML(linkId, properties, mapInstance.getZoom());
  hoverPopup.value?.setLngLat(event.lngLat).setHTML(html).addTo(mapInstance);
  mapInstance.getCanvas().style.cursor = "pointer";
}

function hideHoverPopup() {
  const mapInstance = map.value;
  if (!mapInstance) return;
  mapInstance.getCanvas().style.cursor = "";
  if (hoverPopup.value) {
    hoverPopup.value.remove();
  }
}

function bindLayerHover(layerId: string) {
  const mapInstance = map.value;
  if (!mapInstance) return;
  mapInstance.on("mousemove", layerId, showHoverPopup);
  mapInstance.on("mouseleave", layerId, hideHoverPopup);
}

function updateLineColors(sourceData = speedData.value) {
  const mapInstance = map.value;
  if (!mapInstance || !mapInstance.isStyleLoaded()) return;
  if (!mapInstance.getLayer(MACRO_LAYER_ID)) return;
  if (!mapInstance.isSourceLoaded("highways")) return;

  const speedMap = sourceData || {};
  const macroColorExpression: unknown[] = ["match", ["get", "LinkID"]];
  for (const [linkId, data] of Object.entries(speedMap || {})) {
    macroColorExpression.push(linkId, speedToColor(readAvg(data as SpeedItem)));
  }
  macroColorExpression.push("#666666");

  if (mapInstance.getLayer(MACRO_LAYER_ID)) {
    mapInstance.setPaintProperty(MACRO_LAYER_ID, "line-color", macroColorExpression);
  }

  for (let laneIndex = 0; laneIndex < MAX_LANES; laneIndex++) {
    const microColorExpression: unknown[] = ["match", ["get", "LinkID"]];
    for (const [linkId, data] of Object.entries(speedMap || {})) {
      const laneSpeed = readLaneSpeed(data as SpeedItem, laneIndex);
      microColorExpression.push(linkId, speedToColor(laneSpeed));
    }
    microColorExpression.push(TRANSPARENT);

    const layerId = laneLayerId(laneIndex);
    if (mapInstance.getLayer(layerId)) {
      mapInstance.setPaintProperty(layerId, "line-color", microColorExpression);
    }
  }
}

onMounted(() => {
  if (!mapContainer.value) return;

  const mapInstance = new maplibregl.Map({
    container: mapContainer.value,
    style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    center: [120.982, 23.9738],
    zoom: 8,
    minZoom: 6,
    maxZoom: 15,
  });
  map.value = mapInstance;

  mapInstance.on("load", () => {
    mapInstance.addSource("highways", {
      type: "geojson",
      data: "/highway_links.geojson",
    });

    // macro layer: shows average speed when zoomed out
    mapInstance.addLayer({
      id: MACRO_LAYER_ID,
      type: "line",
      source: "highways",
      maxzoom: 13,
      layout: {
        "line-join": "round",
        "line-cap": "round",
      },
      paint: {
        "line-width": 4,
        "line-color": "#666666",
      },
    });
    bindLayerHover(MACRO_LAYER_ID);

    // micro layers: shows lane-level speed when zoomed in
    const laneWidth = 3;
    for (let laneIndex = 0; laneIndex < MAX_LANES; laneIndex++) {
      const offset = (laneIndex - (MAX_LANES - 1) / 2) * laneWidth;

      mapInstance.addLayer({
        id: laneLayerId(laneIndex),
        type: "line",
        source: "highways",
        minzoom: 13,
        layout: {
          "line-join": "round",
          "line-cap": "round",
        },
        paint: {
          "line-width": laneWidth - 0.5,
          "line-offset": offset,
          "line-color": TRANSPARENT,
        },
      });
      bindLayerHover(laneLayerId(laneIndex));
    }

    updateLineColors();
  });

  // Avoid first-load race: if speed data arrives before GeoJSON source is ready,
  // re-apply colors once the highways source finishes loading.
  mapInstance.on("sourcedata", (event: any) => {
    if (event.sourceId !== "highways") return;
    if (!mapInstance.isSourceLoaded("highways")) return;
    updateLineColors();
  });

  refreshSpeedFetch();
  pollTimer = setInterval(() => {
    refreshSpeedFetch();
  }, POLL_INTERVAL_MS);
});

watch(speedFetchError, (newError) => {
  if (newError) {
    console.error("[vd-speed] fetch failed:", newError);
  }
});

watch(
  speedData,
  (newSpeeds) => {
    updateLineColors(newSpeeds);
  },
  { deep: true },
);

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }

  if (map.value) {
    hideHoverPopup();
    map.value.remove();
    map.value = null;
  }
});
</script>

<style scoped>
.map-wrapper {
  position: relative;
  width: 100vw;
  height: 100vh;
}
.map-container {
  width: 100%;
  height: 100%;
}
.dashboard-panel {
  position: absolute;
  top: 20px;
  left: 20px;
  width: 350px;
  background: rgba(0, 0, 0, 0.8);
  border-radius: 8px;
  z-index: 10;
}

.source-disclaimer {
  position: absolute;
  right: 16px;
  bottom: 16px;
  z-index: 10;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.4;
  color: #f5f5f5;
  background: rgba(0, 0, 0, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 6px;
  backdrop-filter: blur(2px);
}
</style>
