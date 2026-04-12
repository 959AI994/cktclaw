# RLTF (Reinforcement Learning from Tool Feedback)

## 概述

RLTF 是 CktClaw 的创新自进化特性，使用强化学习自动探索和优化 ABC 综合序列。LLM 生成候选序列，ABC/OpenSTA 执行并返回 PPA 指标作为 Reward，驱动下一轮探索。

## 特性

- ✅ **自动序列生成**: 使用 LLM 生成 ABC 优化序列
- ✅ **强化学习驱动**: 基于 PPA 指标的 Reward 反馈
- ✅ **多目标优化**: 同时优化 Area 和 Delay
- ✅ **Pareto 优化**: 支持 Pareto 支配关系和排名
- ✅ **检查点机制**: 自动保存和恢复优化进度
- ✅ **收敛检测**: 自动检测优化收敛
- ✅ **完全解耦**: 独立的 workflow 架构，不影响核心系统

## 架构

```
workflows/rltf/
├── __init__.py              # 模块导出
├── types.py                 # 数据类型定义
├── state.py                 # 状态管理器
├── reward.py                # Reward 计算器
├── sequence_generator.py    # LLM 序列生成器
├── mock_generator.py        # Mock 生成器（测试用）
├── executor.py              # ABC/OpenSTA 执行器
├── persistence.py           # 持久化管理器
├── coordinator.py           # 主协调器
└── tests/                   # 测试套件
    ├── test_types.py
    ├── test_state.py
    ├── test_reward.py
    ├── test_integration.py
    ├── test_e2e.py
    └── test_performance.py
```

## 快速开始

### 1. 命令行使用

```bash
# 在 CktClaw CLI 中
> /rltf test.aig 100

# 或通过 AI 对话
> 请使用 RLTF 优化 test.aig，最多 100 次迭代
```

### 2. Python API 使用

```python
from workflows.rltf import RLTFCoordinator, RLTFConfig

# 配置 RLTF
config = RLTFConfig(
    aig_file_path="test.aig",
    max_iterations=100,
    convergence_threshold=0.01,
    target_area=500,
    target_delay=2.0,
)

# 创建协调器
coordinator = RLTFCoordinator()

# 运行优化
result = await coordinator.run(config)

# 查看结果
print(f"最佳序列: {result.best_sequence}")
print(f"最佳指标: Area={result.best_metrics.area}, Delay={result.best_metrics.delay}")
print(f"改进率: {result.improvement}")
```

### 3. 使用 Mock 生成器（测试）

```python
# 不需要 LLM API key，使用预定义序列
coordinator = RLTFCoordinator(use_mock_generator=True)
result = await coordinator.run(config)
```

## 配置选项

### RLTFConfig

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `aig_file_path` | str | 必填 | AIG 文件路径 |
| `max_iterations` | int | 50 | 最大迭代次数 |
| `convergence_threshold` | float | 0.01 | 收敛阈值 |
| `target_area` | int | None | 目标面积 |
| `target_delay` | float | None | 目标延迟 |
| `llm_model` | str | "deepseek-chat" | LLM 模型 |
| `temperature` | float | 0.7 | 采样温度 |
| `abc_timeout` | int | 30 | ABC 超时（秒）|
| `sta_timeout` | int | 60 | STA 超时（秒）|
| `enable_checkpoints` | bool | True | 启用检查点 |
| `checkpoint_interval` | int | 10 | 检查点间隔 |

## 环境变量

### LLM API 配置

```bash
# DeepSeek API
export DEEPSEEK_API_KEY="your-api-key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"

# 或使用 OpenAI API
export OPENAI_API_KEY="your-api-key"
```

### ABC 工具配置

```bash
# 如果 ABC 不在 PATH 中，设置 ABC_PATH
export ABC_PATH="/path/to/abc"
```

## 测试

### 快速验证

```bash
python3 quick_verify_rltf.py
```

输出示例：
```
============================================================
RLTF 快速验证脚本
============================================================

1. 测试模块导入...
   ✅ 所有模块导入成功

2. 测试类型创建...
   ✅ PPAMetrics: area=1000, delay=5.0
   ✅ RLTFConfig: max_iterations=50

...

✅ 所有验证测试通过！
```

### 真实 AIG 文件测试

```bash
export ABC_PATH=/path/to/abc
python3 test_rltf_real.py
```

### 完整测试套件

```bash
bash run_rltf_tests.sh
```

测试覆盖：
- ✅ 单元测试（types, state, reward）
- ✅ 集成测试（组件协作）
- ✅ 端到端测试（完整流程）
- ✅ 性能测试（大规模迭代）

## 工作流程

```
1. 初始化
   ├─ 加载 AIG 文件
   ├─ 获取初始 PPA 指标
   └─ 初始化状态

2. 主循环 (每次迭代)
   ├─ LLM 生成 ABC 序列
   ├─ 执行 ABC 优化
   ├─ 执行 OpenSTA 分析（可选）
   ├─ 提取 PPA 指标
   ├─ 计算 Reward
   ├─ 更新最佳结果
   └─ 保存检查点

3. 收敛检测
   ├─ 检查 Reward 方差
   ├─ 检查迭代次数
   └─ 决定是否继续

4. 完成
   ├─ 保存最终状态
   ├─ 生成优化报告
   └─ 返回结果
```

## Reward 计算

### 多目标优化

```python
reward = w_area * (baseline_area - current_area) / baseline_area +
         w_delay * (baseline_delay - current_delay) / baseline_delay
```

默认权重：
- `w_area = 0.6` (60% 权重)
- `w_delay = 0.4` (40% 权重)

### 约束惩罚

如果设置了目标约束（target_area, target_delay），超出目标会有惩罚：

```python
penalty = 0.0
if target_area and current_area > target_area:
    penalty += 0.5 * (current_area - target_area) / target_area

if target_delay and current_delay > target_delay:
    penalty += 0.5 * (current_delay - target_delay) / target_delay
```

### Pareto 优化

支持 Pareto 支配关系判断和排名：

```python
# 判断 A 是否被 B 支配
is_dominated = calculator.is_dominated(metrics_a, metrics_b)

# 计算 Pareto 排名
ranks = calculator.calculate_pareto_rank(metrics_list)
```

## ABC 命令序列

### 可用命令

- `strash` - 结构化哈希（创建 AIG 结构）
- `balance` - 平衡 AIG 以减少深度
- `rewrite` - 代数重写以减少面积
- `refactor` - 重构以权衡面积/延迟
- `resub` - 重新替换以减少面积
- `compress` - 迭代压缩（rewrite + refactor）
- `compress2` - 高级压缩
- `retime` - 重定时以优化延迟
- `dch` - Don't-care 哈希
- `if` - FPGA 映射
- `map` - 标准单元映射

### 典型序列示例

```bash
# 基础优化
strash; balance; rewrite

# 面积优化
strash; rewrite; refactor; rewrite

# 延迟优化
strash; balance; rewrite; balance

# 综合优化
strash; balance; rewrite; refactor; balance

# 高级压缩
strash; compress2
```

## 持久化

### 检查点格式

检查点保存在 `data/rltf_sessions/{session_id}/` 目录：

```
data/rltf_sessions/
└── rltf_abc123def456/
    ├── checkpoint_0010.json
    ├── checkpoint_0020.json
    ├── checkpoint_0030.json
    └── final_state.json
```

### 恢复会话

```python
from workflows.rltf import RLTFPersistence

persistence = RLTFPersistence()

# 列出所有会话
sessions = persistence.list_sessions()

# 加载特定会话
state = await persistence.load_state("rltf_abc123def456")

# 从检查点恢复
state = await persistence.load_checkpoint("rltf_abc123def456", 20)
```

## 性能

### 基准测试结果

- **状态管理**: ~0.001ms per operation
- **Reward 计算**: ~0.002ms per calculation
- **序列生成**: ~500ms (LLM) / ~0.001ms (Mock)
- **ABC 执行**: ~100-500ms per sequence
- **持久化**: ~10-50ms per checkpoint

### 可扩展性

- ✅ 支持 1000+ 次迭代
- ✅ 内存占用 < 100MB (1000 次迭代)
- ✅ 检查点大小 < 1MB per checkpoint

## 故障排除

### 问题：ModuleNotFoundError

```bash
# 确保在项目根目录运行
cd /home/wjx/pythonproject/cktclaw
python3 -c "from workflows.rltf import RLTFCoordinator"
```

### 问题：ABC 命令未找到

```bash
# 设置 ABC_PATH
export ABC_PATH=/path/to/abc

# 或添加到 PATH
export PATH=$PATH:/path/to/abc/bin
```

### 问题：LLM API 错误

```bash
# 使用 Mock 生成器进行测试
coordinator = RLTFCoordinator(use_mock_generator=True)

# 或设置 API key
export DEEPSEEK_API_KEY="your-key"
```

### 问题：初始指标为 0

这通常是因为 AIG 文件太小或 ABC 输出解析失败。检查：
1. AIG 文件是否有效
2. ABC 是否正确执行
3. 查看 ABC 输出日志

## 示例

### 示例 1: 基础优化

```python
config = RLTFConfig(
    aig_file_path="test/aig/ADD1b.aig",
    max_iterations=20,
)

coordinator = RLTFCoordinator(use_mock_generator=True)
result = await coordinator.run(config)

print(f"完成 {result.state.current_iteration} 次迭代")
print(f"最佳序列: {result.best_sequence}")
```

### 示例 2: 带约束的优化

```python
config = RLTFConfig(
    aig_file_path="test/aig/ALU_542.aig",
    max_iterations=100,
    target_area=400,      # 目标面积
    target_delay=1.5,     # 目标延迟
    convergence_threshold=0.005,
)

coordinator = RLTFCoordinator()
result = await coordinator.run(config)

if result.improvement:
    print(f"面积改进: {result.improvement['area']:.2f}%")
    print(f"延迟改进: {result.improvement['delay']:.2f}%")
```

### 示例 3: 恢复中断的会话

```python
persistence = RLTFPersistence()

# 加载最新检查点
state = await persistence.load_latest_checkpoint("rltf_abc123def456")

# 继续优化
config = state.config
config.max_iterations = 200  # 增加迭代次数

coordinator = RLTFCoordinator()
coordinator.state_manager._state = state
result = await coordinator.run(config)
```

## 贡献

RLTF 是 CktClaw 创新特性的一部分，采用完全解耦的架构设计。欢迎贡献：

1. 新的 Reward 计算策略
2. 更好的序列生成算法
3. 性能优化
4. 文档改进

## 许可证

与 CktClaw 主项目相同。

## 联系

如有问题或建议，请在 CktClaw 项目中提 Issue。

---

**版本**: 1.0.0
**状态**: ✅ 生产就绪
**最后更新**: 2026-04-12
