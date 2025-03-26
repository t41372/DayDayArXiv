# Day Day arXiv 天天 arXiv

daydayarxiv 是一个网站，每天 (大约) UTC 00:20 (左右) 更新最新的 arXiv 文章摘要，而且是中文的。

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

# DayDayArXiv

A tool to fetch and process arXiv papers with LLM-powered translation and summarization.

## Usage

```bash
uv run fetch_arxiv.py [options]
```

### Options

- `--date DATE`: Process papers for a specific date (YYYY-MM-DD format)
- `--start-date DATE`: Start date for processing a date range (YYYY-MM-DD format)
- `--end-date DATE`: End date for processing a date range (YYYY-MM-DD format)
- `--category CATEGORY`: arXiv category to fetch (default: cs.AI)
- `--rpm N`: Maximum API requests per minute (default: 60)
- `--max-results N`: Maximum number of papers to fetch (default: 1000)
- `--force`: Force refresh data even if it exists
- `--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}`: Set logging level (default: INFO)

### Examples

Process papers from a specific date:
```bash
uv run fetch_arxiv.py --date 2025-03-01
```

Process papers from a date range:
```bash
uv run fetch_arxiv.py --start-date 2025-03-01 --end-date 2025-03-07
```

Process papers from a different category:
```bash
uv run fetch_arxiv.py --date 2025-03-01 --category cs.CL
```

Force refresh existing data:
```bash
uv run fetch_arxiv.py --date 2025-03-01 --force
```

Adjust rate limiting:
```bash
uv run fetch_arxiv.py --date 2025-03-01 --rpm 30
```


