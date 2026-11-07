# Immich 高德地图工具 —— 常用命令入口
#
# 覆盖默认值的方式：make urls TILE_BASE=http://192.0.2.10:9002
PYTHON      ?= python3
TILE_BASE   ?= http://192.0.2.10:9002
PUBLIC_BASE ?= http://192.0.2.10:9003
HOST        ?=
REMOTE_STYLE_DIR ?= /srv/immich-amap/mapstyles
CENTER      ?= 121.4737,31.2304
ZOOM        ?= 15
DIST        ?= dist

.DEFAULT_GOAL := help

.PHONY: help install urls compact static selftest test lint format check clean deploy-static

help: ## 显示可用命令
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## 安装开发依赖（可编辑安装）
	$(PYTHON) -m pip install -e ".[dev]"

urls: ## 生成 data: URL 版样式（桌面端直接粘贴）
	$(PYTHON) -m immich_amap urls --tile-base $(TILE_BASE) --out $(DIST)

compact: ## 生成极简版 data: URL（单域名、无背景层）
	$(PYTHON) -m immich_amap urls --tile-base $(TILE_BASE) --emit-json --compact --out $(DIST)

static: ## 生成 http 静态托管版样式（桌面 + 手机端）
	$(PYTHON) -m immich_amap static \
		--tile-base $(TILE_BASE) \
		--center $(CENTER) --zoom $(ZOOM) \
		--public-base $(PUBLIC_BASE) \
		--out $(DIST)/mapstyles

selftest: ## 端到端抓图自测（依赖正在运行的 tile-proxy）
	$(PYTHON) -m immich_amap selftest --limit 1

test: ## 运行单元测试
	$(PYTHON) -m pytest

lint: ## 代码风格检查
	$(PYTHON) -m ruff check .

format: ## 自动修复可修复的风格问题
	$(PYTHON) -m ruff check --fix .

check: lint test ## 提交前检查（lint + test）

deploy-static: static ## 同步静态样式到远端主机（HOST=user@host REMOTE_STYLE_DIR=/srv/...）
	@test -n "$(HOST)" || { echo "用法: make deploy-static HOST=user@host [REMOTE_STYLE_DIR=/srv/immich-amap/mapstyles]"; exit 1; }
	ssh $(HOST) 'mkdir -p $(REMOTE_STYLE_DIR)'
	scp -r $(DIST)/mapstyles/*.json $(HOST):$(REMOTE_STYLE_DIR)/
	ssh $(HOST) 'chmod -R 755 $(REMOTE_STYLE_DIR)'

clean: ## 清理构建产物
	rm -rf $(DIST) .pytest_cache .ruff_cache build *.egg-info
