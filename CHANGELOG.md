# Changelog

本项目的重要变更。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
日期为北京时间。

## [Unreleased]

### Added

- MIT License；通用 Docker Compose 部署（`compose.yaml` + `.env.example`）；
  独立 Python 包 `immich_amap` 与 CLI（`urls` / `static` / `selftest` / `geodata` /
  `geodata-sim` / `amap-cache`）；
- 中文地名库生成：中文化、城市级归一化、增强点集、全量别名、高德精修、粒度/显示参数；
- 高德亮色 / 暗色 / 卫星样式，GCJ-02 纠偏（tile-proxy）与桌面 `data:` URL 两种形态；
- 浏览器版生成器 `web/maker.html`；pytest/ruff 测试与 GitHub Actions CI。

### Changed

- 文档重构为通用 Docker 部署，示例统一使用 `<HOST>` / `192.0.2.10`；
- 生成物（`dist/`、样式 JSON、URL 清单）不再入库，用 CLI / `make` 生成。

### Removed

- 主机/个人环境专属的部署记录、快照与内部协作说明，不进入公开仓库。

## [1.0.0] - 2026-11-05

仓库规整：代码合并为 `immich_amap` 包、文档拆分、测试与工具链。
