#!/bin/bash
# CktClaw 优化验证脚本

echo "=========================================="
echo "CktClaw 优化验证测试"
echo "=========================================="
echo ""

# Test 1: Config loading
echo "✓ Test 1: 配置加载测试"
python -c "
import config
print('  - AI4EDA_TOOLKIT_PATH:', config.AI4EDA_TOOLKIT_PATH)
print('  - LOCAL_CHAT_MODEL:', config.LOCAL_CHAT_MODEL if config.LOCAL_CHAT_MODEL else '(未设置)')
print('  - CODEV_PATH:', config.CODEV_PATH)
"
echo ""

# Test 2: Environment variable override
echo "✓ Test 2: 环境变量覆盖测试"
CKTCLAW_LOCAL_MODEL=Qwen/Qwen3.5-2B python -c "
import config
print('  - LOCAL_CHAT_MODEL:', config.LOCAL_CHAT_MODEL)
print('  - CODEV_PATH:', config.CODEV_PATH)
"
echo ""

# Test 3: AI4EDA path override
echo "✓ Test 3: AI4EDA 路径覆盖测试"
CKTCLAW_AI4EDA_PATH=/custom/path/ai4eda python -c "
import config
print('  - AI4EDA_TOOLKIT_PATH:', config.AI4EDA_TOOLKIT_PATH)
"
echo ""

# Test 4: Python syntax check
echo "✓ Test 4: Python 语法检查"
python -m py_compile handlers/chat_handler_v2.py 2>&1 && echo "  - chat_handler_v2.py: OK"
python -m py_compile harness/query/query_loop_enhanced.py 2>&1 && echo "  - query_loop_enhanced.py: OK"
python -m py_compile config.py 2>&1 && echo "  - config.py: OK"
python -m py_compile handlers/ai4eda_handler.py 2>&1 && echo "  - ai4eda_handler.py: OK"
python -m py_compile orchestrator/engine.py 2>&1 && echo "  - engine.py: OK"
echo ""

# Test 5: Check debug output removed
echo "✓ Test 5: Debug 输出删除检查"
if grep -q "🔍 LLM Response" handlers/chat_handler_v2.py; then
    echo "  - ✗ Debug 输出仍然存在"
else
    echo "  - ✓ Debug 输出已删除"
fi
echo ""

# Test 6: Check tool deduplication added
echo "✓ Test 6: 工具去重逻辑检查"
if grep -q "called_tool_signatures" harness/query/query_loop_enhanced.py; then
    echo "  - ✓ 工具去重字段已添加"
else
    echo "  - ✗ 工具去重字段未找到"
fi

if grep -q "_filter_duplicate_tools" harness/query/query_loop_enhanced.py; then
    echo "  - ✓ 工具去重方法已添加"
else
    echo "  - ✗ 工具去重方法未找到"
fi
echo ""

# Test 7: Check orchestrator confirmation added
echo "✓ Test 7: Workflow 需求确认检查"
if grep -q "Interactive requirement gathering" orchestrator/engine.py; then
    echo "  - ✓ 需求确认逻辑已添加"
else
    echo "  - ✗ 需求确认逻辑未找到"
fi
echo ""

# Test 8: Check improve.md exists
echo "✓ Test 8: 进度文档检查"
if [ -f "todo/improve.md" ]; then
    echo "  - ✓ improve.md 已创建"
    echo "  - 文件大小: $(wc -l < todo/improve.md) 行"
else
    echo "  - ✗ improve.md 未找到"
fi
echo ""

echo "=========================================="
echo "所有测试完成！"
echo "=========================================="
