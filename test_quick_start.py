"""
快速启动测试 - 验证 CktClaw 基本功能
"""

import sys
sys.path.insert(0, '/home/wjx/pythonproject')

print("="*70)
print("🚀 CktClaw 快速启动测试")
print("="*70)
print()

# 1. 测试导入
print("1️⃣ 测试核心导入")
try:
    from cktclaw.main import CLIState
    from cktclaw.handlers.chat_handler_v2 import process_chat_v2
    from cktclaw.harness import (
        get_state_manager,
        get_task_manager,
        get_skill_registry,
        get_coordinator_manager,
    )
    print("   ✅ 所有核心模块导入成功")
except Exception as e:
    print(f"   ❌ 导入失败: {e}")
    sys.exit(1)

# 2. 测试 CLIState 初始化
print()
print("2️⃣ 测试 CLIState 初始化")
try:
    state = CLIState()
    print(f"   ✅ CLIState 初始化成功")
    print(f"      - Session ID: {state.session_id[:8]}")
    print(f"      - Storage: {'已初始化' if state.storage else '未初始化'}")
    print(f"      - ContextManager: {'已初始化' if state.context_manager else '未初始化'}")
except Exception as e:
    print(f"   ❌ 初始化失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 3. 测试 Harness 管理器
print()
print("3️⃣ 测试 Harness 管理器")
try:
    state_manager = get_state_manager()
    task_manager = get_task_manager()
    skill_registry = get_skill_registry()
    coordinator = get_coordinator_manager()
    print("   ✅ 所有 Harness 管理器初始化成功")
except Exception as e:
    print(f"   ❌ Harness 管理器失败: {e}")
    sys.exit(1)

print()
print("="*70)
print("✅ CktClaw 快速启动测试通过")
print("="*70)
print()
print("🎯 系统状态: 正常")
print("🚀 CktClaw 可以正常启动！")
print()
