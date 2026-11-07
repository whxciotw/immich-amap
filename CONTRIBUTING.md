# Contributing

- Python 3.9+，无运行时依赖；开发依赖：`python3 -m pip install -e ".[dev]"`。
- 提交前跑 `python3 -m ruff check .` 与 `python3 -m pytest`（CI 同款）。
- `immich_amap/tiles.py` 是高德瓦片地址/参数的唯一事实来源；改它时同步
  `web/maker.html` 里的 `TILE_CONFIG`，`tests/test_web.py` 会校验漂移。
- 不要提交 `dist/`、`.env`、真实内网 IP/域名、个人位置、访问凭据等非公开信息；
  示例统一用 `<HOST>`、`192.0.2.10`、`example.com`。
- 提交信息用 Conventional Commits（`feat:` / `fix:` / `docs:` / `chore:` …）。
- 代码以 MIT 发布；提交即表示同意以同一许可证发布。
