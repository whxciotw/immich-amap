# Third-party notices

本项目代码以 MIT 发布。运行时依赖/引用以下第三方资源，请遵守各自许可：

| 资源 | 用途 | 许可 / 说明 |
| --- | --- | --- |
| [Immich](https://github.com/immich-app/immich) | 宿主应用；本工具只生成样式和替换地名数据 | AGPL-3.0。手机端修复位于配套仓库 [immich-app](https://github.com/whxciotw/immich-app)，遵循 AGPL-3.0 |
| [GeoNames](https://www.geonames.org/) | 逆地理编码数据（`cities500` / `admin1` / `countryInfo` 等） | CC BY 4.0。本项目**不重分发**数据，只读取 Immich 镜像内的 `geodata` |
| [Natural Earth](https://www.naturalearthdata.com/) | 国家边界与中文国家名 | Public domain |
| OpenCC（繁简映射） | `geodata_tables.py` 中内嵌的 251 字繁转简表 | Apache-2.0 |
| [NEGIAO/tile-proxy](https://github.com/NEGIAO/tile-proxy) | GCJ-02 逐瓦片重采样服务（Docker 镜像） | GPL-2.0-or-later；本项目只引用镜像，不修改/分发其源码 |
| [高德地图](https://lbs.amap.com/) 瓦片 | 地图底图 | 非官方直连地址，仅个人自用；商用请走高德开放平台正规授权。样式已带 `© 高德地图` 署名 |

如果分发本项目的容器/镜像组合，请自行核对上述许可证义务。
