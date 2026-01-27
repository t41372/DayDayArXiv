# Day Day arXiv 天天 arXiv

daydayarxiv 是一个网站，每天 (大约) UTC 02:20 (左右) 更新最新的 arXiv 文章摘要，而且是中文的。

像刷信息流一样，在垃圾时间刷 arXiv 文章，看看有没有什么值得注意的文章。用中文所以你在刷的时候完全不用思考，一点都不累！

这个项目的目标是把刷 arXiv，跟上 arXiv 最新进展的行为变得非常愉悦，非常无脑，让普通人有事没事就可以刷刷 arXiv。

这个网站是个纯静态网站，用 GitHub action 每天更新数据 (主要怕被打，不敢用数据库)。文章数据实现了懒加载和浏览器缓存。

这个网站的优点是长得还行，起码我是这么觉得的。

> 注意: 本项目与 arXiv 本身没有任何关系。

## 本地开发的一些信息

GitHub action 会调用 python 脚本来生成每天的更新数据。更新数据会直接被放到 `daydayarxiv_frontend/public/data` 目录下，以 json 格式储存。

任务进度直接存储在最终输出的 JSON 文件中，使得中断恢复更为简单。每个日期和类别组合的数据都可以自动恢复之前的处理状态，不再需要单独的状态文件。

所以... 呃... 随着时间的推移，那个目录下应该会充满很多的 json 文件。我暂时不想管，毕竟我还是希望把这个网站做成纯静态的网站 (方便白嫖还不怕被打)。

总之，结构是这样
- 前端页面，action 会不断往里面塞 json 文件
- Python 脚本，被 action 调用来获取数据，处理数据，塞 json 之类的。

## Quickstart（本地开发）

1. 安装依赖（会安装当前项目本体）
```bash
uv sync
```
如果你刚拉取了更新（例如新增 CLI），请重新执行一次 `uv sync` 让入口脚本生效。

2. 运行（推荐 CLI）
```bash
uv run daydayarxiv --date 2025-03-01
```

也可以用模块入口：
```bash
uv run python -m daydayarxiv --date 2025-03-01
```

旧入口（仅作为兼容，仍需先执行 `uv sync`）：
```bash
uv run fetch_arxiv.py --date 2025-03-01
```

3. （可选）刷新前端数据索引（根据实际数据同步 `index.json`）
```bash
uv run daydayarxiv refresh-index
```

可按类别过滤并进行严格校验：
```bash
uv run daydayarxiv refresh-index --category cs.AI --fail-on-issues
```

允许部分数据进入索引，但会输出警告与重跑命令：
```bash
uv run daydayarxiv refresh-index --allow-partial
```

4. （可选）前端本地开发
```bash
cd daydayarxiv_frontend
npm install
npm run dev
```

### 配置说明（简版）

- 配置只通过环境变量读取（`.env` 会被自动读取）。
- 如果想走环境变量配置，可复制 `.env.sample` 为 `.env` 并补齐。
- `backup` provider 可选；未配置时不会使用 fallback。
- Langfuse 默认开启；若本地不需要可设置：
  - `DDARXIV_LANGFUSE_ENABLED=false`
- 默认遇到失败会标记并等待下次重试；如需严格退出可设置：
  - `DDARXIV_FAIL_ON_ERROR=true` 或配置 `fail_on_error = true`
- 状态写入频率（减少频繁磁盘写入，可根据需要调小或设为 0 关闭节流）：
  - `DDARXIV_STATE_SAVE_INTERVAL_S=1.0` 或配置 `state_save_interval_s = 1.0`

### 常见问题 / 故障排查

- 报错 “ModuleNotFoundError: No module named 'daydayarxiv'”
  - 请先执行 `uv sync`（确保项目本体已安装），然后使用 `uv run daydayarxiv ...` 或 `uv run python -m daydayarxiv ...`。
  - 若仍想使用旧入口，请确认已执行 `uv sync` 后再运行 `uv run fetch_arxiv.py ...`。
- 报错 “Failed to spawn: daydayarxiv”
  - 说明 CLI 脚本尚未安装到环境中；请重新执行 `uv sync` 或 `uv sync --reinstall`。
- 报错 “Langfuse is enabled but ... keys are missing”
  - 说明开启了 Langfuse 但未配置 key；要么补齐 `DDARXIV_LANGFUSE_PUBLIC_KEY/DDARXIV_LANGFUSE_SECRET_KEY`，要么关闭 Langfuse。
- 生成失败后是否退出
  - 默认不会退出，会标记失败并等待下次运行自动重试。
  - 如需严格失败（CI 直接退出），设置 `fail_on_error = true`。

# DayDayArXiv

A tool to fetch and process arXiv papers with LLM-powered translation and summarization.

## Usage

```bash
uv run daydayarxiv [command] [options]
```

### Commands

- `run` (default): Fetch and process arXiv papers.
- `refresh-index`: Rebuild `daydayarxiv_frontend/public/data/index.json` from actual data files.

### Options

#### `run` options
- `--date DATE`: Process papers for a specific date (YYYY-MM-DD format)
- `--start-date DATE`: Start date for processing a date range (YYYY-MM-DD format)
- `--end-date DATE`: End date for processing a date range (YYYY-MM-DD format)
- `--category CATEGORY`: arXiv category to fetch (default: cs.AI)
- `--max-results N`: Maximum number of papers to fetch (default: 1000)
- `--force`: Force refresh data even if it exists
- `--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}`: Set logging level (default: INFO)

#### `refresh-index` options
- `--data-dir PATH`: Data directory (default from settings/env)
- `--category CATEGORY`: Restrict to specific categories (repeatable)
- `--no-content-validation`: Skip summary/content validation checks
- `--dry-run`: Do not write `index.json`, only report issues
- `--fail-on-issues`: Exit non-zero if invalid files are found
- `--allow-partial`: Include partially valid data in index while warning

### Examples

Process papers from a specific date:
```bash
uv run daydayarxiv --date 2025-03-01
```

Process papers from a date range:
```bash
uv run daydayarxiv --start-date 2025-03-01 --end-date 2025-03-07
```

Process papers from a different category:
```bash
uv run daydayarxiv --date 2025-03-01 --category cs.CL
```

Force refresh existing data:
```bash
uv run daydayarxiv --date 2025-03-01 --force
```

Refresh index.json for existing data:
```bash
uv run daydayarxiv refresh-index
```

配置与限流建议通过 `.env` 或环境变量完成（见上文 Quickstart）。
