"""
测试 CktMem 2.0 与 ContextManager 的集成

验证文件系统记忆是否正确加载到上下文中
"""

import sys
import asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cktmem import ContextManager, Storage, CompactConfig


async def test_integration():
    """测试 CktMem 2.0 集成"""

    print("=" * 70)
    print("CktMem 2.0 集成测试")
    print("=" * 70)

    # 1. 初始化存储和上下文管理器
    import tempfile
    import os

    # 使用临时文件作为数据库
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()

    storage = Storage(db_path=temp_db.name)

    system_prompt = "You are CktClaw, an AI assistant for circuit analysis."

    context_manager = ContextManager(
        storage=storage,
        system_prompt=system_prompt,
        config=CompactConfig(),
        project_root=str(PROJECT_ROOT),  # 传入项目根目录
    )

    print("\n✓ ContextManager 已初始化")
    print(f"  项目根目录: {PROJECT_ROOT}")

    # 2. 创建测试会话
    import uuid
    session_id = str(uuid.uuid4())[:8]
    await storage.create_session(
        session_id=session_id,
        project_name="test_project",
        model_choice="logicrt",
    )

    print(f"✓ 测试会话已创建: {session_id}")

    # 3. 构建上下文
    user_message = "请分析这个电路的功能"

    messages = await context_manager.build_context(
        session_id=session_id,
        user_message=user_message,
        auto_compact=False,  # 禁用自动压缩
    )

    print(f"\n✓ 上下文已构建，共 {len(messages)} 条消息")

    # 4. 检查文件系统记忆是否加载
    filesystem_memory_found = False

    for i, msg in enumerate(messages):
        print(f"\n消息 {i + 1}:")
        print(f"  角色: {msg.role}")
        print(f"  层级: {msg.layer}")
        print(f"  类型: {msg.msg_type}")

        if msg.metadata and msg.metadata.get("type") == "filesystem_memory":
            filesystem_memory_found = True
            print(f"  ✓ 找到文件系统记忆！")
            print(f"  内容长度: {len(msg.content)} 字符")
            print(f"  内容预览 (前 200 字符):")
            print(f"  {msg.content[:200]}...")
        else:
            print(f"  内容预览: {msg.content[:100]}...")

    # 5. 验证结果
    print("\n" + "=" * 70)
    print("验证结果")
    print("=" * 70)

    if filesystem_memory_found:
        print("✓ 文件系统记忆已成功加载到上下文中")
        print("✓ CktMem 2.0 集成成功！")
    else:
        print("✗ 未找到文件系统记忆")
        print("  可能原因：")
        print("  1. 记忆目录不存在")
        print("  2. MEMORY.md 文件不存在")
        print("  3. 记忆系统被禁用")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(test_integration())
