# Repository Guidelines

daydayarxiv 是一个网站，每天 (大约) UTC 02:20 (左右) 更新最新的 arXiv 文章摘要，而且是中文的。

像刷信息流一样，在垃圾时间刷 arXiv 文章，看看有没有什么值得注意的文章。用中文所以你在刷的时候完全不用思考，一点都不累！

这个项目的目标是把刷 arXiv，跟上 arXiv 最新进展的行为变得非常愉悦，非常无脑，让普通人有事没事就可以刷刷 arXiv。

这个网站是个纯静态网站，用 GitHub action 每天更新数据 (主要怕被打，不敢用数据库)，数据直接以 json 格式储存在 `daydayarxiv_frontend/public/data` 目录下。每日数据实现了懒加载和浏览器缓存。

更新数据的逻辑用 astral uv + python 实现。


## Project Structure & Module Organization
- `src/daydayarxiv/` holds the core Python package (CLI, pipeline, clients, settings).
- `fetch_arxiv.py` is a legacy entry point kept for compatibility.
- `tests/unit/` contains unit tests (files named `test_*.py`).
- `daydayarxiv_frontend/` is a Next.js/Tailwind frontend; generated JSON data lands in `daydayarxiv_frontend/public/data/`.
- `logs/` and `work/` store runtime artifacts; avoid committing generated files unless explicitly needed.

## Build, Test, and Development Commands
- `uv sync` installs dependencies and the local package.
- `uv run daydayarxiv --date 2025-03-01` runs the primary CLI.
- `uv run python -m daydayarxiv --date 2025-03-01` runs the module entry.
- `uv run fetch_arxiv.py --date 2025-03-01` runs the legacy script.
- `uv run pytest` executes tests (coverage enforced).
- `uv run ruff check src/daydayarxiv` runs lint checks.
- `uv run pyright` runs strict type checking.
- Frontend: `cd daydayarxiv_frontend && npm install && npm run dev` for local UI work.

## Coding Style & Naming Conventions
- Python 3.12, 4-space indentation, and a 100-character line limit.
- Linting via Ruff (E/F/I/B/UP/SIM/RUF); type checking via Pyright in strict mode.
- Use `snake_case` for modules/functions and `test_*.py` naming in `tests/unit/`.

## Testing Guidelines
- Test framework: `pytest` with `pytest-asyncio`.
- Coverage is required at 100% (`--cov-fail-under=100`).
- Add or update tests alongside behavior changes, especially CLI and pipeline logic.

## Commit & Pull Request Guidelines
- Follow existing commit subject patterns such as `fix: ...`, `chore: ...`, or scoped forms like `fix(ci): ...`.
- Data refresh commits use `Update data: YYYY-MM-DD HH:MM:SS UTC` in history; keep that format when applicable.
- PRs should include a concise summary, test results, and screenshots for frontend changes.

## Configuration & Secrets
- Configuration is read from environment variables; `.env` is auto-loaded.
- Use `.env.sample` as a template and keep secrets out of version control.
- Optional integrations (e.g., Langfuse) can be disabled via env flags when developing locally.
