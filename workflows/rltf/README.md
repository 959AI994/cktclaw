# RLTF (Reinforcement Learning from Tool Feedback)

基于工具反馈的强化学习综合序列优化模块。

## 📖 简介

RLTF 是 CktClaw 的创新自进化特性之一，使用强化学习自动探索和优化 ABC 逻辑综合序列。系统通过 LLM 生成候选序列，ABC/OpenSTA 执行并返回 PPA (Power, Performance, Area) 指标作为 Reward，驱动下一轮探索。

## 🎯 核心特性

- **自动序列生成**: 使用 LLM (DeepSeek) 生成 ABC 优化序列
- **强化学习**: 基于 PPA 指标计算 Reward，指导探索方向
- **多目标优化**: 同时优化面积 (Area) 和延迟 (Delay)
- **收敛检测**: 自动检测优化收敛，避免无效迭代
- **状态持久化**: 支持检查点保存和会话恢复
- **完全解耦**: 可热插拔，不影响核心系统

## 🚀 快速开始

### 基本用法

```bash
# 在 CktClaw CLI 中
> /rltf test.aig 50

# 参数说明:
# - test.aig: AIG 文件路径
# - 50: 最大迭代次数 (可选，默认 50)
```

### 通过 AI 对话调用

```bash
> 请使用 RLTF 优化 test.aig，最多 100 次迭代
```

## 📊 工作流程

```
1. 初始化
   ├─ 验证 AIG 文件
   ├─ 获取初始 PPA 指标
   └─ 创建会话

2. RL 循环 (最多 N 次迭代)
   ├─ LLM 生成 ABC 序列
   ├─ 执行 ABC 优化
   ├─ 执行 OpenSTA 时序分析 (可选)
   ├─ 提取 PPA 指标
   ├─ 计算 Reward
   ├─ 更新最佳结果
   └─ 检查收敛

3. 完成
   ├─ 保存最终状态
   ├─ 生成优化报告
   └─ 返回最佳序列
```

## 📁 架构设计

### 目录结构

```
workflows/rltf/
├── __init__.py              # 模块初始化
├── types.py                 # 类型定义
├── state.py                 # 状态管理器
├── reward.py                # Reward 计算器
├── sequence_generator.py    # LLM 序列生成器
├── executor.py              # ABC/OpenSTA 执行器
├── persistence.py           # 持久化管理器
└── coordinator.py           # 主协调器

skills/
└── rltf_skill.py           # Skill 入口
```

### 核心组件

| 组件 | 职责 |
|------|------|
| **RLTFCoordinator** | 主协调器，管理整个 RL 循环 |
| **RLTFStateManager** | 状态管理，跟踪迭代历史 |
| **RLTFRewardCalculator** | Reward 计算，支持多目标优化 |
| **RLTFSequenceGenerator** | LLM 序列生成，基于历史反馈 |
| **RLTFExecutor** | ABC/OpenSTA 执行，提取 PPA 指标 |
| **RLTFPersistence** | 持久化，支持检查点和恢复 |

## 🔧 配置选项

```python
RLTFConfig(
    aig_file_path="test.aig",      # AIG 文件路径
    max_iterations=50,              # 最大迭代次数
    convergence_threshold=0.01,     # 收敛阈值
    target_area=None,               # 目标面积 (可选)
    target_delay=None,              # 目标延迟 (可选)
    llm_model="deepseek-chat",     # LLM 模型
    temperature=0.7,                # LLM 温度
    abc_timeout=30,                 # ABC 超时 (秒)
    sta_timeout=60,                 # OpenSTA 超时 (秒)
    enable_checkpoints=True,        # 启用检查点
    checkpoint_interval=10,         # 检查点间隔
)
```

## 📈 输出示例

```
📊 获取初始 PPA 指标...
   Area: 1000, Delay: 5.2000 ns

🚀 开始 RLTF 优化 (最大迭代: 50)
============================================================
✅ Iter   1 | Reward: +0.1234 | Area:  950 | Delay: 4.9000 | Seq: strash; balance; rewrite...
   Iter   2 | Reward: +0.0856 | Area:  980 | Delay: 5.0000 | Seq: strash; rewrite; refactor...
✅ Iter   3 | Reward: +0.1567 | Area:  920 | Delay: 4.7000 | Seq: strash; balance; rewrite; refactor...
...
💾 检查点已保存: checkpoint_0010.json
...
✅ 检测到收敛 (方差 < 0.01)

============================================================
🎉 RLTF 优化完成

📈 统计信息:
   总迭代次数: 35
   成功次数: 34
   失败次数: 1
   成功率: 97.1%
   平均 Reward: 0.1123
   最佳 Reward: 0.1567

🎯 最终改进:
   Area: +8.00%
   Delay: +9.62%

🏆 最佳序列:
   strash; balance; rewrite; refactor

💾 会话数据已保存到: data/rltf_sessions/rltf_a1b2c3d4e5f6/
```

## 💾 数据持久化

### 会话数据结构

```
data/rltf_sessions/
└── rltf_<session_id>/
    ├── checkpoint_0010.json    # 检查点 (每 10 次迭代)
    ├── checkpoint_0020.json
    ├── state.json              # 最终状态
    └── result.json             # 最终结果
```

### 恢复会话

```python
# 通过 Python API
coordinator = RLTFCoordinator()
result = await coordinator.resume("rltf_a1b2c3d4e5f6")
```

## 🧪 测试

```bash
# 运行单元测试
pytest workflows/rltf/tests/

# 运行集成测试
pytest workflows/rltf/tests/test_integration.py

# 端到端测试
python -m cktclaw.workflows.rltf.tests.test_e2e
```

## 🔍 调试

### 启用详细日志

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 查看会话信息

```python
from cktclaw.workflows.rltf import RLTFPersistence

persistence = RLTFPersistence()
sessions = persistence.list_sessions()
info = persistence.get_session_info("rltf_a1b2c3d4e5f6")
```

## 📚 API 参考

### RLTFCoordinator

```python
coordinator = RLTFCoordinator()

# 运行优化
result = await coordinator.run(config)

# 暂停优化
await coordinator.pause()

# 恢复优化
result = await coordinator.resume(session_id)
```

### RLTFRewardCalculator

```python
calculator = RLTFRewardCalculator(
    area_weight=0.4,
    delay_weight=0.4,
    power_weight=0.2
)

# 计算 Reward
reward = calculator.calculate(current, baseline, config)

# 判断 Pareto 支配
is_dominated = calculator.is_dominated(metrics_a, metrics_b)
```

## 🤝 贡献

RLTF 是 CktClaw 创新特性的一部分，欢迎贡献！

## 📄 许可证

MIT License

## 🔗 相关资源

- [CktClaw 主项目](../../README.md)
- [架构设计文档](../../docs/RLTF_DESIGN.md)
- [ABC 文档](https://people.eecs.berkeley.edu/~alanmi/abc/)
- [OpenSTA 文档](https://github.com/The-OpenROAD-Project/OpenSTA)

---

**版本**: 0.1.0
**作者**: AI4EDA 创新架构师
**最后更新**: 2026-04-12
