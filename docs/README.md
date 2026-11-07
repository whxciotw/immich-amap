# 文档索引

命令统一用 `python3 -m immich_amap <子命令>`；`make` 只是薄封装。

## 阅读路径

| 目的 | 顺序 |
| --- | --- |
| 完整部署（电脑 + 手机） | [quickstart.md](quickstart.md) 或 [README](../README.md) |
| 长期部署（任意 Docker 主机） | [deployment.md](deployment.md) → [operations.md](operations.md) |
| 明白为什么会偏、纠偏原理 | [architecture.md](architecture.md) |
| 地点显示英文 / 村镇样式 | [geodata-cn.md](geodata-cn.md) |
| 手机端黑屏 / 初始位置不对 | [mobile.md](mobile.md) |

## 约定

- 文中 `<HOST>` 指部署机在局域网中的 IP 或域名；`<DATA_DIR>` 指持久化目录。
  `.env` 里的变量（`HOST`、`DATA_DIR`、端口等）按自己的环境修改。
- 「纠偏」= GCJ-02 → WGS-84 的逐瓦片重采样，由 `tile-proxy` 完成；
  样式名不带 `fixed` 的是直连高德、不纠偏。
- `dist/` 是生成物，不入库，用 `make` / CLI 重新生成。
- 当前行为以代码和其余文档为准。
