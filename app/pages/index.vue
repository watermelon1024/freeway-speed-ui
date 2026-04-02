<template>
  <div class="map-wrapper">
    <div ref="mapContainer" class="map-container"></div>

    <div class="dashboard-panel"></div>
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

function updateLineColors(speedMap) {
  if (!map.value || !map.value.isStyleLoaded()) return;

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
    }

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
</style>
