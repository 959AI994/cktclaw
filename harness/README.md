# Harness Engineering

CktClaw 的核心架构模块

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│ Query (中枢循环)                                         │
│ - Tool-Result 配对与自愈                                 │
│ - 自动压缩触发                                           │
│ - 状态机转换                                             │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Coordinator (调度隔离)                                   │
│ - 模式管理 (Coordinator/Normal)                          │
│ - Worker 调度                                            │
│ - 通知解析                                               │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Skills (技能资产化)                                      │
│ - 技能注册与发现                                         │
│ - 别名系统                                               │
│ - 条件激活                                               │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Tasks (任务状态机)                                       │
│ - 任务生命周期管理                                       │
│ - 输出持久化                                             │
│ - 清理机制                                               │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Bootstrap (根状态)                                       │
│ - 全局状态管理                                           │
│ - 会话管理                                               │
│ - 统计跟踪                                               │
└─────────────────────────────────────────────────────────┘
```

## 五大核心模块

### 1. Bootstrap (根状态)

全局状态管理，提供线程安全的状态访问。

```python
from harness import get_state_manager

state_manager = get_state_manager()
session_id = await state_manager.get_session_id()
await state_manager.set_cwd("/path/to/project")
```

**特性:**
- 单例模式
- asyncio.Lock 线程安全
- 模型使用统计
- 成本跟踪

### 2. Tasks (任务状态机)

任务生命周期管理，支持 7 种任务类型和 5 种状态。

```python
from harness import get_task_manager, TaskType, TaskStatus

task_manager = get_task_manager()
handle = await task_manager.create_task(TaskType.LOCAL_BASH, "ls -la")
await task_manager.update_task_status(handle.task_id, TaskStatus.COMPLETED)
```

**特性:**
- 任务 ID 生成（前缀 + 8 位随机字符）
- 输出持久化（~/.cktclaw/tasks/）
- 后台任务支持
- 自动清理机制

### 3. Skills (技能资产化)

技能注册与管理，支持别名和条件激活。

```python
from harness import register_skill, get_skill, SkillDefinition, LoadedFrom

skill = SkillDefinition(
    name="commit",
    description="Create a git commit",
    aliases=["ci", "c"],
    loaded_from=LoadedFrom.BUNDLED,
)
await register_skill(skill)

# 通过别名获取
skill = await get_skill("ci")
```

**特性:**
- 3 种技能类型（prompt/tool/workflow）
- 7 种技能来源
- 别名系统（一对多映射）
- 条件激活（基于路径模式）

### 4. Coordinator (调度隔离)

多智能体调度，支持 Coordinator 和 Normal 两种模式。

```python
from harness import get_coordinator_manager, CoordinatorMode

coordinator = get_coordinator_manager()
await coordinator.set_mode(CoordinatorMode.COORDINATOR)

# 获取 Worker 工具上下文
context = await coordinator.get_worker_tools_context()

# 解析 Worker 通知
notification = await coordinator.parse_notification(xml_content)
```

**特性:**
- 模式隔离（Coordinator vs Worker）
- Worker 通知解析（XML 格式）
- 任务工作流（Research → Synthesis → Implementation → Verification）
- Scratchpad 支持

### 5. Query (中枢循环)

查询循环管理，Tool-Result 配对与自愈。

```python
from harness import create_query_loop, QueryConfig

config = QueryConfig(
    system_prompt="You are a helpful assistant",
    max_turns=10,
    auto_compact_threshold=150_000,
)

loop = create_query_loop(config)
async for event in loop.run():
    if isinstance(event, dict):
        print(f"Event: {event['type']}")
    else:
        result = event
        print(f"Result: {result.terminal_reason}")
```

**特性:**
- Tool-Result 配对验证
- 自动补全缺失的 tool_result
- 自动压缩触发
- 状态机转换（Continue/Terminal）
- 预算管理（Token/Cost）

## 设计原则

1. **单例模式**: 所有管理器都是单例
2. **线程安全**: asyncio.Lock 保护共享状态
3. **状态最小化**: DO NOT ADD MORE STATE
4. **不可变状态**: 每次迭代创建新状态
5. **错误自愈**: 自动修复常见错误
6. **生成器模式**: yield 中间结果

## 测试覆盖

| 模块 | 测试数量 | 通过率 |
|------|---------|--------|
| Bootstrap | 7 | 100% |
| Tasks | 11 | 100% |
| Skills | 10 | 100% |
| Coordinator | 13 | 100% |
| Query | 15 | 100% |
| **总计** | **56** | **100%** |

## 运行测试

```bash
# 单个模块测试
python harness/bootstrap/test_state.py
python harness/tasks/test_tasks.py
python harness/skills/test_skills.py
python harness/coordinator/test_coordinator.py
python harness/query/test_query.py

# 集成测试
python harness/test_harness_integration.py
```

## 文件结构

```
harness/
├── __init__.py                    # 总入口
├── test_harness_integration.py   # 集成测试
├── bootstrap/
│   ├── __init__.py
│   ├── state.py                   # 状态管理
│   └── test_state.py
├── tasks/
│   ├── __init__.py
│   ├── task_types.py              # 任务类型
│   ├── task_manager.py            # 任务管理器
│   └── test_tasks.py
├── skills/
│   ├── __init__.py
│   ├── skill_types.py             # 技能类型
│   ├── skill_registry.py          # 技能注册表
│   └── test_skills.py
├── coordinator/
│   ├── __init__.py
│   ├── coordinator_types.py       # 调度器类型
│   ├── coordinator_manager.py     # 调度管理器
│   └── test_coordinator.py
└── query/
    ├── __init__.py
    ├── query_types.py             # 查询类型
    ├── query_loop.py              # 查询循环
    └── test_query.py
```

## 版本

当前版本: **1.0.0**

## 许可

MIT License
