# 验收标准（核心）

## 目标范围
- 仅重构/重写 Python 与 GitHub Actions；前端代码不改动。
- 输出 JSON 结构与前端既有预期保持一致（允许新增字段，但不可删除/改名已用字段）。

## 可靠性与错误处理
- 不允许 silent fail：任何关键输出（title_zh/tldr_zh/summary）为空或包含失败提示时，流水线必须失败并返回非 0 退出码。
- LLM 调用具备重试与退避策略；在弱/强模型失败时自动回退到 backup 模型。
- 对于可恢复错误（超时/连接重置/429/5xx）进行可控重试；对不可恢复错误（认证失败/无额度）不进行同供应商重试，直接回退或失败。
- 输出文件写入具有原子性，状态一致且可恢复。

## LLM 与 Langfuse
- 三种 LLM：strong（日报总结）、weak（翻译/单篇 TLDR）、backup（兜底）。
- 三种 LLM 使用不同 provider（不同 base_url / api_key / model / rpm）。
- 通过 Langfuse 官方推荐的 OpenAI 兼容集成方式进行 tracing，并保留可开关配置。

## 配置管理
- 使用 pydantic-settings v2；统一环境变量前缀，支持 `.env`。
- 支持单一配置文件（如 `daydayarxiv.toml`），可通过环境变量覆盖。
- README 中给出完整配置与示例。

## 并发与性能
- 使用 asyncio + semaphore 控制并发。
- 每个 provider 有独立限流器（rpm），并保证请求均匀分布。
- 处理批次时避免阻塞事件循环（同步 I/O 通过线程或分离封装）。

## 结构与工具链
- 项目结构遵循 `src/daydayarxiv`。
- Python 3.12+ 最佳实践（类型标注完整、避免隐式 Any）。
- 工具链：uv、ruff、pyright（strict）、pytest（含覆盖率 100%）。

## 测试与质量门禁
- 单元测试 + 关键路径集成测试覆盖率达到 100%。
- 在提交前运行：ruff、pyright、pytest -q。

## 文档
- README 增加 quickstart、配置说明、常见问题与故障排查。
- 关键模块有清晰注释。

## GitHub Actions
- Actions 使用新的 CLI/配置方式，能在失败时阻止自动提交。
- 仍保持每日定时与手动触发能力。

## 输出兼容性
- `DailyData` 与 `Paper` 字段最小集合保持：
  - `date, category, summary, papers`
  - `paper.arxiv_id, title, title_zh, authors, abstract, tldr_zh, categories, primary_category, comment, published_date, updated_date`
- 保留现有扩展字段（如 `processing_status`, `attempts`, `pdf_url`）。
