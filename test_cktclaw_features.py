#!/usr/bin/env python3
"""
CktClaw 功能测试脚本
测试：工具去重、debug输出删除、AI4EDA路径配置、本地模型配置、workflow确认逻辑
"""

import sys
import os
import asyncio
import json

sys.path.insert(0, '/root/cktclaw')

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"

results = []

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    print(f"  {status} {name}" + (f": {detail}" if detail else ""))

print("=" * 60)
print("CktClaw 功能测试")
print("=" * 60)

# ── Test 1: Config ──────────────────────────────────────────
print("\n[1] 配置加载测试")
try:
    import config
    check("AI4EDA_TOOLKIT_PATH 已配置", hasattr(config, 'AI4EDA_TOOLKIT_PATH'),
          config.AI4EDA_TOOLKIT_PATH)
    check("LOCAL_CHAT_MODEL 已配置", hasattr(config, 'LOCAL_CHAT_MODEL'))
    check("CODEV_PATH 已配置", hasattr(config, 'CODEV_PATH'), config.CODEV_PATH)
except Exception as e:
    check("config 导入", False, str(e))

# ── Test 2: Env var override ────────────────────────────────
print("\n[2] 环境变量覆盖测试")
os.environ['CKTCLAW_LOCAL_MODEL'] = 'Qwen/Qwen2.5-3B'
import importlib
importlib.reload(config)
check("CKTCLAW_LOCAL_MODEL 覆盖 CODEV_PATH",
      config.CODEV_PATH == 'Qwen/Qwen2.5-3B',
      f"CODEV_PATH={config.CODEV_PATH}")
del os.environ['CKTCLAW_LOCAL_MODEL']
importlib.reload(config)

os.environ['CKTCLAW_AI4EDA_PATH'] = '/test/path/ai4eda'
importlib.reload(config)
check("CKTCLAW_AI4EDA_PATH 覆盖 AI4EDA_TOOLKIT_PATH",
      config.AI4EDA_TOOLKIT_PATH == '/test/path/ai4eda',
      f"AI4EDA_TOOLKIT_PATH={config.AI4EDA_TOOLKIT_PATH}")
del os.environ['CKTCLAW_AI4EDA_PATH']
importlib.reload(config)

# ── Test 3: Debug output removed ───────────────────────────
print("\n[3] Debug 输出删除测试")
with open('/root/cktclaw/handlers/chat_handler_v2.py') as f:
    content = f.read()
check("🔍 LLM Response Type 已删除", "🔍 LLM Response Type" not in content)
check("🔍 LLM Response (first 100 chars) 已删除",
      "🔍 LLM Response (first 100 chars)" not in content)

# ── Test 4: Tool deduplication ─────────────────────────────
print("\n[4] 工具去重逻辑测试")
with open('/root/cktclaw/harness/query/query_loop_enhanced.py') as f:
    content = f.read()
check("called_tool_signatures 字段存在", "called_tool_signatures" in content)
check("_filter_duplicate_tools 方法存在", "_filter_duplicate_tools" in content)
check("重复调用警告消息存在", "检测到重复工具调用" in content)

# ── Test 5: Tool dedup logic (unit test) ───────────────────
print("\n[5] 工具去重逻辑单元测试")
try:
    from harness.query.query_loop_enhanced import EnhancedQueryLoop, LoopState
    from harness.query.query_types import QueryConfig

    async def dummy_llm(msgs): return {"role": "assistant", "content": "ok"}
    async def dummy_tool(name, args): return "result"

    cfg = QueryConfig(system_prompt="", max_turns=5)
    loop = EnhancedQueryLoop(dummy_llm, dummy_tool, cfg)
    state = LoopState(messages=[])

    tool_calls = [
        {"id": "1", "type": "function", "function": {"name": "yosys", "arguments": '{"args": "stat"}'}},
        {"id": "2", "type": "function", "function": {"name": "yosys", "arguments": '{"args": "stat"}'}},
        {"id": "3", "type": "function", "function": {"name": "abc",   "arguments": '{"args": "print_stats"}'}},
    ]

    filtered, skipped = loop._filter_duplicate_tools(tool_calls, state)
    check("第一次调用 yosys 通过", len(filtered) == 2, f"filtered={len(filtered)}, skipped={len(skipped)}")
    check("重复 yosys 被跳过", len(skipped) == 1)

    # 再次调用同样的工具，应该全部被跳过
    filtered2, skipped2 = loop._filter_duplicate_tools(tool_calls, state)
    check("第二次调用全部被跳过", len(filtered2) == 0, f"filtered={len(filtered2)}, skipped={len(skipped2)}")

except Exception as e:
    check("工具去重单元测试", False, str(e))

# ── Test 6: AI4EDA handler uses config ─────────────────────
print("\n[6] AI4EDA handler 配置化测试")
with open('/root/cktclaw/handlers/ai4eda_handler.py') as f:
    content = f.read()
check("硬编码路径已删除", "/home/wjx/" not in content)
check("使用 config.AI4EDA_TOOLKIT_PATH", "config.AI4EDA_TOOLKIT_PATH" in content)

# ── Test 7: Orchestrator confirmation ──────────────────────
print("\n[7] Orchestrator 需求确认测试")
with open('/root/cktclaw/orchestrator/engine.py') as f:
    content = f.read()
check("需求确认逻辑存在", "Interactive requirement gathering" in content)
check("用户输入提示存在", "请描述您的具体需求" in content)
check("确认执行提示存在", "确认执行" in content)
check("取消逻辑存在", '"cancelled"' in content)

# ── Test 8: gitignore ──────────────────────────────────────
print("\n[8] .gitignore 模型文件排除测试")
with open('/root/cktclaw/.gitignore') as f:
    content = f.read()
check("models/qwen/ 已排除", "models/qwen/" in content)
check("*.safetensors 已排除", "*.safetensors" in content)
check("*.bin 已排除", "*.bin" in content)

# ── Test 9: QueryLoop import ───────────────────────────────
print("\n[9] QueryLoop 完整导入测试")
try:
    from harness.query.query_loop_enhanced import EnhancedQueryLoop
    from harness.query.query_types import QueryConfig, QueryStateEnum
    check("EnhancedQueryLoop 导入成功", True)
    check("QueryConfig 导入成功", True)
except Exception as e:
    check("QueryLoop 导入", False, str(e))

# ── Test 10: Async tool dedup end-to-end ───────────────────
print("\n[10] 工具去重端到端异步测试")
async def run_dedup_test():
    call_count = {"yosys": 0}
    llm_call_count = [0]

    async def mock_llm(msgs):
        llm_call_count[0] += 1
        # 第1轮返回工具调用，第2轮及以后返回文本
        if llm_call_count[0] == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "t1", "type": "function",
                     "function": {"name": "yosys", "arguments": '{"args":"stat"}'}},
                ]
            }
        return {"role": "assistant", "content": "分析完成"}

    async def mock_tool(name, args):
        call_count[name] = call_count.get(name, 0) + 1
        return f"{name} result"

    from harness.query.query_loop_enhanced import EnhancedQueryLoop
    from harness.query.query_types import QueryConfig, QueryStateEnum

    cfg = QueryConfig(system_prompt="", max_turns=5)
    loop = EnhancedQueryLoop(mock_llm, mock_tool, cfg)

    messages = [{"role": "user", "content": "分析电路"}]
    final = None
    async for r in loop.run(messages):
        final = r

    return call_count, final

try:
    call_count, final = asyncio.run(run_dedup_test())
    check("yosys 只被调用一次", call_count.get("yosys", 0) == 1,
          f"实际调用次数: {call_count.get('yosys', 0)}")
    check("最终状态为 TERMINAL", final is not None and final.state.value == "terminal")
except Exception as e:
    check("端到端异步测试", False, str(e))

# ── Summary ────────────────────────────────────────────────
print("\n" + "=" * 60)
passed = sum(1 for s, _, _ in results if s == PASS)
failed = sum(1 for s, _, _ in results if s == FAIL)
print(f"测试结果: {passed} 通过 / {failed} 失败 / {len(results)} 总计")
if failed == 0:
    print("🎉 所有测试通过！CktClaw 功能正常。")
else:
    print("⚠️  有测试失败，请检查上方输出。")
print("=" * 60)
