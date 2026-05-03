# Freeway Speed

以 Nuxt 4 + MapLibre GL 建立的國道即時車速視覺化介面。

## 專案功能

- 讀取國道路段 GeoJSON（`public/highway_links.geojson`）並繪製地圖線段
- 呼叫本地 API（`/api/vd-speed`）取得即時車速資料
- 依縮放層級切換顯示方式
  - 縮小時顯示路段平均車速（macro layer）
  - 放大時顯示車道車速（micro lane layers）
- 每 60 秒自動輪詢更新一次車速

## 技術棧

- Nuxt 4
- Vue 3
- MapLibre GL
- fast-xml-parser

## 快速開始

### 安裝相依套件

```bash
npm install
```

### 啟動開發伺服器

```bash
npm run dev
```

預設開啟於：<http://localhost:3000>

## 可用指令

```bash
# 開發模式
npm run dev

# 建置
npm run build

# 預覽 production build
npm run preview

# 產生靜態檔案
npm run generate
```

## API 說明

### GET /api/vd-speed

伺服器端會抓取交通部高速公路局 VD XML：

- 來源：<https://tisvcloud.freeway.gov.tw/history/motc20/VDLive.xml>

並轉換成前端可直接使用的 JSON，格式如下：

```json
{
 "10010": {
  "avg": 78,
  "lanes": {
   "1": 76,
   "2": 81
  }
 }
}
```

- key：`LinkID`
- `avg`：該路段有效車道的平均速度（km/h，四捨五入）
- `lanes`：各車道速度（僅保留大於 0 的值）

## 地圖顏色規則

- \>= 80：綠色
- \>= 60：黃色
- \>= 40：橘色
- \>= 20：紅色
- < 20：紫色
- 無資料：透明（或預設灰色）

## 專案結構

```text
app/
 pages/
  index.vue          # 地圖主頁與即時渲染邏輯
server/
 api/
  vd-speed.ts        # 取得並解析 VD XML，回傳車速 JSON
public/
 highway_links.geojson
 highway_sections.geojson
```

