# 运维手册

适用于用 [deployment.md](deployment.md) 部署的任意 Docker 主机。
约定：`<HOST>`、`<DATA_DIR>`、`<STYLE_DIR>` 与 `.env` 一致。

## 1. 日常命令

```bash
# 容器状态 / 日志（独立 compose 方式）
docker compose ps
docker compose logs -f tile-proxy
docker compose logs -f mapstyle

# 健康与样式
curl -s http://<HOST>:9002/health
curl -sI http://<HOST>:9003/style-light.json | head -1

# 瓦片缓存占用（具名卷）
docker run --rm -v immich-amap_tile-proxy-cache:/cache alpine du -sh /cache
```

> 若把两个 service 合并进了 Immich 的 compose，把上面的 `--env-file/-f` 换成
> Immich 的 compose 路径即可；服务名仍是 `tile-proxy` / `mapstyle`。

## 2. 改样式（初始视野、滤镜）

```bash
set -a; . ./.env; set +a
python3 -m immich_amap static --tile-base "http://$HOST:9002" \
  --public-base "http://$HOST:9003" --center <经度>,<纬度> --zoom 15 \
  --out dist/mapstyles
# mapstyle 挂载的是这个目录，文件更新即生效（nginx 已设 no-cache）
```

远程部署时可用 `make deploy-static HOST=user@host REMOTE_STYLE_DIR=/srv/immich-amap/mapstyles`，
或者直接把 JSON 拷到 `STYLE_DIR`。

## 3. 升级与回滚

```bash
# tile-proxy（版本钉死，watchtower 不会自动升级）
docker compose pull tile-proxy
docker compose up -d tile-proxy

# mapstyle（nginx:alpine 可跟随升级，也可以固定 tag）
docker compose pull mapstyle
docker compose up -d mapstyle
```

- 样式本身无状态：改回旧参数重新生成即可。
- 地名库回滚：换回旧 geodata 目录（或去掉 volume）→ 重启 `immich_server` → 重跑元数据提取。

## 4. 备份

| 对象 | 位置 | 建议 |
| --- | --- | --- |
| compose 文件 + `.env` | 仓库 / 部署目录 | 纳入版本管理或定期备份 |
| `DATA_DIR` | `./data`（或自定义） | 备份 `tile-proxy-admin` |
| 样式生成物 | `STYLE_DIR` | 可重新生成，不必备份 |
| geodata 目录（可选） | 自定义 | 可重新生成（约 10 秒），备份只是为了省事 |

## 5. 验收清单

| # | 检查 | 期望 |
| --- | --- | --- |
| 1 | `curl -s http://<HOST>:9002/health` | `{"ok":true,...}` |
| 2 | `docker compose ps` | 两个服务 `Up` |
| 3 | `curl -sI http://<HOST>:9003/style-light.json` | `200` |
| 4 | CORS 头 | `Access-Control-Allow-Origin: *` |
| 5 | `python3 -m immich_amap selftest --limit 1` | 通过 |
| 6 | 抽查瓦片 | 纠偏版仍是 `256x256` |
| 7 | Immich 地图页 / 手机 App | 正常显示、不黑屏 |
| 8 | 地名库（若部署） | 日志 `Successfully imported ...`，资产城市为中文 |

## 6. 排障

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| 桌面正常、手机黑屏 | 手机端不认 `data:` URL | 改用 http 托管样式（[mobile.md](mobile.md)） |
| 样式 404 | `STYLE_DIR` 挂载错 / 文件不在 | 检查 `docker compose config` 与目录权限（nginx 需可读） |
| 底图整体偏移几百米 | 用了不纠偏样式，或照片 EXIF 本身是 GCJ-02 | 按 [quickstart.md](quickstart.md) 第 0 步自测后选样式 |
| 改 `center` 不生效 | 地址栏 hash 覆盖 | 访问干净的 `/map` |
| https 下底图空白 / 混合内容 | 瓦片/样式服务是 http | 挂同一反代路径，用 https 基址重新生成（[deployment.md](deployment.md) §7） |
| 瓦片慢（冷/热） | 现场重采样 / 缓存未命中 | 冷请求 35~100ms、热 1~3ms 属正常；确认 `DATA_DIR`/缓存卷可写 |
| 瓦片 403/超时 | 容器不能出网，或上游限流 | 检查容器网络与 `PROXY_RATE_LIMIT` |
| 地名还是旧值 | 没重跑元数据提取 | 见 [geodata-cn.md](geodata-cn.md) |
| 放大到 z19 模糊 | 高德瓦片只到 z18 | 正常 |
| `docker compose` 报错 | `.env` 变量缺失/路径不存在 | `docker compose --env-file ... config -q` 定位 |
