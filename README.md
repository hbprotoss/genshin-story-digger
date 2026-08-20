# story-digger-agent

原神故事线挖掘 agent：给定故事线名称，从 MongoDB 中的六类游戏文本（任务对白、书籍、圣遗物、武器、地图可交互文本、角色资料）整理出带出处的中文 Markdown 文档。

基于 claude-code-sdk 驱动 MiMo 模型（mimo-v2.5-pro），主 agent 规划拆分章节后并行派发 sub agent 滚雪球检索，最后汇总成文。

## 运行

```bash
uv run python src/__main__.py [--config /root/.story-digger-agent/config.toml]
```

交互式会话：
1. 输入一个故事线关键词（可能模糊，如"渊下""坎瑞亚"）；
2. 主 agent 先列出候选故事线让你确认（可多选/补充描述）；
3. 确认后 agent 输出大纲、并行派发 sub agent 挖掘，最后写出 Markdown。

配置文件 `config.toml` 含 `[mongo]` / `[chat]` / `[agent]` 三段：

```toml
[mongo]   host / port / database / username / password / auth_source(可选，默认 admin)
[chat]    base_url(Anthropic 兼容端点) / api_key / model / temperature(保留但实现忽略) / stream / debug_llm
[agent]   output_dir(默认 ./output/) / max_subagents(默认 5)
```

产出文档写入 `[agent].output_dir`（默认 `./output/`）。

## 测试

```bash
uv run --with pytest pytest tests/ -v
```

需要 MongoDB 可达（`tests/conftest.py` 读真实 config，连不上相关用例会 skip）；端到端 LLM 交互为手动冒烟，不在测试内。

## 设计文档

- `docs/superpowers/specs/2026-08-20-story-digger-agent-design.md`：设计文档
- `docs/superpowers/plans/2026-08-20-story-digger-agent.md`：实施计划