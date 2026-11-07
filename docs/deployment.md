# 部署（Docker / Compose）

面向任意 Docker 主机（Linux、NAS、云主机均可）。示例统一用
`<HOST>`（局域网 IP 或域名）、`<DATA_DIR>`（持久化目录），
按自己的环境替换。

## 1. 组成

| 组件 | 作用 | 必需 |
| --- | --- | --- |
| `tile-proxy` | 把高德 GCJ-02 瓦片按 WGS-84 网格重采样 | 纠偏版必需 |
| `mapstyle`（nginx） | 提供 `style-*.json`（手机端必须走 http） | 手机端必需 |
| geodata volume | 覆盖 Immich 镜像内的 GeoNames 数据（中文地名） | 必装 |

```
浏览器 → Immich 页面 → 按 style URL 取样式 → 直接请求 tile-proxy/mapstyle
```

关键网络要求：

- `tile-proxy` 必须能出网访问 `*.is.autonavi.com`；
- `9002`（瓦片）和 `9003`（样式）必须发布到**局域网**——请求来自浏览器，不是 Immich 服务端；
- 若通过 https 访问 Immich，样式/瓦片也要走 https 反代（否则混合内容会被拦）。

## 2. 准备目录与配置

```bash
git clone <仓库地址> immich-amap && cd immich-amap
cp .env.example .env
$EDITOR .env       # 至少改 HOST；目录/端口按需
```

`.env` 常用变量：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `HOST` | `192.0.2.10` | 部署机地址，生成样式时用 |
| `DATA_DIR` | `./data` | 持久化目录（tile-proxy 管理配置） |
| `STYLE_DIR` | `./dist/mapstyles` | 样式输出目录，mapstyle 容器挂载它 |
| `TILE_PROXY_PORT` / `MAPSTYLE_PORT` | `9002` / `9003` | 宿主机端口 |
| `TZ` | `Asia/Shanghai` | 容器时区 |

## 3. 启动服务

### 方式 1：独立 compose（最简单）

```bash
docker compose up -d
docker compose ps
```

### 方式 2：合并进已有的 Immich compose

如果 Immich 已经由 compose 管理，把 `compose.yaml` 里的两个 service
（`tile-proxy`、`mapstyle`）复制到 Immich 的 compose 文件中，然后只启动新增服务：

```bash
cd /path/to/immich
docker compose config -q
docker compose up -d tile-proxy mapstyle     # 不要整项目 up，避免影响 Immich 自己的容器
```

两边的约定要一致：`STYLE_DIR` 是宿主机上 `immich_amap static --out` 的输出目录，
`NGINX_CONF` 指向 `deploy/nginx/style-server.conf`。

## 4. 生成样式

```bash
set -a; . ./.env; set +a

# 桌面 + 手机（http 静态托管，输出到 compose 挂载的目录）
python3 -m immich_amap static \
  --tile-base "http://$HOST:${TILE_PROXY_PORT:-9002}" \
  --public-base "http://$HOST:${MAPSTYLE_PORT:-9003}" \
  --center <经度>,<纬度> --zoom 15 \
  --out dist/mapstyles
```

- `--center` / `--zoom` 是初始视野（`经度,纬度`），只在 `static` 输出里生效；
- 临时调试也可以在电脑浏览器用 `data:` URL（`immich_amap urls`），但手机不可用，不作为部署方式；
- 生成物在 `dist/`（gitignored），改完重新生成即可，样式服务无需重启。

## 5. 填进 Immich

**管理 → 系统设置 → 地图与 GPS 设置 → 地图**：

```
亮色风格：http://<HOST>:9003/style-light.json
暗色风格：http://<HOST>:9003/style-dark.json
备选：    http://<HOST>:9003/style-sat.json
```

保存后刷新（`Ctrl+F5`）。若地址栏残留 `#15/31.17/121.61` 这类 hash，会覆盖初始视野，
先访问干净的 `http://<HOST>:2283/map`。

## 6. 中文地名库

Immich 的逆地理编码用镜像内 `/build/geodata` 的 GeoNames 数据，与底图无关。
要显示中文地名：

1. 从 **Immich 镜像原始层** 取数据（容器里 `/build/geodata` 被 volume 覆盖后不能当输入）：

   ```bash
   docker create --name immich-geodata-src ghcr.io/immich-app/immich-server:v3
   docker cp immich-geodata-src:/build/geodata /tmp/geodata-orig
   docker rm immich-geodata-src
   ```

2. 生成并部署：

   ```bash
   python3 -m immich_amap geodata --src /tmp/geodata-orig --dst /tmp/geodata-cn
   # 可选：--amap-cache、--level county、--prefix none 等，详见 geodata-cn.md
   ```

3. 给 `immich-server` 追加只读 volume：

   ```yaml
       immich-server:
         volumes:
           - ${UPLOAD_LOCATION}:/usr/src/app/upload
           - /path/to/geodata-cn:/build/geodata:ro     # <== 追加
   ```

4. 重启 `immich-server`，日志应出现：

   ```
   Successfully imported 229133 geodata records in 7.98s
   Initialized local reverse geocoder
   ```

5. 已存在资产重跑「管理 → 任务 → 提取元数据 → 全部运行」。

规则、粒度与高德精修见 [geodata-cn.md](geodata-cn.md)。

## 7. HTTPS / 反向代理 / CORS

- **混合内容**：Immich 走 https 时，`http://<HOST>:9002/9003` 会被浏览器拦。
  把两个服务挂到同一反代的路径下，然后用 https 地址重新生成样式：

  ```nginx
  location /tileproxy/ { proxy_pass http://127.0.0.1:9002/; }
  location /mapstyle/  { proxy_pass http://127.0.0.1:9003/; }
  ```

  ```bash
  python3 -m immich_amap static \
    --tile-base https://photos.example.com/tileproxy \
    --public-base https://photos.example.com/mapstyle \
    --center <经度>,<纬度> --zoom 15 --out dist/mapstyles
  ```

- **CORS**：`tile-proxy` 与仓库自带 nginx 配置都返回 `Access-Control-Allow-Origin: *`；
  若反代剥离了响应头，需要在反代补上（至少包含 `Access-Control-Allow-Origin`）。

## 8. 验收

| # | 检查 | 期望 |
| --- | --- | --- |
| 1 | `curl -s http://<HOST>:9002/health` | `{"ok":true,...}` |
| 2 | `curl -sI http://<HOST>:9003/style-light.json` | `200` |
| 3 | `curl -sI -H 'Origin: http://<HOST>:2283' http://<HOST>:9003/style-light.json` | 含 `Access-Control-Allow-Origin: *` |
| 4 | `python3 -m immich_amap selftest --limit 1` | 全部通过（可选 Pillow 校验 256×256） |
| 5 | Immich 地图页 | 底图出现、标记压准地物 |
| 6 | 手机 App 地图页 | 不黑屏（走 http 托管样式） |

## 9. 升级与回滚

```bash
# 升级 tile-proxy（版本钉死，不会自动升级）
docker compose pull tile-proxy
docker compose up -d tile-proxy

# 回滚样式：改回旧 URL 或重新生成旧参数即可，无状态
# 回滚地名库：把 immich-server 的 geodata volume 去掉/换回旧目录，重启并重跑元数据
```

compose 文件、`.env`、`DATA_DIR`、geodata 目录建议纳入备份。
