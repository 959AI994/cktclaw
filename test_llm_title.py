"""
测试 LLM 标题生成功能
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cktmem.title_generator import generate_session_title_with_llm, generate_session_title


async def test_llm_title_generation():
    """测试 LLM 标题生成"""
    print("=" * 60)
    print("测试 LLM 标题生成")
    print("=" * 60)

    # 测试用例
    test_cases = [
        {
            "user": "帮我分析上海交通大学的电路设计",
            "assistant": "好的，我来帮你分析上海交通大学（SJTU）的电路设计特点...",
        },
        {
            "user": "/reverse adder.aig",
            "assistant": "正在逆向工程 adder.aig 文件，这是一个加法器电路...",
        },
        {
            "user": "这个 RISC-V CPU 的性能如何？",
            "assistant": "RISC-V CPU 的性能分析如下：时钟频率 2GHz，面积 0.5mm²...",
        },
        {
            "user": "优化这个乘法器的延迟",
            "assistant": "我将帮你优化乘法器的关键路径延迟...",
        },
        {
            "user": "module counter(input clk, output [7:0] count);",
            "assistant": "这是一个 8 位计数器模块...",
        },
    ]

    # 尝试导入 LLM 分析器
    try:
        from models.llm_analyzer import LLMVerilogAnalyzer
        llm_analyzer = LLMVerilogAnalyzer(verbose=False)
        print("\n✓ LLM 分析器已加载\n")
        use_llm = True
    except Exception as e:
        print(f"\n⚠ 无法加载 LLM 分析器: {e}")
        print("将使用基于规则的标题生成\n")
        llm_analyzer = None
        use_llm = False

    for i, case in enumerate(test_cases, 1):
        user_msg = case["user"]
        assistant_msg = case["assistant"]

        print(f"\n{'='*60}")
        print(f"测试用例 {i}")
        print(f"{'='*60}")
        print(f"用户: {user_msg[:60]}...")
        print(f"助手: {assistant_msg[:60]}...")

        # 基于规则的标题
        rule_title = generate_session_title(user_msg)
        print(f"\n规则生成: {rule_title}")

        # LLM 生成的标题
        if use_llm:
            llm_title = await generate_session_title_with_llm(
                user_message=user_msg,
                assistant_response=assistant_msg,
                llm_analyzer=llm_analyzer,
                max_length=40,
            )
            print(f"LLM 生成:  {llm_title}")
        else:
            print(f"LLM 生成:  (未启用)")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_llm_title_generation())
