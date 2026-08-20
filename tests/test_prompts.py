from prompts import MAIN_SYSTEM_PROMPT, SUBAGENT_TASK_TEMPLATE


def test_main_prompt_has_replace_slots_and_constraints():
    formatted = (
        MAIN_SYSTEM_PROMPT
        .replace("{max_subagents}", "5")
        .replace("{output_dir}", "./output/")
    )
    assert "{max_subagents}" not in formatted
    assert "./output/" in formatted
    # 五条核心约束的关键词都在
    for key in ("候选", "大纲", "并行", "Task", "检索覆盖说明"):
        assert key in formatted


def test_subagent_template_placeholders():
    formatted = SUBAGENT_TASK_TEMPLATE.format(
        topic="坎瑞亚大灾变", seed_keywords="坎瑞亚, 黑日王朝", chapter_title="大灾变",
    )
    assert "坎瑞亚大灾变" in formatted
    assert "黑日王朝" in formatted
    assert "{topic}" not in formatted
    for key in ("滚雪球", "出处", "连续 2 轮"):
        assert key in formatted
