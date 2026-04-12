#!/bin/bash
# RLTF 测试运行脚本

set -e

echo "=========================================="
echo "RLTF 测试套件"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="/home/wjx/pythonproject/cktclaw"
cd "$PROJECT_ROOT"

# 检查依赖
echo -e "${YELLOW}检查测试依赖...${NC}"
python3 -c "import pytest" 2>/dev/null || {
    echo -e "${RED}pytest 未安装，正在安装...${NC}"
    pip install pytest pytest-asyncio psutil
}

echo -e "${GREEN}✓ 依赖检查完成${NC}"
echo ""

# 运行测试的函数
run_tests() {
    local test_type=$1
    local test_path=$2
    local description=$3

    echo "=========================================="
    echo -e "${YELLOW}运行 ${description}${NC}"
    echo "=========================================="

    if pytest "$test_path" -v --tb=short; then
        echo -e "${GREEN}✓ ${description} 通过${NC}"
        return 0
    else
        echo -e "${RED}✗ ${description} 失败${NC}"
        return 1
    fi
}

# 测试计数器
total_tests=0
passed_tests=0
failed_tests=0

# 1. 单元测试
echo ""
if run_tests "unit" "workflows/rltf/tests/test_types.py" "类型定义测试"; then
    ((passed_tests++))
else
    ((failed_tests++))
fi
((total_tests++))

echo ""
if run_tests "unit" "workflows/rltf/tests/test_state.py" "状态管理器测试"; then
    ((passed_tests++))
else
    ((failed_tests++))
fi
((total_tests++))

echo ""
if run_tests "unit" "workflows/rltf/tests/test_reward.py" "Reward 计算器测试"; then
    ((passed_tests++))
else
    ((failed_tests++))
fi
((total_tests++))

# 2. 集成测试
echo ""
if run_tests "integration" "workflows/rltf/tests/test_integration.py" "集成测试"; then
    ((passed_tests++))
else
    ((failed_tests++))
fi
((total_tests++))

# 3. 端到端测试
echo ""
if run_tests "e2e" "workflows/rltf/tests/test_e2e.py" "端到端测试"; then
    ((passed_tests++))
else
    ((failed_tests++))
fi
((total_tests++))

# 4. 性能测试
echo ""
if run_tests "performance" "workflows/rltf/tests/test_performance.py" "性能测试"; then
    ((passed_tests++))
else
    ((failed_tests++))
fi
((total_tests++))

# 总结
echo ""
echo "=========================================="
echo "测试总结"
echo "=========================================="
echo -e "总测试套件: ${total_tests}"
echo -e "${GREEN}通过: ${passed_tests}${NC}"
echo -e "${RED}失败: ${failed_tests}${NC}"
echo ""

if [ $failed_tests -eq 0 ]; then
    echo -e "${GREEN}🎉 所有测试通过！${NC}"
    exit 0
else
    echo -e "${RED}❌ 有测试失败${NC}"
    exit 1
fi
