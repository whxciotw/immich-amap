# 原理与设计

本文说明三件事：为什么只换底图会偏、纠偏代理怎么工作、以及几个「为什么只能这么做」的
Immich 侧约束。文中 Immich 源码路径以 v3.3.x 为准。

## 1. Immich 侧的事实

| 事实 | 依据（Immich 源码） |
| --- | --- |
| 服务端地图设置只有两个字段：`lightStyle` / `darkStyle`，都只校验「是不是合法 URL」 | `server/src/dtos/config.dto.ts` → `z.url()` |
| 前端把这个 URL 原样交给 MapLibre 当 style，**由浏览器自己 fetch** | `web/src/lib/components/shared-components/map/Map.svelte`（`MapLibre` 组件的 style URL） |
| 照片坐标直接当标记坐标用，**没有任何坐标系转换** | 同上：`coordinates: [marker.lon, marker.lat]` |
| 高德栅格瓦片是 **GCJ-02（火星坐标）** | 国测局加密偏移，城区可达数百米 |
| 照片 EXIF 的 GPS 通常是 **WGS-84** | iPhone / 绝大多数相机如此 |

结论：**只把底图换成高德 = 整城偏移**。偏移方向随地区变化（北京约 580m 东、170m 北），
放大到 z17 时偏移量超过 2 个瓦片。这不是配置项能解决的，也没有任何 URL 参数能纠偏。

## 2. 纠偏的两条路

| 方案 | 做法 | 代价 |
| --- | --- | --- |
| 换 WGS-84 底图 | 用天地图等本身就是 WGS-84 的底图 | 零改造，但不是高德 |
| 逐瓦片重采样代理 | 中间加一层代理，把 WGS-84 网格换算成 GCJ-02 再取图重采样 | 要部署一个服务；首次请求慢 |

本项目采用第二种，代理用 [NEGIAO/tile-proxy](https://github.com/NEGIAO/tile-proxy)
（同一思路的成熟实现，Home Assistant 社区的
[938134/ha_cnmaps](https://github.com/938134/ha_cnmaps) 是早期实现）。

```
浏览器按 WGS-84 网格请求 /proxy/gcj2wgs/<上游高德URL>
        │
        ▼
tile-proxy：把该 WGS-84 瓦片换算成 GCJ-02
        │  算出需要哪 1~4 张上游高德瓦片
        ▼
抓高德瓦片 → 重采样 / 拼合 → 输出与 WGS-84 对齐的 256×256 图
        │
        ▼
浏览器看到的就是「坐标对得上」的高德底图
```

### 纠偏精度（实测）

拿天安门附近一张纠偏瓦片和原始高德瓦片做互相关：

| 指标 | 值 |
| --- | --- |
| 实际内容位移 | `(582, −170) px` |
| 理论 GCJ-02 偏移 | `(581.7, −170.25) px` |
| 残差 | 0.3 px |
| NCC（归一化互相关） | 0.995 |

亚像素吻合，说明代理的换算与重采样是正确的。

## 3. `data:` URL 为什么能塞进 Immich

Immich 只要一个 URL，浏览器去 fetch 它。而 `data:application/json;base64,...`
本身就是合法 URL：

1. 服务端 `z.url()` 用 `new URL()` 解析，接受任意 scheme（按 Immich 同款 `zod@4.4.3` 实测通过）；
2. MapLibre 的 `makeRequest()` 对不含 `://` 的地址直接走 `fetch()`，`data:` 正好命中这条分支。

于是可以把整个 `style.json` 编码进一条 URL 直接粘贴，省掉找地方托管 JSON。

> 这条路径**只对桌面浏览器成立**，现在仅用于临时调试；正式部署（含手机）走 http 托管样式，
> 见 [deployment.md](deployment.md)。手机端不认 `data:`，原因见 [mobile.md](mobile.md)。

## 4. 样式结构

`immich_amap/styles.py` 生成三种变体，每种都有纠偏 / 不纠偏两版：

| 变体 | source | 图层 | 说明 |
| --- | --- | --- | --- |
| `light` | `amap`（webrd01~04 style=8） | `bg` + `amap` | 亮色路网 |
| `dark` | 同上 | `bg` + `amap`（带 `raster-*` 滤镜） | 高德没有暗色栅格瓦片，用亮度/饱和度/对比度压暗 |
| `sat` | `sat`（webst style=6）+ `lab`（webst style=8） | `bg` + `sat` + `lab` | 卫星影像叠加透明路网注记，天然偏暗 |

- `minzoom=3`、`maxzoom=18`：高德 z≥19 不再出图。
- 滤镜只加在底图图层上，不影响 Immich 叠加的照片标记。
- 极简版（`--compact`）额外去掉背景层、attribution，只留单个瓦片域名，`data:` URL 最短。

## 5. 初始视野（`center` / `zoom`）

桌面端：MapLibre 在 `style.load` 时，如果相机还没被移动过，会用样式里的 `center/zoom`
做初始视野（`maplibre-gl/src/ui/map.ts` 的 `style.load` 处理）。Immich 先 `style=""`
再 `setStyle(styleUrl)`，相机未动，所以样式里的值会生效。

注意两点：

- **Immich 地图页启用了 hash 同步**：地址栏残留 `#zoom/lat/lng` 会覆盖样式的 `center/zoom`，
  调试初始视野前先访问干净的 `/map`。
- **手机端不读**：App 显式传入 `CameraPosition`，原生 SDK 不会采用样式里的值，
  服务端无解，见 [mobile.md](mobile.md)。

因此 `center` / `zoom` 只在 `immich_amap static`（http 托管版）输出里写入，
`data:` URL 版不写（桌面端也生效，但为保持 URL 短，默认不带）。

## 6. 为什么中文地名只能改数据

Immich v3 的逆地理编码不用 Nominatim，而是镜像内的本地 GeoNames 数据集
（`/build/geodata`）：启动时 `metadata.service.ts` → `mapRepository.init()` 导入
`cities500.txt`、`admin1CodesASCII.txt`、`admin2Codes.txt`、`countryInfo.txt`。

- 城市名取 `cities500.txt` 第 2 列 `name`（英文/罗马化），第 4 列 `alternateNames`
  （含中文）虽然入库但**不参与显示**；
- SQL 只按「25km 内最近距离」取一条，**不看行政级别**，所以会显示村/镇/乡；
- 配置里 `reverseGeocoding` 只有 `enabled` 一个开关，**没有语言选项**。

所以「优先中文、没有则英文」以及「统一到城市粒度」都只能改数据层，
本项目的做法是重写地名库文件，见 [geodata-cn.md](geodata-cn.md)。
