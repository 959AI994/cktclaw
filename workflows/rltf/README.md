# RLTF（Reinforcement Learning from Tool Feedback）

基于 **工具反馈（PPA 指标）** 的强化式探索：用 LLM 生成 ABC 优化序列，经 ABC / OpenSTA 执行得到面积、延迟、功耗等信号，计算 Reward 并驱动下一轮序列搜索。模块位于 `workflows/rltf/`，通过 Skill `/rltf` 接入 CktClaw，与核心对话链路解耦。

---

## 功能概览

| 能力 | 说明 |
|------|------|
| 序列生成 | LLM（默认 DeepSeek）根据历史反馈生成 ABC 命令串；测试可用 `mock_generator` |
| 强化式探索 | 以相对基线的 PPA 改进为 Reward，迭代更新最优序列 |
| 多目标 | 面积、延迟、功耗加权（默认权重见下文 Reward 节） |
| Pareto / 约束 | 支配关系判断、目标超界惩罚（与 `RLTFConfig` 中 target 字段配合） |
| 收敛 | 基于 Reward 方差等条件提前结束 |
| 持久化 | `checkpoint_*.json`、`state.json`、`result.json`；支持从检查点恢复继续跑 |
| 工程 | 异步协调器、超时、检查点清理、进度输出 |

---

## 目录与组件

```
workflows/rltf/
├── __init__.py              # 导出公共 API
├── types.py                 # 状态、配置、PPA、结果等数据类型
├── state.py                 # 状态机与迭代历史
├── reward.py                # Reward、Pareto、惩罚项
├── sequence_generator.py    # LLM 序列生成与校验
├── mock_generator.py        # 无 API Key 时的序列源（测试）
├── executor.py              # ABC / OpenSTA 调用与指标解析
├── persistence.py           # 检查点、会话目录、结果 JSON
├── coordinator.py           # 主循环、收敛、暂停/恢复
├── README.md                # 本文档（已合并原 RLTF_README / RLTF_COMPLETION_REPORT）
└── tests/                   # 单元 / 集成 / e2e / 性能等
    ├── test_types.py
    ├── test_state.py
    ├── test_reward.py
    ├── test_integration.py
    ├── test_e2e.py
    └── test_performance.py

skills/rltf_skill.py          # CLI 与对话侧入口
```

| 组件 | 职责 |
|------|------|
| `RLTFCoordinator` | 校验 AIG、驱动循环、收敛、暂停/恢复、汇总报告 |
| `RLTFStateManager` | 当前轮次、历史、最优解、统计 |
| `RLTFRewardCalculator` | 加权 Reward、约束惩罚、Pareto 辅助 |
| `RLTFSequenceGenerator` | 调用 LLM、解析命令、失败回退 |
| `RLTFExecutor` | 落地 ABC/OpenSTA、抽取 PPA |
| `RLTFPersistence` | 会话目录、检查点读写、`list_sessions` 等 |

**集成方式**：业务代码集中在 `workflows/rltf/`；对外主要通过 `skills/rltf_skill.py` 与 `main.py` 中的技能注册接入（保持核心 handler 尽量不动）。

---

## 快速开始

### CLI（CktClaw 内）

```bash
> /rltf path/to/design.aig 50
# 第二个参数为最大迭代次数，可选，默认视配置而定

# 自然语言等价示例
> 请使用 RLTF 优化 test.aig，最多 100 次迭代
```

### Python API

在项目根目录下，保证 `workflows` 在 `PYTHONPATH` 中（或已安装包体），例如：

```python
from workflows.rltf import RLTFCoordinator, RLTFConfig

config = RLTFConfig(
    aig_file_path="test.aig",
    max_iterations=100,
    convergence_threshold=0.01,
    target_area=500,      # 可选
    target_delay=2.0,     # 可选
)

coordinator = RLTFCoordinator()
result = await coordinator.run(config)

print(result.best_sequence)
print(result.best_metrics.area, result.best_metrics.delay)
```

### 无 LLM Key 的冒烟 / 测试

```python
coordinator = RLTFCoordinator(use_mock_generator=True)
result = await coordinator.run(config)
```

---

## 配置项（`RLTFConfig`）

| 字段 | 类型 | 默认 / 说明 |
|------|------|-------------|
| `aig_file_path` | `str` | 必填，AIG 路径 |
| `max_iterations` | `int` | 最大迭代轮数 |
| `convergence_threshold` | `float` | 收敛判定（与实现内方差逻辑配合） |
| `target_area` / `target_delay` | 可选 | 超界触发惩罚项 |
| `llm_model` | `str` | 如 `deepseek-chat` |
| `temperature` | `float` | 采样温度 |
| `abc_timeout` / `sta_timeout` | `int` | 秒级超时 |
| `enable_checkpoints` | `bool` | 是否写检查点 |
| `checkpoint_interval` | `int` | 每隔多少轮写一次 |

更细字段以 `workflows/rltf/types.py` 中 `RLTFConfig` 定义为准。

---

## 环境变量

```bash
# LLM（DeepSeek 示例）
export DEEPSEEK_API_KEY="your-api-key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"

# 或使用 OpenAI 兼容端点
export OPENAI_API_KEY="your-api-key"

# ABC 不在 PATH 时
export ABC_PATH="/path/to/abc"
```

---

## 工作流程（摘要）

1. **初始化**：校验 AIG、测基线 PPA、初始化 `RLTFState`。  
2. **迭代**：生成序列 → ABC（及可选 STA）→ 解析 PPA → Reward → 更新最优 → 按需写检查点。  
3. **收敛或达上限**：写 `state.json` / `result.json`，打印统计与最佳序列。  
4. **恢复**：`load_checkpoint(session_id)`（`iteration=None` 时取最新）后由 `RLTFCoordinator.resume` 继续 `run`。

---

## Reward 与权重（与代码一致）

`RLTFRewardCalculator` 默认归一化权重：**面积 0.4、延迟 0.4、功耗 0.2**（构造时传入的权重会再归一化到和为 1）。在相对基线的改进率基础上，可按配置加入 **目标超界惩罚**；并提供 **Pareto 支配** 等辅助方法供扩展策略使用。

---

## ABC 命令备忘（常用）

典型子命令包括：`strash`、`balance`、`rewrite`、`refactor`、`resub`、`compress` / `compress2`、`retime`、`dch` 等。具体合法组合以 ABC 版本与生成器约束为准；LLM 输出会经解析与基本校验。

示例串（仅作格式参考）：

```text
strash; balance; rewrite; refactor
```

---

## 持久化布局

根目录默认在 `data/rltf_sessions/<session_id>/`：

```
data/rltf_sessions/
└── rltf_<id>/
    ├── checkpoint_0010.json   # 每 checkpoint_interval 轮次等策略写入
    ├── checkpoint_0020.json
    ├── state.json               # 最新状态快照
    └── result.json              # 最终结果（结构化导出）
```

列出会话、读取元信息：

```python
from workflows.rltf import RLTFPersistence

persistence = RLTFPersistence()
sessions = persistence.list_sessions()
info = persistence.get_session_info("rltf_xxx")
```

从检查点恢复并由协调器继续：

```python
coordinator = RLTFCoordinator()
result = await coordinator.resume("rltf_xxx")
```

（`resume` 内部会 `load_checkpoint(session_id)` 后基于已有 `config` 再次 `run`。）

---

## 测试与验证

```bash
# 项目根目录：快速导入与类型冒烟
python3 quick_verify_rltf.py

# 指定 ABC 路径后跑真实 AIG（若存在该脚本）
export ABC_PATH=/path/to/abc
python3 test_rltf_real.py

# 工作流测试套件
pytest workflows/rltf/tests/
# 或
bash run_rltf_tests.sh
```

---

## 调试与排错

- **详细日志**：`import logging; logging.basicConfig(level=logging.DEBUG)`  
- **`ModuleNotFoundError`**：在仓库根执行，并确认 `from workflows.rltf import RLTFCoordinator` 能解析。  
- **找不到 ABC**：设置 `ABC_PATH` 或把 `abc` 加入 `PATH`。  
- **LLM 报错**：临时使用 `RLTFCoordinator(use_mock_generator=True)` 验证管线。  
- **初始 PPA 为 0 或异常**：检查 AIG 是否有效、ABC 输出是否被正确解析、超时是否过短。

---

## 协调器 API 摘要

```python
coordinator = RLTFCoordinator(use_mock_generator=False)

result = await coordinator.run(config)
await coordinator.pause()
result = await coordinator.resume(session_id)
```

`RLTFRewardCalculator` 可独立使用，用于实验权重或支配判定：

```python
from workflows.rltf import RLTFRewardCalculator

calculator = RLTFRewardCalculator(area_weight=0.4, delay_weight=0.4, power_weight=0.2)
reward = calculator.calculate(current_metrics, baseline_metrics, config)
```

---

## 实现状态说明（原完成报告摘要）

- **交付物**：上述 Python 模块 + `skills/rltf_skill.py` + 测试目录；设计上保持 workflow 与核心解耦。  
- **质量**：类型标注与分层清晰；**测试与覆盖率**应随 `workflows/rltf/tests/` 与 CI 持续加强（以仓库当前状态为准）。  
- **版本**：包内 `__version__` 见 `workflows/rltf/__init__.py`（当前为 **0.1.0**）。  
- **后续方向**（非承诺路线图）：更强测试矩阵、真实设计库基准、Data Flywheel / 多智能体等上层创新与文档联动见 `innovation_todo.md` 等。

---

## 输出示例（控制台）

```text
获取初始 PPA ...
开始 RLTF，最大迭代: 50
Iter   1 | Reward: +0.12 | Area: 950 | Delay: 4.9 | Seq: strash; balance; ...
...
检查点已保存: checkpoint_0010.json
收敛提前结束

总迭代 / 成功 / 失败、平均与最佳 Reward、相对基线的 Area/Delay 改进百分比
最佳 ABC 序列: ...
会话目录: data/rltf_sessions/rltf_<id>/
```

---

## 相关链接

- [CktClaw 主 README](../../README.md)  
- [ABC](https://people.eecs.berkeley.edu/~alanmi/abc/)  
- [OpenSTA](https://github.com/The-OpenROAD-Project/OpenSTA)  
- 顶层设计类文档若存在：`docs/RLTF_DESIGN.md`（以仓库实际文件为准）

---

## 许可证

与 CktClaw 主项目一致（如主仓库为 MIT，则此处同为 MIT）。

---

**文档说明**：本文档已合并原 `RLTF_README.md` 与 `RLTF_COMPLETION_REPORT.md` 中与用户相关的技术内容，去掉重复段落并以当前代码与目录为准做了校正（例如持久化文件名、默认 Reward 权重、测试脚本路径）。维护时请仅更新本 `README.md`。

**最后更新**：2026-04-12
