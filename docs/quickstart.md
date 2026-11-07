# 快速部署（电脑 + 手机）

按 [README](../README.md) 的完整路径部署：纠偏服务 + 样式托管 + 中文地名库。
约定：`<HOST>` 是部署机局域网 IP 或域名。

## 1. 准备

```bash
git clone <仓库地址> immich-amap && cd immich-amap
cp .env.example .env
$EDITOR .env            # 至少把 HOST 改成自己的地址
```

需要：Python 3.9+、Docker / Docker Compose、Immich v3.x；
`9002`/`9003` 端口对局域网开放，主机能出网访问 `*.is.autonavi.com`。

## 2. 生成样式

```bash
set -a; . ./.env; set +a
python3 -m immich_amap static \
  --tile-base "http://$HOST:${TILE_PROXY_PORT:-9002}" \
  --public-base "http://$HOST:${MAPSTYLE_PORT:-9003}" \
  --center <经度>,<纬度> --zoom 15 --out dist/mapstyles
```

## 3. 启动服务

```bash
docker compose up -d
docker compose ps
curl -s http://$HOST:9002/health
curl -sI http://$HOST:9003/style-light.json | head -1
```

## 4. 填入 Immich

**管理 → 系统设置 → 地图与 GPS 设置 → 地图**：

```
亮色：http://<HOST>:9003/style-light.json
暗色：http://<HOST>:9003/style-dark.json
```

保存刷新；桌面和手机都应正常显示高德底图。

## 5. 中文地名库

步骤（取镜像原始 geodata → 生成 → 挂载 → 重跑元数据）见
[geodata-cn.md](geodata-cn.md) §6，或直接照 [README](../README.md) 步骤 5 做。

## 6. 验收与排障

见 [operations.md](operations.md) §5–§6 和 [faq.md](faq.md)。
