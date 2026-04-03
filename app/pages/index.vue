<template>
  <div class="map-wrapper">
    <div ref="mapContainer" class="map-container"></div>

    <div class="dashboard-panel"></div>
    <div class="source-disclaimer">資料來源：交通部高速公路局「交通資料庫」</div>
  </div>
</template>

<script setup>
import { ref, shallowRef, onMounted, onUnmounted, watch } from "vue";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

const mapContainer = shallowRef(null);
const map = shallowRef(null);

const MAX_LANES = 4;
const MACRO_LAYER_ID = "highway-macro";
const MICRO_LAYER_PREFIX = "highway-micro-lane-";
const TRANSPARENT = "rgba(0,0,0,0)";
const SPEED_API_URL = "/api/vd-speed";
const POLL_INTERVAL_MS = 60_000;

const realtimeSpeeds = ref({});
let pollTimer = null;
const hoverPopup = shallowRef(null);

const {
  data: speedData,
  execute: executeSpeedFetch,
  error: speedFetchError,
} = await useLazyFetch(SPEED_API_URL, {
  server: false,
  immediate: false,
  default: () => ({}),
});

function speedToColor(speed) {
  if (typeof speed !== "number") return TRANSPARENT;
  if (speed >= 80) return "#00ff00";
  if (speed >= 60) return "#ffff00";
  if (speed >= 40) return "#ffa500";
  return "#ff0000";
}

function laneLayerId(laneIndex) {
  return `${MICRO_LAYER_PREFIX}${laneIndex}`;
}

function getSegmentName(properties, linkId) {
  return properties?.SectionName || properties?.RoadSectionName || properties?.RoadName || `Link ${linkId}`;
}

function formatSpeed(speed) {
  return typeof speed === "number" ? `${speed} km/h` : "--";
}

function buildPopupHTML(linkId, properties, zoomLevel) {
  const speedData = realtimeSpeeds.value?.[linkId];
  const segmentName = getSegmentName(properties, linkId);
  const avgSpeed = formatSpeed(speedData?.avg);

  let lanesHtml = "";
  if (zoomLevel >= 13 && speedData?.lanes && Object.keys(speedData.lanes).length > 0) {
    const laneEntries = Object.entries(speedData.lanes)
      .map(([lane, speed]) => [Number(lane), speed])
      .sort((a, b) => a[0] - b[0]);

    const laneRows = laneEntries.map(([lane, speed]) => `<li>車道 ${lane}: ${formatSpeed(speed)}</li>`).join("");

    lanesHtml = `<hr style=\"border:0;border-top:1px solid rgba(255,255,255,.2);margin:8px 0;\"><ul style=\"margin:0;padding-left:16px;\">${laneRows}</ul>`;
  }

  return `<div style=\"font-size:12px;line-height:1.5;\"><div style=\"font-weight:700;margin-bottom:4px;\">${segmentName}</div><div>LinkID: ${linkId}</div><div>平均時速: ${avgSpeed}</div>${lanesHtml}</div>`;
}

function showHoverPopup(event) {
  if (!map.value || !event.features?.length) return;

  const feature = event.features[0];
  const linkId = feature?.properties?.LinkID;
  if (!linkId) return;

  if (!hoverPopup.value) {
    hoverPopup.value = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 12,
      className: "speed-popup",
    });
  }

  const html = buildPopupHTML(linkId, feature.properties, map.value.getZoom());
  hoverPopup.value.setLngLat(event.lngLat).setHTML(html).addTo(map.value);
  map.value.getCanvas().style.cursor = "pointer";
}

function hideHoverPopup() {
  if (!map.value) return;
  map.value.getCanvas().style.cursor = "";
  if (hoverPopup.value) {
    hoverPopup.value.remove();
  }
}

function bindLayerHover(layerId) {
  if (!map.value) return;
  map.value.on("mousemove", layerId, showHoverPopup);
  map.value.on("mouseleave", layerId, hideHoverPopup);
}

function updateLineColors(speedMap) {
  if (!map.value || !map.value.isStyleLoaded()) return;
  if (!map.value.getLayer(MACRO_LAYER_ID)) return;
  if (!map.value.isSourceLoaded("highways")) return;

  const macroColorExpression = ["match", ["get", "LinkID"]];
  for (const [linkId, data] of Object.entries(speedMap || {})) {
    macroColorExpression.push(linkId, speedToColor(data?.avg));
  }
  macroColorExpression.push("#666666");

  if (map.value.getLayer(MACRO_LAYER_ID)) {
    map.value.setPaintProperty(MACRO_LAYER_ID, "line-color", macroColorExpression);
  }

  for (let laneIndex = 0; laneIndex < MAX_LANES; laneIndex++) {
    const microColorExpression = ["match", ["get", "LinkID"]];
    for (const [linkId, data] of Object.entries(speedMap || {})) {
      const laneSpeed =
        data?.lanes?.[laneIndex] ??
        data?.lanes?.[String(laneIndex)] ??
        data?.lanes?.[laneIndex + 1] ??
        data?.lanes?.[String(laneIndex + 1)];
      microColorExpression.push(linkId, speedToColor(laneSpeed));
    }
    microColorExpression.push(TRANSPARENT);

    const layerId = laneLayerId(laneIndex);
    if (map.value.getLayer(layerId)) {
      map.value.setPaintProperty(layerId, "line-color", microColorExpression);
    }
  }
}

onMounted(() => {
  map.value = new maplibregl.Map({
    container: mapContainer.value,
    style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    center: [120.982, 23.9738],
    zoom: 7,
  });

  map.value.on("load", () => {
    map.value.addSource("highways", {
      type: "geojson",
      data: "/highway_links.geojson",
    });

    // macro layer: shows average speed when zoomed out
    map.value.addLayer({
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

      map.value.addLayer({
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

    updateLineColors(realtimeSpeeds.value);
  });

  // Avoid first-load race: if speed data arrives before GeoJSON source is ready,
  // re-apply colors once the highways source finishes loading.
  map.value.on("sourcedata", (event) => {
    if (event.sourceId !== "highways") return;
    if (!map.value || !map.value.isSourceLoaded("highways")) return;
    updateLineColors(realtimeSpeeds.value);
  });

  executeSpeedFetch();
  pollTimer = setInterval(() => {
    executeSpeedFetch();
  }, POLL_INTERVAL_MS);
});

watch(speedData, (newData) => {
  realtimeSpeeds.value = newData || {};
});

watch(speedFetchError, (newError) => {
  if (newError) {
    console.error("[vd-speed] fetch failed:", newError);
  }
});

watch(
  realtimeSpeeds,
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
