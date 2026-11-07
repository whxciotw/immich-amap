# 部署素材

这里放「部署到任意 Docker 主机」用的文件，不含生成物（`dist/` 由 `make` 生成）。

| 文件 | 用途 |
| --- | --- |
| `../compose.yaml` | `tile-proxy` + `mapstyle` 两个服务的完整 compose 示例（仓库根目录，可直接 up） |
| `../.env.example` | compose 变量示例，复制为 `.env` 使用 |
| `nginx/style-server.conf` | 样式静态托管的 nginx 配置（CORS + no-cache） |

## 快速使用

```bash
cp .env.example .env
# 编辑 .env：至少把 HOST 改成宿主机的局域网 IP / 域名
python3 -m immich_amap static \
  --tile-base http://$HOST:9002 --public-base http://$HOST:9003 \
  --center <经度>,<纬度> --zoom 15 --out dist/mapstyles
docker compose up -d
```

然后按 [../docs/deployment.md](../docs/deployment.md) 把
`http://$HOST:9003/style-light.json` / `style-dark.json` 填进 Immich。

> `compose.yaml` 只包含地图相关的两个服务。中文地名库是可选的，
> 通过给 `immich-server` 追加一个只读 volume 实现，见 compose 文件末尾注释。
