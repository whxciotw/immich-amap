# 常见问题（FAQ）

## 坐标与纠偏

### 贴上去以后标记整体偏了几百米？

底图是高德（GCJ-02），照片 EXIF 是 WGS-84，Immich 不做坐标转换。
使用 http 托管的纠偏样式，并部署 `tile-proxy`。见 [deployment.md](deployment.md) 与 [quickstart.md](quickstart.md)。

### 我的照片不偏，还需要纠偏吗？

不需要。部分国产安卓机写入的 GPS 本身就是 GCJ-02，直接用不纠偏版（`amap-light`）即可。
判断方法见 [quickstart.md](quickstart.md) 第 0 步。

### 不纠偏版能直接用吗？

能，而且不需要部署任何东西 —— 复制 `data:` URL 粘贴即可（桌面端）。
只是照片标记会整体偏移。

### 为什么不能只给一条 URL 让它「自动纠偏」？

纠偏必须在瓦片层面做（把 WGS-84 网格换算成 GCJ-02 再重采样），需要服务端代理。
Immich 只接受样式 URL，没有任何参数能做坐标变换。详见 [architecture.md](architecture.md)。

## `data:` URL（临时调试用）

> 正式部署请用 http 托管样式；下面仅用于桌面端临时验证。

### `data:` URL 为什么能粘进 Immich？

服务端只校验「是不是合法 URL」，`data:` 是合法 URL；浏览器 fetch 它也能正常解析。
详见 [architecture.md](architecture.md) §3。

### URL 太长，粘贴时要注意什么？

一条 1~2KB，是一整条 URL，**别漏字符**、别换行。Immich 后台是 schema 驱动的文本框，
没有长度限制。若开了 `IMMICH_HELMET` 的自定义 CSP，需要放行 `data:`。

### 电脑上正常，手机上黑屏？

`data:` URL 只有桌面浏览器能用，手机端 `maplibre_gl` 不认，必须用 http 托管。
见 [mobile.md](mobile.md)。

### 不想用 `data:`，想自己托管 JSON？

`web/maker.html` 每张卡片都有「下载 JSON」按钮；也可以直接用
`python3 -m immich_amap urls --out dist` 生成的 `dist/amap-*.json`，
丢到任意 Web 服务器/反代路径下，把它的 http(s) 地址填进 Immich 即可
（注意手机端本来就必须用 http 托管）。

### 想更短的 URL？

```bash
python3 -m immich_amap urls --compact --out dist
```

极简版只有 350~500 字符（单个瓦片域名、无背景层）。

## 部署与访问

### 样式服务 404 / 地图空白

先确认 `STYLE_DIR` 挂载路径与生成目录一致，且文件对 nginx worker 可读（`chmod -R a+r`）；
用 `docker compose exec mapstyle ls /usr/share/nginx/html` 对照检查。

### https 访问 Immich，底图加载不出来 / 控制台报混合内容

纠偏服务和样式服务是 http 的，被浏览器拦了。挂到同一个反代路径下，用 https 基址重新生成样式，
见 [deployment.md](deployment.md) §7。

### CORS 要额外配吗？

一般不用：`tile-proxy` 的瓦片响应自带 `Access-Control-Allow-Origin: *`，
nginx 配置里也加了。若反代抹掉了响应头，补上即可。

### 瓦片第一次很慢？

纠偏是现场重采样（每张输出瓦片可能拼 1~4 张上游图），冷请求约 35~100ms，
之后走容器磁盘缓存（`/data/cache`）1~3ms。卫星图纠偏后是 PNG，单张约 130KB。

### 纠偏服务需要什么网络条件？

容器要能出网访问 `*.is.autonavi.com`；端口要发布到局域网（瓦片是浏览器直接拉的）。

## 样式与显示

### 高德有暗色底图吗？

没有暗色栅格瓦片。`dark` 样式是把路网瓦片用 `raster-brightness-max` /
`raster-saturation` / `raster-contrast` 滤镜压暗，只作用于底图，不影响照片标记。
很多人更喜欢 `sat`（卫星图天然偏暗）。

### 放大到最大级别很模糊？

高德瓦片 `maxzoom=18`，再放大只是拉伸，正常现象。

### 改了 `center`/`zoom` 不生效？

地址栏的 MapLibre hash（`#15/31.17/121.61`）会覆盖样式值。先访问干净的 `/map`。

### 手机端为什么总是从夏威夷 / (0,0) 开始？

App 里硬编码了 `CameraPosition`，服务端改不了。见 [mobile.md](mobile.md)。

## 地名

### 地点名还是英文 / 显示成村镇？

这是 Immich 本地 GeoNames 地名库的问题，不是底图问题。部署「中文 + 城市级地名库」，
见 [geodata-cn.md](geodata-cn.md)。

### 换了高德底图，为什么地点名没变？

逆地理编码在服务端用本地 GeoNames 数据完成，与底图完全无关；换高德底图不会改变它。

### 改了地名库要重跑什么？

① 确认 `geodata-date.txt` 变了才会重新导入；② 必须重跑 `metadataExtraction` 任务，
已存在资产在数据库里的旧地名才会刷新。

## 兼容与合规

### 支持哪些 Immich 版本？

v3.x（v3.3.x 实测）。样式是标准 MapLibre style v8，Immich 只校验 URL，理论上版本兼容性很宽。

### 能用在高德官方 JS API 吗？

不能。官方 JS API 是矢量 + 自定义样式，MapLibre 用不了；本项目用的是社区常用的栅格瓦片地址
（`webrd0X/webst0X.is.autonavi.com`），**不是高德官方授权接口**。个人自用风险自负，
商用请走高德开放平台正规授权。

### `tile-proxy` 的许可证？

上游 [NEGIAO/tile-proxy](https://github.com/NEGIAO/tile-proxy) 是 GPL-2.0-or-later，
修改后分发需按 GPL 提供源码。
