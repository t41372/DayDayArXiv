# 设计方案（Python + Actions）

## 现状摘要（基于代码审计）
- Python 实现分散在根目录脚本，`src/daydayarxiv` 为空。
- LLM 调用缺少严格的失败判定与统一的回退策略，导致“生成失败”内容仍被写入并发布。
- 配置依赖多处环境变量，缺少统一配置文件与类型校验。
- 状态管理与输出写入耦合，重试逻辑与失败判定分散。

## 目标架构
```
src/daydayarxiv/
  __init__.py
  __main__.py          # python -m daydayarxiv
  cli.py               # 参数解析与入口
  settings.py          # pydantic-settings + config file
  logging.py           # 统一日志配置
  models.py            # RawPaper/Paper/DailyData + 状态
  arxiv_client.py      # arXiv 获取封装
  llm/
    __init__.py
    client.py          # Langfuse + OpenAI 兼容 + 重试/回退
    validators.py      # 结果校验（避免 silent fail）
  pipeline.py          # 业务流水线
  storage.py           # JSON 读写/原子保存
  prompts/             # 迁移现有 prompts

fetch_arxiv.py         # 兼容旧入口的薄封装
```

## 核心流程
1. CLI 解析 -> 加载 Settings（env + TOML + .env）。
2. 获取 arXiv 原始数据（异步封装同步库），保存 `*_raw.json`。
3. 初始化/恢复状态（DailyData），注册待处理论文。
4. 使用 semaphore + asyncio 并发处理：
   - 每篇论文并发执行：翻译标题 + 单篇 TLDR。
   - 使用弱模型为主，失败自动回退到 backup。
5. 汇总日报（strong 模型为主，失败回退到 backup）。
6. 输出校验：任何关键字段无效则直接失败退出；否则写入最终 JSON。

## LLM 设计
- ProviderConfig：`base_url/api_key/model/rpm/timeout/max_retries`。
- 3 个 provider：weak/strong/backup。
- 每个 provider 独立 RateLimiter（平滑限流）。
- tenacity 负责重试与退避；分类可重试/不可重试错误。
- Langfuse：使用官方 OpenAI 兼容封装，保持 trace + session。

## 配置设计
- `Settings`（pydantic-settings v2）支持：
  - `.env`
  - `DAYDAYARXIV_CONFIG=daydayarxiv.toml`
  - `DAYDAYARXIV_*` 环境变量覆盖
- 输出目录、并发度、日志级别、LLM 配置、重试策略均可配置。

## Actions 调整
- 统一使用新的 CLI（保留 `fetch_arxiv.py` 兼容）。
- 当 CLI 返回非 0 时，Actions 失败并阻止 commit。
- 明确三类 LLM provider 的密钥与 base_url。

## 兼容性约束
- `DailyData`/`Paper` 必要字段保持不变；新增字段允许。
- 输出路径仍在 `daydayarxiv_frontend/public/data/{date}/`。

## 测试策略
- 单元测试：settings/llm/validators/storage/models。
- 集成测试：pipeline（mock arxiv + mock llm）。
- pytest-cov 强制 100% 覆盖率；pyright strict + ruff。

---

# 设计方案审查（对照验收标准）
- 可靠性/错误处理：通过 validators + 失败即退出机制满足。
- LLM 与 Langfuse：采用官方集成 + 三 provider 配置与回退。
- 配置管理：pydantic-settings + TOML + env 覆盖。
- 并发与性能：asyncio + semaphore + RateLimiter。
- 结构与工具链：全部迁移到 src/daydayarxiv；补齐 ruff/pyright/pytest。
- 文档与 Actions：README + workflow 更新。

未覆盖项：无（后续如新增问题，将在 todo 增补）。
