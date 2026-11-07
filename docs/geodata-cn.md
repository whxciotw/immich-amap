# 中文 + 可控粒度地名库（可选）

Immich 的地点名默认是英文，而且经常显示成「村镇」级别。本页说明根因、
`immich_amap geodata` 做了什么、参数怎么选、以及部署与效果。

> 这是可选功能：不部署地名库不影响高德底图；部署后 Immich 的地点显示/搜索走中文。

## 能力一览（默认全关）

| 能力 | 参数 | 说明 |
| --- | --- | --- |
| 中文化 + 城市级归一化 | （默认） | 名字优先级取中文，非城市行归一到最近城市 |
| 增强点集 | `--enhance FILE` / `--full` | 并入 GeoNames 国家 dump，补 25km 空白 |
| 全量中文别名 | `--alternate-names FILE` | 用 `alternateNamesV2.txt` 补中文名 |
| 高德精修 | `amap-cache` 子命令 + `--amap-cache CSV` | 按坐标反查官方行政区名，缓存后离线用 |
| 粒度/显示 | `--level` / `--prefix` / `--separator` | city/county/town、是否加前缀 |

## 1. 根因

Immich v3 逆地理编码**不用 Nominatim**，而是镜像内 `/build/geodata` 的 GeoNames 数据。

| 现象 | 根因 |
| --- | --- |
| 地点名英文 | 城市名取 `cities500.txt` 第 2 列 `name`（英文/罗马化），第 4 列中文别名**不参与显示** |
| 显示村镇 | SQL 只按「25km 内最近距离」取一条，**不看行政级别** |
| 没有语言开关 | `reverseGeocoding` 配置只有 `enabled` |

所以只能改数据层：重写 geodata 文件并挂载覆盖 `/build/geodata`（新照片也生效）。

## 2. 用法

```bash
# 最小用法：中文化 + 城市级
python3 -m immich_amap geodata --src <原始 geodata> --dst <输出目录>

# 常用组合
python3 -m immich_amap geodata --src <src> --dst <dst> \
    --amap-cache amap.csv --prefix none
python3 -m immich_amap geodata --src <src> --dst <dst> \
    --level county --prefix none
```

`--src` 必须是 **Immich 镜像原始层**的 geodata（挂过 volume 后容器内目录已被覆盖），
取法见 [deployment.md](deployment.md) §6。

处理流程：

1. **中文化**：`cities500` 名字按 `NAME_OVERRIDE` > 高德缓存 > 第 4 列中文别名 > 原名
   （全程繁转简）；`admin1CodesASCII` 中国省级、`countryInfo` 国家名换成中文；
2. **增强点集**（可选）：并入国家 dump 中 feature class=`P` 的点（默认人口 ≥100，`--full` 不过滤）；
3. **粒度归一化**：非目标级别行改写成 150km 内最近锚点的名字（同省 → 同国 → 任意）；
4. **显示名**：`--prefix province`（默认，写「省 · 市」）或 `none`（只写地名）；
5. 写新的 `geodata-date.txt`，触发 Immich 重新导入。

## 3. 规则

### 城市判定（`is_city`）

| 国家/地区 | 规则 |
| --- | --- |
| 中国 | fcode ∈ `{PPLC, PPLA, PPLA2}`，或「名字以市结尾且人口 ≥30 万」 |
| 其他 | fcode ∈ `{PPLC, PPLA, PPLA2}` 或人口 ≥10 万 |
| 公共 | 纯中文名；排除 `区/县/镇/乡/村/街道/旗/屯` 后缀 |

> GeoNames 的 fcode 对部分中国城市不可靠（临汾是 `PPL`），所以用「白名单 + 人口/后缀」组合判断。

### 显示格式（`--prefix`）

| 场景 | `province`（默认） | `none` |
| --- | --- | --- |
| 普通省份 | `山西 · 临汾市` | `临汾市` |
| 直辖市 | `上海市` | `上海市` |
| 境外 | `泰国 · 曼谷` | `曼谷` |
| 港澳台 | `澳门 · 路氹城` | `路氹城` |

「省 · 市」是写进 `city` 字段的复合串；若调用方需要纯市名，用 `--prefix none`。

### 名字细节

- 繁转简内置 251 字表；可选 `zhconv`/`opencc` 只影响 `--alternate-names` 索引，不改变默认档；
- 个别行用 `NAME_OVERRIDE` 按 geonameid 锁定（如 `路氹城`、`金城镇`、`林芝市`、`氹仔`）；
- 港澳台按「中国省级行政区」处理（`SPECIAL_ADMIN1` / `COUNTRY_OVERRIDE` 可改）。

## 4. 粒度与显示

Immich 只有 `country / state / city` 三个字段，没有运行时切换；粒度是**生成时**的选择，
换档 = 换库 + 重启 + 重跑元数据（全库统一，不能并存）。

| `--level` | 写进 city 的内容 | 示例 |
| --- | --- | --- |
| `city`（默认） | 地级市/直辖市 | `苏州市` |
| `county` | 区/县（`PPLA3`、区/县/旗、高德 admin3） | `昆山市` |
| `town` | 每个有中文名的点保持原样，无中文名的归一到最近城市 | `周市镇` |
| `--no-city-level` | 只中文化、不归一化（旧行为） | 村镇行走原名 |

预览（不碰 Immich，复刻 25km 最近点规则）：

```bash
python3 -m immich_amap geodata-sim --src <geodata 目录> --coords assets.csv
python3 -m immich_amap geodata-sim --src <A> --coords assets.csv --compare <B>
```

> `county` 档没有高德缓存时可能命中 GeoNames 的历史区名（如上海「卢湾」）；
> 要准就先跑 `amap-cache`。`town` 档会重新出现村镇名，适合特定需求。

## 5. 可选增强

### 5.1 增强点集（`--enhance`）

```bash
# 从 download.geonames.org/export/dump/ 下载 CN.zip 等，解压出 CN.txt
python3 -m immich_amap geodata --src <src> --dst <dst> \
    --enhance CN.txt --enhance HK.txt --enhance MO.txt --enhance TW.txt
```

- 默认人口 ≥100（`--enhance-min-pop`），`--full` 不做人口过滤；
- 按 geonameid 与 (lat, lon) 双去重；
- 参考：CN dump 的人口字段大量为空，默认阈值只 +67 行；`--full` 会到 112 万行
  （165MB、约 36s、峰值 ~2.1GB），Immich 首次导入明显变慢，按需使用。

### 5.2 全量中文别名（`--alternate-names`）

```bash
python3 -m immich_amap geodata --src <src> --dst <dst> \
    --alternate-names alternateNamesV2.txt
```

- 下载 `alternateNamesV2.zip`（约 200MB，解压约 1.6GB）；
- 只取 zh 系列语言，preferred 优先，过滤历史名/俗称/短名/非纯中文；
- 只补「原名没有中文」的行，不覆盖高德/人工覆盖；
- 索引只保留库中出现过的 geonameid，内存与 `cities500` 同量级。

### 5.3 高德精修（`amap-cache` + `--amap-cache`）

```bash
export AMAP_API_KEY=你的key        # 必须是「Web服务」平台的 key
python3 -m immich_amap amap-cache --src <src> --out amap.csv \
    --coords assets.csv --qps 3
python3 -m immich_amap geodata --src <src> --dst <dst> --amap-cache amap.csv
```

- `assets.csv`：带表头 `latitude,longitude`，或无表头两列 `lat,lon`；
- 只反查坐标 25km 内的 geodata 行，增量缓存；只有省名/占位值/失败的结果不落缓存；
- 内置 WGS-84 → GCJ-02 转换；批量响应按「与请求同序」假设，可用 `--batch-size 1` 抽查；
- city 档取值：普通省 admin2、直辖市 admin1、自治州/地区/盟 admin3、港澳不覆盖；
- 缓存与 `--level` 无关，一次反查四级都能用；结果仅自用，不重分发。

## 6. 部署与维护

步骤见 [deployment.md](deployment.md) §6，摘要：

```bash
# 1) 取镜像原始 geodata
docker create --name immich-geodata-src ghcr.io/immich-app/immich-server:v3
docker cp immich-geodata-src:/build/geodata /tmp/geodata-orig
docker rm immich-geodata-src

# 2) 生成
python3 -m immich_amap geodata --src /tmp/geodata-orig --dst /tmp/geodata-cn

# 3) 挂载：immich-server 追加
#    /path/to/geodata-cn:/build/geodata:ro

# 4) 重启 immich-server，日志应出现
#    Successfully imported ... geodata records
#    Initialized local reverse geocoder

# 5) 重跑「管理 → 任务 → 提取元数据 → 全部运行」
```

要点：

- `geodata-date.txt` 不变时 Immich 会跳过导入；更新后必须重跑元数据才会刷新已有资产；
- Immich 升级若更换了自带 geodata，需要重新取数、生成、覆盖；
- 自检：

  ```bash
  docker exec immich_server head -1 /build/geodata/cities500.txt   # 第 2 列应为中文
  docker logs immich_server | grep -i geodata
  docker exec immich_postgres psql -U <user> -d <db> -c \
    "select city, state, count(*) from asset_exif where city <> '' group by 1,2 order by 3 desc limit 15;"
  ```

## 7. 局限与许可

- 全球约 20% 地名有中文别名（中国城市约 94%）；境外小地方仍可能英文，
  可用 `--alternate-names` 提升；
- 中文名来自 GeoNames 别名启发式，个别不符合习惯写法，用 `NAME_OVERRIDE` 覆盖；
- `--level county/town` 的效果取决于数据（高德缓存/增强点足够才准）；
- 数据来源：GeoNames（CC BY 4.0）、Natural Earth（公有领域，国家中文名）、
  Immich 镜像自带数据；高德结果仅衍生自用，遵守其条款；
- 繁简转换：内置 251 字表，或可选 `zhconv`/`OpenCC`（`pip install -e ".[zh]"`）。
