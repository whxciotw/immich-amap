# 手机端

手机端（Immich App，`maplibre_gl`）和桌面浏览器（MapLibre GL JS）行为不同，
本页记录两个已知差异与对应的处理方式。

## 1. 黑屏根因：原生 SDK 不认 `data:` URL

Immich 移动端把配置里的样式字符串直接交给
`MapLibreMap(styleString: style)`（`mobile/lib/presentation/widgets/map/map.widget.dart`）。
`maplibre_gl` 原生层对 `styleString` 的判定顺序是：

1. `{` / `[` 开头 → 当内联 JSON；
2. `/` 开头 → 当绝对文件路径；
3. `http(s)://` / `mapbox://` 开头 → 当 URL；
4. **其余一律当 Flutter asset 路径**。

于是 `data:application/json;base64,...` 被当成 asset 路径 → 加载失败 → **地图区黑屏**。
桌面端是浏览器 `fetch()`，所以 `data:` 反而能用 —— 这就是「电脑正常、手机黑屏」的原因。

### 解决：用 http 托管样式

新增一个静态服务（nginx）提供 `style-*.json`，把 http 地址粘进 Immich：

```
http://<HOST>:9003/style-light.json
http://<HOST>:9003/style-dark.json
http://<HOST>:9003/style-sat.json
```

部署方式见 [deployment.md](deployment.md) §3。注意样式目录要可被 nginx worker 读取（只读挂载即可）。

## 2. 初始视野：桌面端与手机端不是一回事

| 端 | 行为 | 依据 |
| --- | --- | --- |
| 桌面 | 相机没动过时，用样式里的 `center` / `zoom` | `maplibre-gl/src/ui/map.ts` 的 `style.load` 处理 |
| 手机·地点页顶部地图卡 | 无定位权限时默认 **夏威夷** `LatLng(21.44950, -157.91959)`、`zoom: 8` | `place.page.dart` |
| 手机·地图页 | 兜底 `CameraPosition(target: LatLng(0, 0), zoom: 0)` | `map.widget.dart` |

这两处是**显式传入 `CameraPosition`**，原生 SDK 不会采用样式里的 `center/zoom`。
所以**服务端无法改变手机端初始相机**，给 App 定位权限也没用（那两处不读设备位置）。

### 如果一定要改（需要 fork 手机端重编 APK）

改动点只有一处：`mobile/lib/presentation/pages/library.page.dart:229`。

```dart
// 现状：写死 null，导致 PlacePage / MapPage 都拿不到位置
onTap: () => context.pushRoute(PlaceRoute(currentLocation: null)),

// 方案 A：固定坐标（改动最小）
onTap: () => context.pushRoute(PlaceRoute(currentLocation: const LatLng(31.23040, 121.4737))),

// 方案 B：动态 GPS（先要权限，失败回退固定坐标）
onTap: () async {
  final (loc, _) = await MapUtils.checkPermAndGetLocation(context: context);
  context.pushRoute(PlaceRoute(currentLocation: loc == null
      ? const LatLng(31.23040, 121.4737)
      : LatLng(loc.latitude, loc.longitude)));
},
```

构建方式（约 30~40 分钟，需要带 Flutter + Android SDK 的环境）：

```bash
git clone --depth 1 --branch v3.3.6 https://github.com/immich-app/immich /tmp/immich-mobile
# 应用上面的改动后
docker run --rm -v /tmp/immich-mobile/mobile:/app -w /app \
  ghcr.io/cirruslabs/flutter:stable \
  sh -c "flutter pub get && flutter build apk --release"
# 产物：/tmp/immich-mobile/mobile/build/app/outputs/flutter-apk/app-release.apk
```

代价：签名与商店版不同 → 需先卸载官方 App 再侧载；之后**不会自动更新**，每次升级都要重编。

## 3. 地图页 hash 同步（调试初始视野时会踩）

Immich 地图页启用了 MapLibre 的 hash 同步。地址栏里残留的 `#15/31.17/121.61`
之类的片段会**覆盖**样式里的 `center/zoom`。调试初始视野前，先访问一次干净的
`http://<HOST>:2283/map`（删掉 `#` 之后的内容）。

## 4. 上游状态与本仓库的 App fork

「Places 地图初始位置写死夏威夷 / (0,0)」已提交给 Immich 上游：

- Issue <https://github.com/immich-app/immich/issues/32969>：被 maintainer 以
  duplicate 关闭（上游把它当作 feature 讨论）；
- PR <https://github.com/immich-app/immich/pull/32970>：被 bot 以"LLM 生成"政策关闭，未进入 review。

因此这个修复没有进入官方 App。需要在手机端使用的读者可以直接使用配套的
非官方构建 [whxciotw/immich-app](https://github.com/whxciotw/immich-app)：
它在官方 App 基础上修复了地图初始位置，并新增地点页国家/省/市三级折叠、
App 内更新等功能，安装包从该仓库的 Releases 下载。
