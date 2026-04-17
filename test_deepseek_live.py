#!/usr/bin/env python3
"""
DeepSeek LLM 真实调用测试
测试：基础对话、工具调用、工具去重、多轮对话
使用 test/aig/abs_calculator_1.aig 作为真实数据
"""

import sys, os, asyncio, json

# 必须以包方式运行
os.chdir('/root/cktclaw')
sys.path.insert(0, '/root')

PASS = "✅"; FAIL = "❌"
results = []

def check(name, ok, detail=""):
    results.append((PASS if ok else FAIL, name))
    print(f"  {PASS if ok else FAIL} {name}" + (f": {detail}" if detail else ""))

TEST_AIG = "/root/cktclaw/test/aig/abs_calculator_1.aig"

print("=" * 70)
print("DeepSeek LLM 真实调用测试")
print("=" * 70)

# ── Test 1: 基础连通性 ──────────────────────────────────────
print("\n[1] DeepSeek API 连通性测试")
try:
    from cktclaw.models.providers.deepseek_provider import DeepSeekProvider
    provider = DeepSeekProvider(verbose=False)
    resp = provider.chat_with_context([
        {"role": "user", "content": "你好，请用一句话介绍自己。"}
    ])
    ok = isinstance(resp, str) and len(resp) > 5 and "Error" not in resp
    check("API 连通性", ok, resp[:80] if ok else resp[:200])
except Exception as e:
    check("API 连通性", False, str(e))
    provider = None

# ── Test 2: 工具调用能力 ────────────────────────────────────
print("\n[2] DeepSeek 工具调用能力测试")
if provider:
    try:
        tools = [{
            "type": "function",
            "function": {
                "name": "yosys",
                "description": "调用 Yosys 进行逻辑综合和电路分析",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "args": {"type": "string", "description": "Yosys 命令参数"}
                    },
                    "required": ["args"]
                }
            }
        }]

        resp = provider.chat_with_context(
            messages=[
                {"role": "system", "content": "你是 CktClaw EDA 助手，需要调用工具分析电路。"},
                {"role": "user", "content": f"请用 yosys 分析这个 AIG 文件的基本统计信息：{TEST_AIG}"}
            ],
            tools=tools
        )

        is_tool_call = isinstance(resp, dict) and resp.get("type") == "tool_call"
        check("DeepSeek 返回工具调用", is_tool_call,
              f"name={resp.get('name')}" if is_tool_call else f"type={type(resp).__name__}, resp={str(resp)[:100]}")

        if is_tool_call:
            check("工具名称正确", resp.get("name") == "yosys", f"name={resp.get('name')}")
            args = resp.get("arguments", {})
            check("工具参数包含 AIG 路径", TEST_AIG in str(args), f"args={args}")
    except Exception as e:
        check("工具调用测试", False, str(e))
else:
    check("工具调用测试", False, "provider 未初始化（API 连通性失败）")

# ── Test 3: 多轮对话 + 工具去重 ────────────────────────────
print("\n[3] 多轮对话 + 工具去重集成测试")

async def run_multiturn_test():
    from cktclaw.models.providers.deepseek_provider import DeepSeekProvider
    from cktclaw.harness.query.query_loop_enhanced import EnhancedQueryLoop
    from cktclaw.harness.query.query_types import QueryConfig

    ds = DeepSeekProvider()
    tool_call_log = []

    tools = [{
        "type": "function",
        "function": {
            "name": "yosys",
            "description": "调用 Yosys 进行逻辑综合和电路分析",
            "parameters": {
                "type": "object",
                "properties": {"args": {"type": "string"}},
                "required": ["args"]
            }
        }
    }]

    async def llm_wrapper(msgs):
        resp = await asyncio.to_thread(ds.chat_with_context, msgs, tools)
        if resp is None:
            return {"role": "assistant", "content": "无响应"}
        if isinstance(resp, str):
            return {"role": "assistant", "content": resp}
        if isinstance(resp, dict) and resp.get("type") == "tool_call":
            return {
                "role": "assistant", "content": "",
                "tool_calls": [{
                    "id": resp.get("tool_call_id", "call_1"),
                    "type": "function",
                    "function": {
                        "name": resp.get("name", ""),
                        "arguments": json.dumps(resp.get("arguments", {})),
                    }
                }]
            }
        return {"role": "assistant", "content": str(resp)}

    async def tool_executor(name, args):
        tool_call_log.append(name)
        # 模拟 yosys 返回真实格式的结果
        return (
            "Yosys 分析结果:\n"
            "Number of wires: 100\n"
            "Number of cells: 92\n"
            "  $_AND_: 47\n"
            "  $_NOT_: 45\n"
        )

    cfg = QueryConfig(
        system_prompt=(
            "你是 CktClaw EDA 助手，专注于电路分析。"
            "工具执行完毕后，直接用中文总结结果，不要重复调用同一工具。"
        ),
        max_turns=8
    )
    loop = EnhancedQueryLoop(llm_wrapper, tool_executor, cfg)

    messages = [
        {"role": "user", "content": f"请用 yosys 分析这个 AIG 文件：{TEST_AIG}，给出电路统计信息。"}
    ]

    final = None
    async for r in loop.run(messages):
        final = r

    return tool_call_log, final

try:
    tool_log, final = asyncio.run(run_multiturn_test())
    check("多轮对话完成", final is not None and final.state.value == "terminal")
    yosys_count = tool_log.count("yosys")
    check("yosys 只被调用一次（去重生效）", yosys_count <= 1,
          f"yosys 调用次数: {yosys_count}")
    if final and final.final_response:
        resp_preview = final.final_response[:120].replace('\n', ' ')
        check("最终响应非空", len(final.final_response) > 10, resp_preview)
except Exception as e:
    check("多轮对话测试", False, str(e))
    import traceback; traceback.print_exc()

# ── Test 4: 中文 EDA 对话 ───────────────────────────────────
print("\n[4] 中文 EDA 对话能力测试")
if provider:
    try:
        resp = provider.chat_with_context([
            {"role": "system", "content": "你是 CktClaw EDA 助手，专注于电路分析。"},
            {"role": "user", "content": "AIG（And-Inverter Graph）是什么？用两句话解释。"}
        ])
        ok = isinstance(resp, str) and len(resp) > 20 and "Error" not in resp
        check("中文 EDA 对话", ok, resp[:100] if ok else resp[:200])
    except Exception as e:
        check("中文 EDA 对话", False, str(e))
else:
    check("中文 EDA 对话", False, "provider 未初始化")

# ── Summary ────────────────────────────────────────────────
print("\n" + "=" * 70)
passed = sum(1 for s, _ in results if s == PASS)
failed = sum(1 for s, _ in results if s == FAIL)
print(f"测试结果: {passed} 通过 / {failed} 失败 / {len(results)} 总计")
if failed == 0:
    print("🎉 DeepSeek LLM 调用测试全部通过！")
else:
    print("⚠️  部分测试失败，请检查上方输出。")
print("=" * 70)
